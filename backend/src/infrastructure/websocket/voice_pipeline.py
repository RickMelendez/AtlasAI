"""
Voice Pipeline - Whisper → Claude → TTS continuous processing.

Handles the complete voice command pipeline:
1. Whisper: audio to text transcription
2. Language detection
3. Transcript cleanup (filler words, last-intent bias)
4. UI command interception (dismiss, open chat)
5. Fast routing (deterministic commands)
6. Claude: full AI processing
7. TTS: text to speech synthesis
8. Database persistence

Runs in background without blocking the WebSocket receive loop.
"""

import asyncio
import base64
import logging
from datetime import datetime
from typing import Optional

from src.domain.entities.assistant_state import AssistantMode, AssistantState
from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message, MessageRole
from src.infrastructure.database import AsyncSessionFactory
from src.infrastructure.database.repositories.conversation_repository import (
    SQLiteConversationRepository,
)
from src.infrastructure.database.repositories.memory_repository import MemoryRepository
from src.infrastructure.events.event_bus import event_bus
from src.infrastructure.events.event_types import EventType
from src.infrastructure.monitoring.sentry import (
    capture_exception as sentry_capture,
)
from src.infrastructure.websocket.command_router import (
    CHAT_OPEN_TRIGGERS,
    DISMISS_TRIGGERS,
    STOP_TTS_TRIGGERS,
    clean_transcript,
    detect_language,
    fast_route,
    needs_screen_context,
    strip_wake_prefix,
)

logger = logging.getLogger(__name__)

# ── Sentence splitter ─────────────────────────────────────────────────────────

import re as _re

def _split_sentences(text: str) -> list[str]:
    """
    Split response into sentences for sentence-level TTS streaming.

    Short sentences are merged with the next one to avoid very short audio clips
    (which have more overhead per ElevenLabs call than they're worth).
    """
    # Split on sentence-ending punctuation followed by whitespace or end-of-string
    raw = _re.split(r'(?<=[.!?])\s+', text.strip())
    sentences: list[str] = []
    buf = ""
    for s in raw:
        s = s.strip()
        if not s:
            continue
        if buf:
            buf += " " + s
        else:
            buf = s
        # Flush buffer when we have a substantial sentence (≥ 30 chars)
        if len(buf) >= 30:
            sentences.append(buf)
            buf = ""
    if buf:
        sentences.append(buf)
    return sentences if sentences else [text.strip()]


def strip_for_tts(text: str) -> str:
    """Remove markdown and symbols TTS should never read aloud."""
    # Remove code blocks entirely
    text = _re.sub(r'```[\s\S]*?```', '', text)
    text = _re.sub(r'`[^`]+`', '', text)
    # Strip markdown formatting characters, keep the inner text
    text = _re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    text = _re.sub(r'_{1,2}([^_\n]+)_{1,2}', r'\1', text)
    text = _re.sub(r'^#{1,6}\s+', '', text, flags=_re.MULTILINE)
    text = _re.sub(r'^\s*[-*+]\s+', '', text, flags=_re.MULTILINE)
    text = _re.sub(r'^\s*\d+\.\s+', '', text, flags=_re.MULTILINE)
    text = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = _re.sub(r'[>#|~]', '', text)
    # Collapse whitespace
    text = _re.sub(r'\n+', ' ', text)
    text = _re.sub(r'\s{2,}', ' ', text)
    return text.strip()


