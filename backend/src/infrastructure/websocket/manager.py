"""
WebSocket Manager - Thin coordinator for WebSocket connections and continuous loops.

This is the CRITICAL component that differentiates Atlas from a traditional chatbot.
It maintains continuous loops that enable 24/7 listening and screen monitoring.

Responsibilities:
1. Coordinate WebSocket lifecycle (via SessionManager)
2. Handle incoming messages (voice chunks, commands, text, screen frames)
3. Route fast deterministic commands (via CommandRouter)
4. Execute voice pipeline in background (via voice_pipeline)
5. Manage screen capture loop

Frontend messages:
  - ping            → pong (keepalive)
  - audio_chunk     → PCM Int16 for wake word detection (OpenWakeWord)
  - audio_command   → full audio (WebM/Opus) for STT (Whisper)
  - chat_message    → user text
  - screen_capture  → screen frame for OCR

Frontend events:
  - websocket_connected    → connection confirmed
  - wake_word_detected     → "Hey Atlas" detected
  - state_changed          → mode change (INACTIVE → LISTENING → THINKING → ACTIVE)
  - ai_response_generated  → Claude text response
  - tts_audio              → MP3 audio base64 response
  - pong                   → keepalive response
"""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

from src.adapters.vision.mss_capture_adapter import MSSCaptureAdapter
from src.domain.entities.assistant_state import AssistantMode, AssistantState
from src.infrastructure.events.event_bus import event_bus
from src.infrastructure.events.event_types import EventType
from src.infrastructure.monitoring.sentry import (
    capture_exception as sentry_capture,
    set_session_context,
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
from src.infrastructure.websocket.session_manager import SessionManager
from src.infrastructure.websocket.voice_pipeline import run_voice_pipeline

if TYPE_CHECKING:
    from src.application.use_cases.process_voice_command import (
        ProcessVoiceCommandUseCase,
    )

logger = logging.getLogger(__name__)



class WebSocketManager:
    """
    Thin coordinator for WebSocket connections and continuous loops.

    Delegates core responsibilities to specialized modules:
    - SessionManager: WebSocket lifecycle (connect, disconnect)
    - CommandRouter: Fast deterministic routing
    - voice_pipeline: Whisper → Claude → TTS processing

    Attributes:
        _session_manager: SessionManager instance
        _voice_busy: Guard preventing concurrent voice pipelines per session
        _whisper_service: FasterWhisper service for transcription
        _wake_word_pcm_buffers: PCM buffer per session for wake word detection
        _wake_word_checking: Guard preventing concurrent Whisper calls
    """

    def __init__(self):
        self._session_manager = SessionManager()
        self._voice_busy: Dict[str, bool] = {}
        self._whisper_service = None
        self._wake_word_pcm_buffers: Dict[str, bytearray] = {}
        self._wake_word_checking: Dict[str, bool] = {}
        logger.info("WebSocket Manager initialized")

    @staticmethod
    def _decode_b64(data: str, context: str = "") -> Optional[bytes]:
        """Decode base64 to bytes; return None and log if failed."""
        try:
            return base64.b64decode(data)
        except Exception as e:
            logger.error(f"Cannot decode base64 {context}: {e}")
            return None

    @staticmethod
    def _pcm16_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
        """Wrap PCM Int16 raw in WAV container for Whisper."""
        import struct

        num_channels = 1
        bits_per_sample = 16
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = len(pcm_bytes)
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + data_size,
            b"WAVE",
            b"fmt ",
            16,
            1,
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b"data",
            data_size,
        )
        return header + pcm_bytes

    @staticmethod
    def _make_event(event_type: str, data: Optional[dict] = None) -> dict:
        """
        Build standard WebSocket event envelope.

        Centralizes construction of {"type": ..., "data": ...} for consistency.

        Args:
            event_type: Event name (EventType.XXX.value or string literal)
            data: Optional event payload

        Returns:
            Event envelope ready for send_event()
        """
        event: dict = {"type": event_type}
        if data is not None:
            event["data"] = data
        return event

    def set_voice_use_case_factory(self, factory: Callable) -> None:
        """
        Inject ProcessVoiceCommandUseCase factory.

        Factory receives AssistantState and returns configured use case.

        Args:
            factory: Callable[[AssistantState], ProcessVoiceCommandUseCase]
        """
        self._session_manager.set_voice_use_case_factory(factory)
        logger.info("✅ Voice use case factory registered")

    def set_whisper_service(self, whisper_service) -> None:
        """Inject FasterWhisper service for wake word detection fallback."""
        self._whisper_service = whisper_service
        self._session_manager.set_whisper_service(whisper_service)
        logger.info("✅ Whisper service registered")

    def set_tool_executor(self, tool_executor) -> None:
        """Inject ToolExecutor (Playwright, terminal, files, Notion)."""
        self._session_manager.set_tool_executor(tool_executor)
        logger.info("✅ ToolExecutor registered")

    def update_screen_context(
        self, session_id: str, description: Optional[str]
    ) -> None:
        """Store latest screen description for session."""
        self._session_manager.update_screen_context(session_id, description)

    # Lifecycle

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Accept WebSocket connection and start continuous loops.

        Args:
            websocket: FastAPI WebSocket connection
            session_id: Unique session identifier
        """
        try:
            await self._session_manager.connect(websocket, session_id)

            set_session_context(session_id)

            await event_bus.emit(
                EventType.WEBSOCKET_CONNECTED.value,
                {"session_id": session_id, "timestamp": datetime.now().isoformat()},
            )

            await self.send_event(
                session_id,
                self._make_event(
                    EventType.WEBSOCKET_CONNECTED.value,
                    {
                        "session_id": session_id,
                        "status": "connected",
                        "message": "Atlas AI connected — ready to listen",
                    },
                ),
            )

            # Start main loop in background
            asyncio.create_task(self.handle_messages(session_id))
            # Start screen capture loop in background
            asyncio.create_task(self._screen_capture_loop(session_id))

            logger.info(f"[{session_id}] Continuous loops started")

        except Exception as e:
            logger.error(
                f"Error connecting WebSocket for {session_id}: {e}", exc_info=True
            )
            sentry_capture(e, session_id=session_id, context="connect")
            raise

    def disconnect(self, session_id: str) -> None:
        """Close connection and stop loops."""
        self._session_manager.disconnect(session_id)
        logger.info(f"[{session_id}] WebSocket disconnected")

    # Sending

    async def send_event(self, session_id: str, event: dict) -> None:
        """Send JSON event to frontend."""
        await self._session_manager.send_event(session_id, event)

    async def broadcast_event(self, event: dict) -> None:
        """Send event to all active connections."""
        await self._session_manager.broadcast_event(event)

    # Main loop

    async def handle_messages(self, session_id: str) -> None:
        """
        Main loop listening to all frontend messages.

        Processes:
        - audio_chunk    → wake word detection via OpenWakeWord
        - audio_command  → STT + AI + TTS pipeline
        - chat_message   → text directly to AI
        - screen_capture → OCR + screen analysis
        - ping           → keepalive
        """
        logger.info(f"[{session_id}] Message handler loop started")

        # OpenWakeWord adapter for this session (lazy init — loads ONNX models locally)
        oww = None
        try:
            from src.adapters.voice.open_wake_word_adapter import (
                OpenWakeWordAdapter,
            )

            loop = asyncio.get_running_loop()
            oww = await loop.run_in_executor(None, OpenWakeWordAdapter)
            logger.info(f"[{session_id}] OpenWakeWord detection active")
        except Exception as oww_err:
            logger.warning(
                f"[{session_id}] Could not init OpenWakeWord: {oww_err}. "
                "Wake word detection via Whisper fallback or manual trigger only."
            )

        while self._session_manager.running_loops.get(session_id, False):
            try:
                ws = self._session_manager.get_websocket(session_id)
                if not ws:
                    break

                try:
                    data = await asyncio.wait_for(ws.receive_json(), timeout=1.0)
                    msg_type = data.get("type", "")
                    logger.debug(f"[{session_id}] ← {msg_type}")

                    # ping / keepalive
                    if msg_type == "ping":
                        await self.send_event(session_id, self._make_event("pong"))

                    # audio_chunk: wake word detection
                    elif msg_type == "audio_chunk":
                        await self._handle_audio_chunk(session_id, data, oww)

                    # wake_word_trigger: browser SpeechRecognition detected wake word
                    elif msg_type == "wake_word_trigger":
                        state = self._session_manager.get_state(session_id)
                        wake_word = (data.get("data", {}) or {}).get(
                            "wake_word", "hey atlas"
                        )
                        if state and state.mode not in (AssistantMode.LISTENING,):
                            state.start_listening()
                            await self.send_event(
                                session_id,
                                self._make_event(
                                    EventType.WAKE_WORD_DETECTED.value,
                                    {
                                        "wake_word": wake_word,
                                        "timestamp": datetime.now().isoformat(),
                                    },
                                ),
                            )
                            logger.info(
                                f"[{session_id}] Wake word via browser "
                                f"SpeechRecognition: '{wake_word}'"
                            )

                    # audio_command: full speech → STT → AI → TTS
                    elif msg_type == "audio_command":
                        await self._handle_audio_command(session_id, data)

                    # chat_message: text input
                    elif msg_type == "chat_message":
                        message = data.get("data", {}).get("message", "")
                        if message:
                            logger.info(f"[{session_id}] Chat: '{message[:60]}'")
                            # Auto-detect language from user text
                            detected_lang = detect_language(message)
                            state = self._session_manager.get_state(session_id)
                            if state:
                                state.language = detected_lang
                            # Only inject screen context when message references screen
                            screen_ctx = (
                                self._session_manager.screen_contexts.get(session_id)
                                if needs_screen_context(message)
                                else None
                            )
                            await event_bus.emit(
                                EventType.USER_MESSAGE_RECEIVED.value,
                                {
                                    "session_id": session_id,
                                    "message": message,
                                    "timestamp": datetime.now().isoformat(),
                                    "screen_context": screen_ctx,
                                },
                            )
                            await self.send_event(
                                session_id,
                                self._make_event(
                                    "message_received", {"status": "processing"}
                                ),
                            )

                    # screen_capture: OCR frame
                    elif msg_type == "screen_capture":
                        inner_sc = data.get("data", {}) or {}
                        screenshot_data = inner_sc.get("data", "")
                        if screenshot_data:
                            await event_bus.emit(
                                EventType.SCREEN_CONTEXT_UPDATED.value,
                                {
                                    "session_id": session_id,
                                    "screenshot_data": screenshot_data,
                                    "timestamp": inner_sc.get(
                                        "timestamp",
                                        datetime.now().timestamp() * 1000,
                                    ),
                                    "format": inner_sc.get("format", "jpeg"),
                                },
                            )

                    # set_language
                    elif msg_type == "set_language":
                        lang = data.get("data", {}).get("language", "es")
                        state = self._session_manager.get_state(session_id)
                        if state:
                            state.language = lang
                            logger.info(f"[{session_id}] Language set to: {lang}")

                except asyncio.TimeoutError:
                    continue

            except WebSocketDisconnect:
                logger.info(f"[{session_id}] Disconnected in main loop")
                break

            except Exception as e:
                logger.error(f"[{session_id}] Loop error: {e}", exc_info=True)
                sentry_capture(
                    e, session_id=session_id, context="handle_messages"
                )
                await asyncio.sleep(1)

        # Cleanup OpenWakeWord (no explicit stop needed — GC handles ONNX sessions)
        oww = None

        logger.info(f"[{session_id}] Message handler loop stopped")

    async def _handle_audio_chunk(
        self, session_id: str, data: dict, oww
    ) -> None:
        """
        Process PCM audio chunk for wake word detection.

        Frontend sends chunks of ~1280 samples (Int16, 16kHz, mono)
        encoded in base64. OpenWakeWord processes 2560-byte chunks
        and detects the wake word.

        Args:
            session_id: Session identifier
            data: Message with 'audio' field (base64 PCM)
            oww: OpenWakeWordAdapter instance (may be None)
        """
        state = self._session_manager.get_state(session_id)

        # Listen for wake words in INACTIVE, ACTIVE, and LISTENING modes.
        # LISTENING included because frontend sends PCM chunks while recording
        # user command; discarding would break voice pipeline on subsequent attempts.
        if state and state.mode not in (
            AssistantMode.INACTIVE,
            AssistantMode.ACTIVE,
            AssistantMode.LISTENING,
        ):
            return

        # Get PCM audio — frontend wraps in "data" field
        inner_chunk = data.get("data", {}) or {}
        audio_b64 = inner_chunk.get("audio", "") or data.get("audio", "")
        if not audio_b64:
            return

        audio_bytes = self._decode_b64(audio_b64, "audio_chunk")
        if audio_bytes is None:
            return

        # If OpenWakeWord unavailable, accumulate PCM for Whisper wake word
        if oww is None:
            if (
                self._whisper_service
                and state
                and state.mode in (AssistantMode.INACTIVE, AssistantMode.ACTIVE)
                and not self._wake_word_checking.get(session_id, False)
            ):
                buf = self._wake_word_pcm_buffers.setdefault(
                    session_id, bytearray()
                )
                buf.extend(audio_bytes)
                # 3 seconds at 16kHz, 16-bit mono = 96000 bytes
                if len(buf) >= 96000:
                    pcm_snapshot = bytes(buf[:96000])
                    # Slide: keep last 1s overlap
                    self._wake_word_pcm_buffers[session_id] = bytearray(
                        buf[64000:]
                    )
                    asyncio.create_task(
                        self._check_whisper_wake_word(session_id, pcm_snapshot, state)
                    )
            return

        # Accumulate in buffer per session and drain in 1280-sample chunks (2560 bytes)
        buf = self._wake_word_pcm_buffers.setdefault(session_id, bytearray())
        buf.extend(audio_bytes)

        _OWW_CHUNK = 2560  # 1280 samples × 2 bytes (Int16)

        while len(buf) >= _OWW_CHUNK:
            chunk = bytes(buf[:_OWW_CHUNK])
            del buf[:_OWW_CHUNK]

            try:
                detected = oww.detect_wake_word(chunk)
                if detected:
                    logger.info(f"[{session_id}] Wake word detected (OpenWakeWord)")

                    if state and state.mode not in (AssistantMode.LISTENING,):
                        state.start_listening()

                    await self.send_event(
                        session_id,
                        self._make_event(
                            EventType.WAKE_WORD_DETECTED.value,
                            {
                                "wake_word": "hey atlas",
                                "timestamp": datetime.now().isoformat(),
                            },
                        ),
                    )
                    # Clean buffer after successful detection
                    self._wake_word_pcm_buffers.pop(session_id, None)
                    break

            except Exception as e:
                logger.error(f"[{session_id}] OpenWakeWord error: {e}")
                sentry_capture(e, session_id=session_id, context="oww_detect")
                break

    async def _check_whisper_wake_word(
        self, session_id: str, pcm_bytes: bytes, state
    ) -> None:
        """
        Transcribe 3-second PCM clip with Whisper to detect "atlas" wake word.

        Only called when OpenWakeWord unavailable.
        Filters silent clips by average energy before API call.
        """
        self._wake_word_checking[session_id] = True
        try:
            # Energy filter: avoid Whisper calls on silence
            import array as _array

            samples = _array.array("h", pcm_bytes)
            avg_abs = sum(abs(s) for s in samples) / max(len(samples), 1)
            if avg_abs < 1200:  # filter ambient noise (32767 = max)
                return

            wav_bytes = self._pcm16_to_wav(pcm_bytes)
            transcript = await self._whisper_service.transcribe_audio(
                wav_bytes, language="en"
            )
            if not transcript:
                return

            text = transcript.lower().strip()
            logger.debug(f"[{session_id}] Wake word check: '{text[:60]}'")

            if "atlas" in text:
                logger.info(f"[{session_id}] Wake word via Whisper: '{text}'")
                if state and state.mode not in (AssistantMode.LISTENING,):
                    state.start_listening()
                    await self.send_event(
                        session_id,
                        self._make_event(
                            EventType.WAKE_WORD_DETECTED.value,
                            {
                                "wake_word": "atlas",
                                "timestamp": datetime.now().isoformat(),
                            },
                        ),
                    )
                    # Clean buffer after successful detection
                    self._wake_word_pcm_buffers.pop(session_id, None)

        except Exception as e:
            logger.debug(f"[{session_id}] Whisper wake word check failed: {e}")
        finally:
            self._wake_word_checking[session_id] = False

    async def _handle_audio_command(self, session_id: str, data: dict) -> None:
        """
        Receive audio_command, validate, and fire pipeline in background.

        The pipeline (Whisper→Claude→TTS) runs as separate asyncio.Task
        so the WebSocket receive loop NEVER blocks. Without this, a 10+ second
        call would prevent ping processing and close with 1011 keepalive timeout.
        """
        # Get audio — frontend wraps payload in "data" field
        inner = data.get("data", {}) or {}
        audio_b64 = inner.get("audio", "") or data.get("audio", "")
        if not audio_b64:
            logger.warning(f"[{session_id}] audio_command with no audio data")
            return

        audio_bytes = self._decode_b64(
            audio_b64, f"audio_command [{session_id}]"
        )
        if audio_bytes is None:
            return

        logger.info(
            f"[{session_id}] Audio command: {len(audio_bytes)} bytes"
        )

        if not self._session_manager._voice_use_case_factory:
            logger.error(f"[{session_id}] No voice use case factory registered")
            return

        # Drop if pipeline already running for this session
        if self._voice_busy.get(session_id):
            logger.warning(f"[{session_id}] Voice pipeline busy — dropping")
            return

        # Immediate ack to frontend (doesn't wait for pipeline)
        await self.send_event(
            session_id,
            self._make_event("message_received", {"status": "processing"}),
        )

        # Fire pipeline in background — receive loop stays free
        asyncio.create_task(
            self._run_voice_pipeline(session_id, audio_bytes)
        )

    async def _run_voice_pipeline(self, session_id: str, audio_bytes: bytes) -> None:
        """
        Execute Whisper → Claude → TTS in background.

        Delegates to voice_pipeline module. Does not block handle_messages,
        so WebSocket continues responding to pings during processing,
        avoiding 1011 keepalive timeout.
        """
        self._voice_busy[session_id] = True
        try:
            state = self._session_manager.get_state(session_id)
            await run_voice_pipeline(
                session_id=session_id,
                audio_bytes=audio_bytes,
                state=state,
                screen_context=self._session_manager.screen_contexts.get(session_id),
                whisper_service=self._whisper_service,
                voice_use_case_factory=self._session_manager._voice_use_case_factory,
                tool_executor=self._session_manager._tool_executor,
                ws_manager=self,
            )
        finally:
            self._voice_busy[session_id] = False

    # Screen capture loop

    async def _screen_capture_loop(self, session_id: str) -> None:
        """
        Continuous loop capturing primary screen every 3 seconds using mss
        and sending as screen_capture event to frontend.

        Replaces Electron desktopCapturer — requires no screen permissions.
        """
        mss_adapter = MSSCaptureAdapter()
        logger.info(f"[{session_id}] MSS screen capture loop started")

        while self._session_manager.running_loops.get(session_id, False):
            try:
                b64_image = await asyncio.get_event_loop().run_in_executor(
                    None, mss_adapter.capture_primary_screen
                )
                await self.send_event(
                    session_id,
                    {
                        "type": "screen_capture",
                        "data": {
                            "data": b64_image,
                            "timestamp": datetime.now().isoformat(),
                            "format": "jpeg",
                        },
                    },
                )
            except Exception as e:
                logger.debug(
                    f"[{session_id}] Screen capture error (non-fatal): {e}"
                )

            await asyncio.sleep(3)

        logger.info(f"[{session_id}] MSS screen capture loop stopped")

    # State management

    def get_state(self, session_id: str) -> Optional[AssistantState]:
        """Get assistant state for session."""
        return self._session_manager.get_state(session_id)

    def update_state(self, session_id: str, new_mode: AssistantMode) -> None:
        """Update assistant mode and notify frontend."""
        state = self._session_manager.get_state(session_id)
        if not state:
            logger.warning(f"[{session_id}] Cannot update state: session not found")
            return

        old_mode = state.mode
        state.mode = new_mode
        logger.info(f"[{session_id}] State: {old_mode.value} → {new_mode.value}")

        asyncio.create_task(
            self.send_event(
                session_id,
                self._make_event(
                    EventType.STATE_CHANGED.value,
                    {
                        "old_mode": old_mode.value,
                        "new_mode": new_mode.value,
                        "state": state.to_dict(),
                    },
                ),
            )
        )


# Global singleton
ws_manager = WebSocketManager()
