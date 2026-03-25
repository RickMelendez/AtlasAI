"""
WebSocket Manager - Maneja conexiones WebSocket y loops continuos.

Este es el componente MÁS CRÍTICO del sistema Atlas.
Es lo que diferencia Atlas de un chatbot tradicional - mantiene loops
continuos que permiten escuchar 24/7 y monitorear pantalla.

Mensajes que recibe del frontend:
  - ping            → responde con pong (keepalive)
  - audio_chunk     → chunk PCM Int16 para wake word detection (OpenWakeWord)
  - audio_command   → audio completo (WebM/WAV) para STT (Whisper)
  - chat_message    → mensaje de texto del usuario
  - screen_capture  → frame de pantalla para OCR

Mensajes que envía al frontend:
  - websocket_connected    → confirmación de conexión
  - wake_word_detected     → se detectó "Hey Atlas"
  - state_changed          → cambio de modo (IDLE → LISTENING → THINKING → SPEAKING)
  - ai_response_generated  → respuesta de texto de Claude
  - tts_audio              → audio MP3 base64 de la respuesta hablada
  - pong                   → respuesta a ping
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Optional

from src.adapters.vision.mss_capture_adapter import MSSCaptureAdapter

from fastapi import WebSocket, WebSocketDisconnect

from src.domain.entities.assistant_state import AssistantMode, AssistantState
from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message, MessageRole
from src.infrastructure.database import AsyncSessionFactory
from src.infrastructure.database.repositories.conversation_repository import \
    SQLiteConversationRepository
from src.infrastructure.events.event_bus import event_bus
from src.infrastructure.events.event_types import EventType
from src.infrastructure.monitoring.sentry import \
    capture_exception as sentry_capture
from src.infrastructure.monitoring.sentry import set_session_context

if TYPE_CHECKING:
    from src.application.use_cases.process_voice_command import \
        ProcessVoiceCommandUseCase

logger = logging.getLogger(__name__)

# ── UI command trigger sets ───────────────────────────────────────────────────

_DISMISS_TRIGGERS = {"dismiss", "go away", "hide", "minimize", "bye atlas", "goodbye atlas"}
_CHAT_OPEN_TRIGGERS = {"open chat", "chat mode", "open chat mode", "show chat", "open chat mode"}

_WAKE_PREFIXES = ("hey atlas,", "hey atlas", "hola atlas,", "hola atlas", "atlas,", "atlas")


def _strip_wake_prefix(text: str) -> str:
    """Remove wake-word prefix so UI command matching works correctly."""
    for prefix in _WAKE_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


# ── Language / screen-context helpers ────────────────────────────────────────

_EN_WORDS = {
    'the', 'is', 'it', 'in', 'of', 'a', 'an', 'and', 'to', 'you', 'i',
    'what', 'how', 'can', 'do', 'my', 'me', 'this', 'that', 'are', 'was',
    'be', 'have', 'has', 'will', 'with', 'for', 'on', 'at', 'by', 'from',
    'or', 'but', 'not', 'yes', 'ok', 'please', 'make', 'show', 'run',
    'open', 'go', 'help', 'use', 'get', 'need', 'want', 'im', "i'm",
    'hey', 'hi', 'hello', 'its', "it's", 'just', 'dont', "don't",
}
_ES_CHARS = set('áéíóúüñ¿¡')

_SCREEN_KEYWORDS = {
    # English
    'this', 'here', 'screen', 'error', 'see', 'look', 'what', 'window',
    'page', 'browser', 'terminal', 'code', 'file', 'line', 'tab', 'site',
    'url', 'running', 'showing', 'warning', 'bug', 'crash', 'output',
    # Spanish
    'esto', 'aquí', 'aqui', 'pantalla', 'ves', 'mira', 'ver', 'línea',
    'linea', 'código', 'codigo', 'archivo', 'página', 'pagina',
    'navegador', 'terminal', 'corriendo', 'mostrando', 'error', 'fallo',
}


def _detect_language(text: str) -> str:
    """Return 'en' or 'es' based on simple word/character heuristics."""
    if any(c in _ES_CHARS for c in text):
        return "es"
    words = {w.strip("'.,!?") for w in text.lower().split()}
    return "en" if words & _EN_WORDS else "es"


def _needs_screen_context(text: str) -> bool:
    """Return True when the message seems to reference the screen."""
    words = {w.strip("'.,!?") for w in text.lower().split()}
    return bool(words & _SCREEN_KEYWORDS)


# ── Transcript cleanup ────────────────────────────────────────────────────────

_FILLER_WORDS = {"uh", "um", "like", "maybe", "actually", "yeah", "so", "well", "hmm"}


def _clean_transcript(text: str) -> str:
    """Remove filler words and bias toward last intent for self-corrections.

    Example: "open github uh maybe actually yeah open repo" → "open repo"
    """
    words = text.lower().split()
    filtered = [w for w in words if w not in _FILLER_WORDS]
    cleaned = " ".join(filtered)

    # Last-intent bias: humans correct themselves at the end.
    # "open github open repo" → "open repo"
    for keyword in ("open", "search", "find", "go to"):
        if cleaned.count(keyword) > 1:
            parts = cleaned.split(keyword)
            cleaned = keyword + parts[-1].strip()
            break

    return cleaned.strip()


# ── Fast router (deterministic command execution, 0ms latency) ────────────────

_KNOWN_SITES = {
    "github": "https://github.com",
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    "twitter": "https://twitter.com",
    "dribbble": "https://dribbble.com",
    "notion": "https://notion.so",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "figma": "https://figma.com",
    "linkedin": "https://linkedin.com",
    "reddit": "https://reddit.com",
    "spotify": "https://open.spotify.com",
    "gmail": "https://mail.google.com",
    "docs": "https://docs.google.com",
    "google docs": "https://docs.google.com",
    "google drive": "https://drive.google.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
}


def _fast_route(text: str) -> Optional[dict]:
    """Deterministic routing for high-confidence commands.

    Returns a dict with tool name + args for immediate execution,
    or None to fall through to Claude.
    """
    t = text.lower().strip().rstrip(".")

    # Ambiguous — let Claude handle
    if "my " in t or "workspace" in t:
        return None

    # "open {site}" → direct navigation
    if t.startswith("open "):
        target = t[5:].strip()
        if target in _KNOWN_SITES:
            return {"tool": "browse_web", "args": {"url": _KNOWN_SITES[target]}}
        # Heuristic fallback for unknown single-word sites
        clean = target.replace(" ", "")
        if clean.isalpha() and len(clean) < 20:
            return {"tool": "browse_web", "args": {"url": f"https://{clean}.com"}}
        return None

    # "search X on Y" → direct search
    if t.startswith("search ") and " on " in t:
        parts = t[7:].split(" on ", 1)
        query = parts[0].strip()
        site = parts[1].strip()
        if site in _KNOWN_SITES:
            base = _KNOWN_SITES[site]
            url = f"{base}/search?q={query.replace(' ', '+')}"
            return {"tool": "browse_web", "args": {"url": url}}

    # "go to {site}" → direct navigation
    if t.startswith("go to "):
        target = t[6:].strip()
        if target in _KNOWN_SITES:
            return {"tool": "browse_web", "args": {"url": _KNOWN_SITES[target]}}

    return None  # everything else → Claude


class WebSocketManager:
    """
    Maneja conexiones WebSocket y loops continuos del sistema.

    Responsabilidades:
    1. Aceptar y mantener conexiones WebSocket con auto-cleanup
    2. Ejecutar loops continuos (wake word, screen monitoring)
    3. Enviar eventos al frontend
    4. Orquestar el pipeline de voz completo por sesión

    Attributes:
        active_connections: session_id → WebSocket
        assistant_states: session_id → AssistantState
        running_loops: session_id → bool
        voice_use_cases: session_id → ProcessVoiceCommandUseCase (creado dinámicamente)
    """

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.assistant_states: Dict[str, AssistantState] = {}
        self.running_loops: Dict[str, bool] = {}
        # Última descripción de pantalla por sesión (actualizada por Claude Vision)
        self.screen_contexts: Dict[str, Optional[str]] = {}
        # Fábrica de use cases de voz — se inyecta desde main.py
        self._voice_use_case_factory = None
        # Ejecutor de herramientas (Playwright, terminal, archivos, Notion)
        self._tool_executor = None
        # Guard: evita pipelines de voz concurrentes por sesión
        self._voice_busy: Dict[str, bool] = {}
        # Whisper service para detección de wake word cuando OpenWakeWord no está disponible
        self._whisper_service = None
        # Buffer PCM por sesión para detección de wake word con Whisper
        self._wake_word_pcm_buffers: Dict[str, bytearray] = {}
        # Guard: evita Whisper calls concurrentes por sesión
        self._wake_word_checking: Dict[str, bool] = {}
        logger.info("WebSocket Manager initialized")

    @staticmethod
    def _decode_b64(data: str, context: str = "") -> Optional[bytes]:
        """Decodifica base64 a bytes; retorna None y loguea si falla."""
        try:
            return base64.b64decode(data)
        except Exception as e:
            logger.error(f"Cannot decode base64 {context}: {e}")
            return None

    @staticmethod
    def _pcm16_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
        """Envuelve PCM Int16 raw en un contenedor WAV para Whisper."""
        import struct
        num_channels = 1
        bits_per_sample = 16
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = len(pcm_bytes)
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF', 36 + data_size, b'WAVE',
            b'fmt ', 16, 1, num_channels, sample_rate,
            byte_rate, block_align, bits_per_sample,
            b'data', data_size,
        )
        return header + pcm_bytes

    @staticmethod
    def _make_event(event_type: str, data: Optional[dict] = None) -> dict:
        """
        Construye el sobre estándar de evento WebSocket.

        Centraliza la construcción del envelope {"type": ..., "data": ...}
        para que todos los call sites tengan estructura consistente.

        Args:
            event_type: Nombre del evento (EventType.XXX.value o string literal)
            data: Payload opcional del evento

        Returns:
            Diccionario envelope listo para pasar a send_event()
        """
        event: dict = {"type": event_type}
        if data is not None:
            event["data"] = data
        return event

    def set_voice_use_case_factory(self, factory):
        """
        Inyecta la fábrica de ProcessVoiceCommandUseCase.

        La fábrica recibe un AssistantState y retorna un use case
        configurado con los servicios correctos.

        Args:
            factory: Callable[[AssistantState], ProcessVoiceCommandUseCase]
        """
        self._voice_use_case_factory = factory
        logger.info("✅ Voice use case factory registered in WebSocketManager")

    def set_whisper_service(self, whisper_service) -> None:
        """Inyecta el servicio FasterWhisper para detección de wake word como fallback."""
        self._whisper_service = whisper_service
        logger.info("✅ Whisper service registered for wake word detection")

    def set_tool_executor(self, tool_executor) -> None:
        """Inyecta el ToolExecutor (Playwright, terminal, archivos, Notion)."""
        self._tool_executor = tool_executor
        logger.info("✅ ToolExecutor registered in WebSocketManager")

    def update_screen_context(self, session_id: str, description: Optional[str]) -> None:
        """Almacena la última descripción visual de pantalla para la sesión."""
        if session_id in self.screen_contexts or session_id in self.active_connections:
            self.screen_contexts[session_id] = description

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Acepta una conexión WebSocket y arranca los loops continuos.

        Args:
            websocket: Conexión WebSocket de FastAPI
            session_id: ID único de la sesión
        """
        try:
            await websocket.accept()

            self.active_connections[session_id] = websocket
            self.assistant_states[session_id] = AssistantState(
                session_id=session_id,
                mode=AssistantMode.INACTIVE,
                language="es",
            )
            self.running_loops[session_id] = True
            self.screen_contexts[session_id] = None

            logger.info(f"[{session_id}] ✅ WebSocket connected")
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

            # Arranca loop principal en background
            asyncio.create_task(self.handle_messages(session_id))
            # Arranca loop de captura de pantalla en background
            asyncio.create_task(self._screen_capture_loop(session_id))

            logger.info(f"[{session_id}] Continuous loops started")

        except Exception as e:
            logger.error(
                f"Error connecting WebSocket for {session_id}: {e}", exc_info=True
            )
            sentry_capture(e, session_id=session_id, context="connect")
            raise

    def disconnect(self, session_id: str) -> None:
        """Cierra la conexión y detiene los loops."""
        self.running_loops[session_id] = False
        self.active_connections.pop(session_id, None)
        self.assistant_states.pop(session_id, None)
        self.running_loops.pop(session_id, None)
        self.screen_contexts.pop(session_id, None)
        # Limpiar contexto de Playwright para esta sesión
        if self._tool_executor and hasattr(self._tool_executor, '_browser') and self._tool_executor._browser:
            try:
                self._tool_executor._browser.close_session(session_id)
            except Exception as e:
                logger.warning(f"[{session_id}] Playwright cleanup error: {e}")
        logger.info(f"[{session_id}] WebSocket disconnected")

    # ── Sending ───────────────────────────────────────────────────────────────

    async def send_event(self, session_id: str, event: dict) -> None:
        """Envía un evento JSON al frontend."""
        ws = self.active_connections.get(session_id)
        if not ws:
            logger.warning(f"[{session_id}] Cannot send — not connected")
            return
        try:
            await ws.send_json(event)
            logger.debug(f"[{session_id}] → {event.get('type', 'unknown')}")
        except Exception as e:
            logger.error(f"[{session_id}] Send error: {e}", exc_info=True)
            self.disconnect(session_id)

    async def broadcast_event(self, event: dict) -> None:
        """Envía un evento a todas las conexiones activas."""
        for session_id in list(self.active_connections.keys()):
            await self.send_event(session_id, event)

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def handle_messages(self, session_id: str) -> None:
        """
        Loop principal que escucha todos los mensajes del frontend.

        Procesa:
        - audio_chunk    → wake word detection via OpenWakeWord
        - audio_command  → STT + AI + TTS pipeline
        - chat_message   → texto directo al AI
        - screen_capture → OCR + análisis de pantalla
        - ping           → keepalive
        """
        logger.info(f"[{session_id}] Message handler loop started")

        # OpenWakeWord adapter para esta sesión (lazy init — carga modelos ONNX locales)
        oww = None
        try:
            from src.adapters.voice.open_wake_word_adapter import OpenWakeWordAdapter
            loop = asyncio.get_running_loop()
            oww = await loop.run_in_executor(None, OpenWakeWordAdapter)
            logger.info(f"[{session_id}] OpenWakeWord detection active")
        except Exception as oww_err:
            logger.warning(
                f"[{session_id}] Could not init OpenWakeWord: {oww_err}. "
                "Wake word detection via Whisper fallback or manual trigger only."
            )

        while self.running_loops.get(session_id, False):
            try:
                ws = self.active_connections.get(session_id)
                if not ws:
                    break

                try:
                    data = await asyncio.wait_for(ws.receive_json(), timeout=1.0)
                    msg_type = data.get("type", "")
                    logger.debug(f"[{session_id}] ← {msg_type}")

                    # ── ping / keepalive ──────────────────────────────────────
                    if msg_type == "ping":
                        await self.send_event(session_id, self._make_event("pong"))

                    # ── audio_chunk: wake word detection ─────────────────────
                    elif msg_type == "audio_chunk":
                        await self._handle_audio_chunk(session_id, data, oww)

                    # ── wake_word_trigger: browser SpeechRecognition detected wake word ──
                    elif msg_type == "wake_word_trigger":
                        state = self.assistant_states.get(session_id)
                        wake_word = (data.get("data", {}) or {}).get("wake_word", "hey atlas")
                        if state and state.mode not in (
                            AssistantMode.LISTENING,
                        ):
                            state.start_listening()
                            await self.send_event(
                                session_id,
                                self._make_event(
                                    EventType.WAKE_WORD_DETECTED.value,
                                    {"wake_word": wake_word, "timestamp": datetime.now().isoformat()},
                                ),
                            )
                            logger.info(f"[{session_id}] 🗣️  Wake word via browser SpeechRecognition: '{wake_word}'")

                    # ── audio_command: full speech → STT → AI → TTS ──────────
                    elif msg_type == "audio_command":
                        await self._handle_audio_command(session_id, data)

                    # ── chat_message: text input ──────────────────────────────
                    elif msg_type == "chat_message":
                        message = data.get("data", {}).get("message", "")
                        if message:
                            logger.info(f"[{session_id}] Chat: '{message[:60]}'")
                            # Auto-detect language from user's text
                            detected_lang = _detect_language(message)
                            state = self.assistant_states.get(session_id)
                            if state:
                                state.language = detected_lang
                            # Only inject screen context when message references the screen
                            screen_ctx = (
                                self.screen_contexts.get(session_id)
                                if _needs_screen_context(message)
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

                    # ── screen_capture: OCR frame ─────────────────────────────
                    elif msg_type == "screen_capture":
                        # Frontend: send('screen_capture', {data: b64, timestamp, format})
                        # WS envelope: {"type": "screen_capture", "data": {"data": b64, ...}}
                        inner_sc = data.get("data", {}) or {}
                        screenshot_data = inner_sc.get("data", "")
                        if screenshot_data:
                            await event_bus.emit(
                                EventType.SCREEN_CONTEXT_UPDATED.value,
                                {
                                    "session_id": session_id,
                                    "screenshot_data": screenshot_data,
                                    "timestamp": inner_sc.get(
                                        "timestamp", datetime.now().timestamp() * 1000
                                    ),
                                    "format": inner_sc.get("format", "jpeg"),
                                },
                            )

                    # ── set_language ──────────────────────────────────────────
                    elif msg_type == "set_language":
                        lang = data.get("data", {}).get("language", "es")
                        state = self.assistant_states.get(session_id)
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
                sentry_capture(e, session_id=session_id, context="handle_messages")
                await asyncio.sleep(1)

        # Cleanup OpenWakeWord (no explicit stop needed — GC handles ONNX sessions)
        oww = None

        logger.info(f"[{session_id}] Message handler loop stopped")

    async def _handle_audio_chunk(
        self,
        session_id: str,
        data: dict,
        oww,
    ) -> None:
        """
        Procesa un chunk de audio PCM para detección de wake word.

        El frontend envía chunks de ~1280 samples (Int16, 16kHz, mono)
        codificados en base64. OpenWakeWord procesa cada chunk de 2560 bytes
        y detecta si se pronunció la wake word.

        Args:
            session_id: ID de la sesión
            data: Mensaje recibido con campo 'audio' (base64 PCM)
            oww: Instancia de OpenWakeWordAdapter (puede ser None)
        """
        state = self.assistant_states.get(session_id)

        # Escuchar wake words en INACTIVE, ACTIVE y LISTENING.
        # LISTENING se incluye porque el frontend sigue enviando chunks PCM mientras
        # graba el comando del usuario; descartarlos rompería el pipeline de voz en
        # el segundo y subsiguientes intentos de wake word.
        if state and state.mode not in (
            AssistantMode.INACTIVE,
            AssistantMode.ACTIVE,
            AssistantMode.LISTENING,
        ):
            return

        # Obtener audio PCM — frontend envuelve en campo "data"
        inner_chunk = data.get("data", {}) or {}
        audio_b64 = inner_chunk.get("audio", "") or data.get("audio", "")
        if not audio_b64:
            return

        audio_bytes = self._decode_b64(audio_b64, "audio_chunk")
        if audio_bytes is None:
            return

        # Si OpenWakeWord no está disponible, acumular PCM para Whisper wake word
        if oww is None:
            if (
                self._whisper_service
                and state
                and state.mode in (AssistantMode.INACTIVE, AssistantMode.ACTIVE)
                and not self._wake_word_checking.get(session_id, False)
            ):
                buf = self._wake_word_pcm_buffers.setdefault(session_id, bytearray())
                buf.extend(audio_bytes)
                # 3 segundos a 16kHz, 16-bit mono = 96000 bytes
                if len(buf) >= 96000:
                    pcm_snapshot = bytes(buf[:96000])
                    # Slide: conservar último 1s de solapamiento
                    self._wake_word_pcm_buffers[session_id] = bytearray(buf[64000:])
                    asyncio.create_task(
                        self._check_whisper_wake_word(session_id, pcm_snapshot, state)
                    )
            return

        # Acumular en buffer interno por sesión y drenar en chunks de 1280 samples (2560 bytes)
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
                    # Limpiar buffer tras detección exitosa
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
        Transcribe un clip PCM de 3s con Whisper para detectar la wake word "atlas".

        Solo se llama cuando OpenWakeWord no está disponible.
        Filtra clips silenciosos por energía media antes de llamar a la API.
        """
        self._wake_word_checking[session_id] = True
        try:
            # Filtro de energía: evitar llamadas a Whisper en silencio
            import array as _array
            samples = _array.array('h', pcm_bytes)
            avg_abs = sum(abs(s) for s in samples) / max(len(samples), 1)
            if avg_abs < 1200:   # filtrar ruido ambiental más agresivamente (32767 = máximo)
                return

            wav_bytes = self._pcm16_to_wav(pcm_bytes)
            transcript = await self._whisper_service.transcribe_audio(wav_bytes, language="en")
            if not transcript:
                return

            text = transcript.lower().strip()
            logger.debug(f"[{session_id}] Wake word check: '{text[:60]}'")

            if 'atlas' in text:
                logger.info(f"[{session_id}] 🎙️  Wake word via Whisper: '{text}'")
                if state and state.mode not in (AssistantMode.LISTENING,):
                    state.start_listening()
                    await self.send_event(
                        session_id,
                        self._make_event(
                            EventType.WAKE_WORD_DETECTED.value,
                            {"wake_word": "atlas", "timestamp": datetime.now().isoformat()},
                        ),
                    )
                    # Limpiar buffer tras detección exitosa
                    self._wake_word_pcm_buffers.pop(session_id, None)

        except Exception as e:
            logger.debug(f"[{session_id}] Whisper wake word check failed: {e}")
        finally:
            self._wake_word_checking[session_id] = False

    async def _handle_audio_command(self, session_id: str, data: dict) -> None:
        """
        Recibe un audio_command, valida y dispara el pipeline en background.

        El pipeline (Whisper→Claude→ElevenLabs) se ejecuta como asyncio.Task
        separado para que el loop de recepción de WebSocket NUNCA se bloquee.
        Sin esto, una llamada de 10+ segundos impide procesar pings y la
        conexión cierra con 1011 keepalive timeout.
        """
        # Obtener audio — el frontend envuelve el payload en un campo "data"
        inner = data.get("data", {}) or {}
        audio_b64 = inner.get("audio", "") or data.get("audio", "")
        if not audio_b64:
            logger.warning(f"[{session_id}] audio_command with no audio data")
            return

        audio_bytes = self._decode_b64(audio_b64, f"audio_command [{session_id}]")
        if audio_bytes is None:
            return

        logger.info(f"[{session_id}] 🎤 audio_command: {len(audio_bytes)} bytes")

        if not self._voice_use_case_factory:
            logger.error(f"[{session_id}] No voice use case factory registered")
            return

        # Descartar si ya hay un pipeline corriendo para esta sesión
        if self._voice_busy.get(session_id):
            logger.warning(f"[{session_id}] Voice pipeline busy — dropping request")
            return

        # Ack inmediato al frontend (no espera al pipeline)
        await self.send_event(
            session_id,
            self._make_event("message_received", {"status": "processing"}),
        )

        # Lanzar pipeline en background — el receive loop queda libre
        asyncio.create_task(self._run_voice_pipeline(session_id, audio_bytes))

    async def _run_voice_pipeline(self, session_id: str, audio_bytes: bytes) -> None:
        """
        Ejecuta Whisper → Claude → ElevenLabs en background.

        Al no bloquear handle_messages, el WebSocket sigue respondiendo a pings
        durante todo el procesamiento, evitando desconexiones 1011.
        """
        self._voice_busy[session_id] = True
        state = self.assistant_states.get(session_id)
        try:
            # ── 1. Transcribir con Whisper (auto-detect idioma) ────────────
            pre_transcript = None
            if self._whisper_service:
                wav_bytes = self._pcm16_to_wav(audio_bytes)
                pre_transcript = await self._whisper_service.transcribe_audio(
                    wav_bytes, language=None  # auto-detect language
                )
                if not pre_transcript or len(pre_transcript.strip()) < 2:
                    logger.debug("[Voice] Empty transcription (silence/VAD filtered), ignoring")
                    if state:
                        state.reset_to_active()
                    return
                if pre_transcript and state:
                    state.language = _detect_language(pre_transcript)
                    logger.info(
                        f"[{session_id}] 🌐 Detected language: {state.language} "
                        f"from: '{pre_transcript[:60]}'"
                    )

            if not pre_transcript or not pre_transcript.strip():
                logger.warning(f"[{session_id}] Empty transcription — skipping pipeline")
                if state:
                    state.reset_to_active()
                return

            # ── 2. Limpiar transcripción (filler words + last-intent bias) ──
            transcription = _clean_transcript(pre_transcript)
            normalized = _strip_wake_prefix(transcription.lower().strip())
            logger.info(f"[{session_id}] 📝 Cleaned transcript: '{transcription}'")

            # ── 3. UI command intercept (ANTES de Claude) ──────────────────
            if any(t in normalized for t in _DISMISS_TRIGGERS):
                logger.info(f"[{session_id}] 🚪 UI command: dismiss")
                await self.send_event(
                    session_id,
                    {"type": "ui_command", "data": {"action": "dismiss"}},
                )
                if state:
                    state.reset_to_active()
                return

            if any(t in normalized for t in _CHAT_OPEN_TRIGGERS):
                logger.info(f"[{session_id}] 💬 UI command: open_chat")
                await self.send_event(
                    session_id,
                    {"type": "ui_command", "data": {"action": "open_chat"}},
                )
                if state:
                    state.reset_to_active()
                return

            # ── 4. Fast router: deterministic commands (0ms, no LLM) ───────
            route = _fast_route(normalized)
            if route and self._tool_executor:
                logger.info(
                    f"[{session_id}] ⚡ Fast route: {route['tool']}({route['args']})"
                )
                try:
                    tool_result = await self._tool_executor.execute(
                        route["tool"], route["args"]
                    )
                    response_text = f"Done — opened that for you."
                    logger.info(f"[{session_id}] ✅ Fast route executed: {tool_result[:80]}")
                except Exception as tool_err:
                    logger.error(f"[{session_id}] Fast route error: {tool_err}")
                    response_text = f"I tried to open that but hit an error: {tool_err}"

                # Enviar respuesta del fast route
                await self.send_event(
                    session_id,
                    self._make_event(
                        EventType.AI_RESPONSE_GENERATED.value,
                        {
                            "message": response_text,
                            "transcription": transcription,
                            "timestamp": datetime.now().isoformat(),
                        },
                    ),
                )
                # TTS para confirmación breve
                await self.send_event(
                    session_id,
                    self._make_event(
                        "tts_audio",
                        {
                            "audio_b64": None,
                            "format": "mp3",
                            "text": response_text,
                        },
                    ),
                )
                logger.info(f"[{session_id}] ⚡ Fast route complete")

            else:
                # ── 5. Claude path: full voice pipeline ────────────────────
                voice_use_case = self._voice_use_case_factory(state)
                result = await voice_use_case.execute(
                    audio_data=audio_bytes,
                    conversation_history=None,
                    screen_context=self.screen_contexts.get(session_id),
                    transcription=transcription,  # cleaned transcript, skip Whisper
                )

                if result["success"]:
                    await self.send_event(
                        session_id,
                        self._make_event(
                            EventType.AI_RESPONSE_GENERATED.value,
                            {
                                "message": result["response"],
                                "transcription": transcription,
                                "timestamp": datetime.now().isoformat(),
                            },
                        ),
                    )

                    await self.send_event(
                        session_id,
                        self._make_event(
                            "tts_audio",
                            {
                                "audio_b64": result.get("audio_response_b64"),
                                "format": "mp3",
                                "text": result["response"],
                            },
                        ),
                    )
                    if result.get("has_audio"):
                        logger.info(f"[{session_id}] 🔊 TTS audio sent")
                    else:
                        logger.info(f"[{session_id}] 🔊 TTS text sent (fallback)")

                    # ── Persistir intercambio de voz en la BD ─────────────────────
                    try:
                        async with AsyncSessionFactory() as session:
                            async with session.begin():
                                repo = SQLiteConversationRepository(session)
                                conversation = await repo.get_active_conversation_by_session(session_id)
                                if not conversation:
                                    lang = state.language if state else "es"
                                    conversation = Conversation(session_id=session_id, language=lang)
                                    await repo.create_conversation(conversation)
                                # Guardar transcripción del usuario
                                user_msg = Message(
                                    conversation_id=conversation.id,
                                    role=MessageRole.USER,
                                    content=transcription,
                                )
                                await repo.add_message(user_msg)
                                # Guardar respuesta del asistente
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
                        logger.error(f"[{session_id}] Voice DB persistence error: {db_err}", exc_info=True)
                        # No fallar el pipeline por error de BD — TTS ya fue enviado

                else:
                    await self.send_event(
                        session_id,
                        self._make_event(
                            EventType.AI_RESPONSE_GENERATED.value,
                            {
                                "message": result["response"],
                                "error": True,
                                "error_detail": result.get("error"),
                            },
                        ),
                    )

            # Volver a ACTIVE y notificar al frontend
            if state:
                old_mode = state.mode
                state.finish_speaking()
                await self.send_event(
                    session_id,
                    self._make_event(
                        EventType.STATE_CHANGED.value,
                        {
                            "old_mode": old_mode.value,
                            "new_mode": state.mode.value,
                            "state": state.to_dict(),
                        },
                    ),
                )

        except Exception as e:
            logger.error(f"[{session_id}] Voice pipeline error: {e}", exc_info=True)
            sentry_capture(e, session_id=session_id, context="voice_pipeline")
            if state:
                old_mode = state.mode
                state.reset_to_active()
                await self.send_event(
                    session_id,
                    self._make_event(
                        EventType.STATE_CHANGED.value,
                        {
                            "old_mode": old_mode.value,
                            "new_mode": state.mode.value,
                            "state": state.to_dict(),
                        },
                    ),
                )
        finally:
            self._voice_busy[session_id] = False
            # Ensure state always resets to ACTIVE after voice pipeline,
            # even if finish_speaking() guard failed earlier.
            if state and state.mode != AssistantMode.ACTIVE:
                state.reset_to_active()
                logger.debug(f"[{session_id}] Force-reset state to ACTIVE after voice pipeline")

    # ── Screen capture loop ───────────────────────────────────────────────────

    async def _screen_capture_loop(self, session_id: str) -> None:
        """
        Loop continuo que captura la pantalla primaria cada 3 segundos usando mss
        y la envía al frontend como evento screen_capture.

        Reemplaza el desktopCapturer de Electron — no requiere permisos de pantalla.
        """
        mss_adapter = MSSCaptureAdapter()
        logger.info(f"[{session_id}] MSS screen capture loop started")

        while self.running_loops.get(session_id, False):
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
                logger.debug(f"[{session_id}] Screen capture error (non-fatal): {e}")

            await asyncio.sleep(3)

        logger.info(f"[{session_id}] MSS screen capture loop stopped")

    # ── State management ──────────────────────────────────────────────────────

    def get_state(self, session_id: str) -> Optional[AssistantState]:
        """Obtiene el estado del asistente para una sesión."""
        return self.assistant_states.get(session_id)

    def update_state(self, session_id: str, new_mode: AssistantMode) -> None:
        """Actualiza el modo del asistente y notifica al frontend."""
        state = self.assistant_states.get(session_id)
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


# Singleton global
ws_manager = WebSocketManager()