async def run_voice_pipeline(
    session_id: str,
    audio_bytes: bytes,
    state: Optional[AssistantState],
    screen_context: Optional[str],
    whisper_service,
    voice_use_case_factory,
    tool_executor,
    ws_manager,
    tts_service=None,
) -> None:
    """
    Execute Whisper → Claude → TTS in background.

    Does not block handle_messages, so WebSocket continues responding to pings
    during the entire processing, avoiding 1011 keepalive timeout.

    Args:
        session_id: Unique session identifier
        audio_bytes: Raw audio data (WebM/Opus from frontend)
        state: AssistantState for this session
        screen_context: Screen description if available
        whisper_service: FasterWhisper service for transcription
        voice_use_case_factory: Factory to create ProcessVoiceCommandUseCase
        tool_executor: ToolExecutor for browser/terminal/file operations
        ws_manager: WebSocketManager for sending events
    """
    try:
        # Step 1: Transcribe with Whisper (auto-detect language)
        pre_transcript = None
        if whisper_service:
            pre_transcript = await whisper_service.transcribe_audio(
                audio_bytes, language=None
            )
            if not pre_transcript or len(pre_transcript.strip()) < 2:
                logger.debug("[Voice] Empty transcription (silence/VAD filtered)")
                if state:
                    state.reset_to_active()
                return

            if pre_transcript and state:
                state.language = detect_language(pre_transcript)
                logger.info(
                    f"[{session_id}] Language detected: {state.language} "
                    f"from: '{pre_transcript[:60]}'"
                )

        if not pre_transcript or not pre_transcript.strip():
            logger.warning(f"[{session_id}] Empty transcription — skipping")
            if state:
                state.reset_to_active()
            return

        # Step 2: Clean transcript (remove filler words, apply last-intent bias)
        transcription = clean_transcript(pre_transcript)
        normalized = strip_wake_prefix(transcription.lower().strip())
        logger.info(f"[{session_id}] Cleaned transcript: '{transcription}'")

        # Step 3: UI command interception (before Claude)

        # Stop TTS — no audio response, just tell frontend to cut playback
        if any(t in normalized for t in STOP_TTS_TRIGGERS):
            logger.info(f"[{session_id}] Stop command detected — cutting TTS")
            await ws_manager.send_event(
                session_id,
                {"type": "stop_tts", "data": {}},
            )
            if state:
                state.reset_to_active()
            return

        if any(t in normalized for t in DISMISS_TRIGGERS):
            logger.info(f"[{session_id}] UI command: dismiss")
            await ws_manager.send_event(
                session_id,
                {"type": "ui_command", "data": {"action": "dismiss"}},
            )
            if state:
                state.reset_to_active()
            return

        if any(t in normalized for t in CHAT_OPEN_TRIGGERS):
            logger.info(f"[{session_id}] UI command: open_chat")
            await ws_manager.send_event(
                session_id,
                {"type": "ui_command", "data": {"action": "open_chat"}},
            )
            if state:
                state.reset_to_active()
            return

        # Step 4: Fast router (deterministic commands, 0ms latency)
        route = fast_route(normalized)
        if route and tool_executor:
            logger.info(
                f"[{session_id}] Fast route: {route['tool']}({route['args']})"
            )
            try:
                tool_result = await tool_executor.execute(
                    route["tool"], route["args"]
                )
                response_text = "Done — opened that for you."
                logger.info(
                    f"[{session_id}] Fast route executed: {tool_result[:80]}"
                )
            except Exception as tool_err:
                logger.error(f"[{session_id}] Fast route error: {tool_err}")
                response_text = f"I tried to open that but hit an error: {tool_err}"

            # Send fast route response
            await ws_manager.send_event(
                session_id,
                {
                    "type": EventType.AI_RESPONSE_GENERATED.value,
                    "data": {
                        "message": response_text,
                        "transcription": transcription,
                        "timestamp": datetime.now().isoformat(),
                    },
                },
            )
            # TTS for brief confirmation — use ElevenLabs to keep voice consistent
            tts_audio_b64 = None
            if tts_service:
                try:
                    audio_bytes_tts = await tts_service.synthesize_speech(response_text)
                    tts_audio_b64 = base64.b64encode(audio_bytes_tts).decode("utf-8")
                except Exception as tts_err:
                    logger.warning(f"[{session_id}] Fast route TTS error: {tts_err}")
            await ws_manager.send_event(
                session_id,
                {
                    "type": "tts_audio",
                    "data": {
                        "audio_b64": tts_audio_b64,
                        "format": "mp3",
                        "text": response_text,
                    },
                },
            )
            logger.info(f"[{session_id}] Fast route complete")

        else:
            # Step 5: Claude path (full voice pipeline)
            # Load long-term memories to inject into Claude's system prompt
            memories: list[str] = []
            try:
                async with AsyncSessionFactory() as _mem_sess:
                    _mem_repo = MemoryRepository(_mem_sess)
                    memories = [m.content for m in await _mem_repo.get_all_memories()]
            except Exception as _mem_err:
                logger.warning(f"[{session_id}] Could not load memories: {_mem_err}")

            # Skip TTS inside the use case — we handle it sentence-by-sentence below
            # to reduce perceived latency (first sentence plays ~1s sooner).
            voice_use_case = voice_use_case_factory(state, include_tts=False)
            result = await voice_use_case.execute(
                audio_data=audio_bytes,
                conversation_history=None,
                screen_context=screen_context,
                transcription=transcription,
                memories=memories,
            )

            if result["success"]:
                # ── Send text to frontend immediately ──────────────────────────
                # Text appears in chat right away; audio follows sentence by sentence.
                await ws_manager.send_event(
                    session_id,
                    {
                        "type": EventType.AI_RESPONSE_GENERATED.value,
                        "data": {
                            "message": result["response"],
                            "transcription": transcription,
                            "timestamp": datetime.now().isoformat(),
                        },
                    },
                )

                # ── Parallel sentence-level TTS ────────────────────────────────
                # Synthesize all sentences concurrently, then send in order.
                # Parallel synthesis cuts total TTS wait from N×latency to ~1×latency.
                if tts_service:
                    sentences = _split_sentences(result["response"])
                    logger.info(
                        f"[{session_id}] TTS: {len(sentences)} sentence(s) — parallel synthesis"
                    )

                    async def _synth(s: str):
                        return await tts_service.synthesize_speech(strip_for_tts(s))

                    synth_results = await asyncio.gather(
                        *[_synth(s) for s in sentences], return_exceptions=True
                    )

                    any_audio_sent = False
                    for i, (sentence, audio_or_err) in enumerate(zip(sentences, synth_results)):
                        if isinstance(audio_or_err, Exception):
                            logger.warning(
                                f"[{session_id}] TTS sentence {i+1} error: {audio_or_err}"
                            )
                            continue
                        tts_audio_b64 = base64.b64encode(audio_or_err).decode("utf-8")
                        await ws_manager.send_event(
                            session_id,
                            {
                                "type": "tts_audio",
                                "data": {
                                    "audio_b64": tts_audio_b64,
                                    "format": "mp3",
                                    "text": sentence,
                                },
                            },
                        )
                        any_audio_sent = True
                        logger.info(
                            f"[{session_id}] TTS sentence {i+1}/{len(sentences)} sent"
                        )

                    # If ElevenLabs failed for ALL sentences (e.g. 402 free-plan limit),
                    # send a null-audio event so the frontend falls back to browser
                    # speechSynthesis instead of staying completely silent.
                    if not any_audio_sent:
                        logger.info(
                            f"[{session_id}] All ElevenLabs calls failed — "
                            "sending browser speechSynthesis fallback"
                        )
                        await ws_manager.send_event(
                            session_id,
                            {
                                "type": "tts_audio",
                                "data": {
                                    "audio_b64": None,
                                    "format": "mp3",
                                    "text": result["response"],
                                },
                            },
                        )
                else:
                    # No TTS service — send empty audio event so frontend can fall back
                    await ws_manager.send_event(
                        session_id,
                        {
                            "type": "tts_audio",
                            "data": {
                                "audio_b64": None,
                                "format": "mp3",
                                "text": result["response"],
                            },
                        },
                    )
                    logger.info(f"[{session_id}] TTS text sent (fallback — no TTS service)")

                # Persist voice exchange to database
                try:
                    async with AsyncSessionFactory() as session:
                        async with session.begin():
                            repo = SQLiteConversationRepository(session)
                            conversation = (
                                await repo.get_active_conversation_by_session(session_id)
                            )
                            if not conversation:
                                lang = state.language if state else "es"
                                conversation = Conversation(
                                    session_id=session_id, language=lang
                                )
                                await repo.create_conversation(conversation)
                            # Save user transcription
                            user_msg = Message(
                                conversation_id=conversation.id,
                                role=MessageRole.USER,
                                content=transcription,
                            )
                            await repo.add_message(user_msg)
                            # Save assistant response
                            assistant_msg = Message(
                                conversation_id=conversation.id,
                                role=MessageRole.ASSISTANT,
                                content=result["response"],
                            )
                            await repo.add_message(assistant_msg)
                            conversation.touch()
                            await repo.update_conversation(conversation)
                    logger.info(f"[{session_id}] Voice exchange persisted to DB")
                except Exception as db_err:
                    logger.error(
                        f"[{session_id}] Voice DB persistence error: {db_err}",
                        exc_info=True,
                    )
                    # Do not fail pipeline for DB error — TTS already sent

            else:
                await ws_manager.send_event(
                    session_id,
                    {
                        "type": EventType.AI_RESPONSE_GENERATED.value,
                        "data": {
                            "message": result["response"],
                            "error": True,
                            "error_detail": result.get("error"),
                        },
                    },
                )

        # Return to ACTIVE and notify frontend
        if state:
            old_mode = state.mode
            state.finish_speaking()
            await ws_manager.send_event(
                session_id,
                {
                    "type": EventType.STATE_CHANGED.value,
                    "data": {
                        "old_mode": old_mode.value,
                        "new_mode": state.mode.value,
                        "state": state.to_dict(),
                    },
                },
            )

    except Exception as e:
        logger.error(
            f"[{session_id}] Voice pipeline error: {e}", exc_info=True
        )
        sentry_capture(e, session_id=session_id, context="voice_pipeline")
        if state:
            old_mode = state.mode
            state.reset_to_active()
            await ws_manager.send_event(
                session_id,
                {
                    "type": EventType.STATE_CHANGED.value,
                    "data": {
                        "old_mode": old_mode.value,
                        "new_mode": state.mode.value,
                        "state": state.to_dict(),
                    },
                },
            )
    finally:
        # Ensure state always resets to ACTIVE after voice pipeline
        if state and state.mode != AssistantMode.ACTIVE:
            state.reset_to_active()
            logger.debug(f"[{session_id}] Force-reset state to ACTIVE")
