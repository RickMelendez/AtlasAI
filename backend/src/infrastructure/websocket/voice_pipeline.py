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
from src.infrastructure.events.event_bus import event_bus
from src.infrastructure.events.event_types import EventType
from src.infrastructure.monitoring.sentry import (
    capture_exception as sentry_capture,
)
from src.infrastructure.websocket.command_router import (
    CHAT_OPEN_TRIGGERS,
    DISMISS_TRIGGERS,
    clean_transcript,
    detect_language,
    fast_route,
    needs_screen_context,
    strip_wake_prefix,
)

logger = logging.getLogger(__name__)


async def run_voice_pipeline(
    session_id: str,
    audio_bytes: bytes,
    state: Optional[AssistantState],
    screen_context: Optional[str],
    whisper_service,
    voice_use_case_factory,
    tool_executor,
    ws_manager,
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
            # TTS for brief confirmation
            await ws_manager.send_event(
                session_id,
                {
                    "type": "tts_audio",
                    "data": {
                        "audio_b64": None,
                        "format": "mp3",
                        "text": response_text,
                    },
                },
            )
            logger.info(f"[{session_id}] Fast route complete")

        else:
            # Step 5: Claude path (full voice pipeline)
            voice_use_case = voice_use_case_factory(state)
            result = await voice_use_case.execute(
                audio_data=audio_bytes,
                conversation_history=None,
                screen_context=screen_context,
                transcription=transcription,
            )

            if result["success"]:
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

                await ws_manager.send_event(
                    session_id,
                    {
                        "type": "tts_audio",
                        "data": {
                            "audio_b64": result.get("audio_response_b64"),
                            "format": "mp3",
                            "text": result["response"],
                        },
                    },
                )
                if result.get("has_audio"):
                    logger.info(f"[{session_id}] TTS audio sent")
                else:
                    logger.info(f"[{session_id}] TTS text sent (fallback)")

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
