"""
Atlas AI Backend - FastAPI Application.

Este es el punto de entrada principal del backend de Atlas AI.
Configura FastAPI, CORS, y registra todos los routers.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.infrastructure.api.routes import websocket
from src.infrastructure.config.settings import get_settings

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

# ── Sentry: initialise BEFORE the app object is created ────────────────────
from src.infrastructure.monitoring.sentry import init_sentry as _init_sentry

_settings = get_settings()
_init_sentry(
    dsn=_settings.sentry_dsn,
    environment="production" if not _settings.debug else "development",
    release="atlas-ai@0.1.0",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager para FastAPI.

    Maneja la inicialización y limpieza de recursos
    al iniciar y cerrar la aplicación.
    """
    # Startup
    logger.info("🚀 Atlas AI Backend starting up...")

    # Inicializar base de datos (CREATE TABLE IF NOT EXISTS)
    from src.infrastructure.database import init_db

    await init_db()

    logger.info("✅ Event Bus initialized")
    logger.info("✅ WebSocket Manager initialized")

    # Registrar event handlers
    from src.adapters.ai.claude_adapter import ClaudeAdapter
    from src.application.use_cases.process_chat_message import \
        ProcessChatMessageUseCase
    from src.infrastructure.events.event_bus import event_bus
    from src.infrastructure.events.event_types import EventType
    from src.infrastructure.websocket.manager import ws_manager

    from src.domain.entities.conversation import Conversation
    from src.domain.entities.message import Message, MessageRole
    from src.infrastructure.database import AsyncSessionFactory
    from src.infrastructure.database.repositories.conversation_repository import \
        SQLiteConversationRepository

    # Inicializar servicios
    claude_service = ClaudeAdapter()
    chat_use_case = ProcessChatMessageUseCase(claude_service)

    # Handler para mensajes de chat
    async def handle_user_message(data: dict):
        """Procesa mensajes de chat del usuario."""
        session_id = data.get("session_id")
        message = data.get("message")
        screen_context = data.get("screen_context")  # ← inyectado por manager.py

        if not session_id or not message:
            logger.warning("Invalid user message data received")
            return

        # Obtener estado del asistente
        state = ws_manager.get_state(session_id)
        if not state:
            logger.warning(f"No state found for session {session_id}")
            return

        # Cargar historial de conversación desde la BD (per-session)
        conversation_history = None
        try:
            async with AsyncSessionFactory() as session:
                async with session.begin():
                    repo = SQLiteConversationRepository(session)
                    conversation = await repo.get_active_conversation_by_session(session_id)
                    if conversation:
                        db_messages = await repo.get_last_n_messages(conversation.id, n=10)
                        conversation_history = [msg.to_claude_format() for msg in db_messages]
                        logger.info(
                            f"[{session_id}] Loaded {len(conversation_history)} messages from DB"
                        )
        except Exception as db_err:
            logger.error(f"[{session_id}] DB history load error: {db_err}", exc_info=True)
            # No fallar el request por un error de BD — continuar sin historial

        # Procesar mensaje y generar respuesta (con contexto de pantalla e historial)
        result = await chat_use_case.execute(
            message, state, screen_context=screen_context, conversation_history=conversation_history
        )

        # Persistir intercambio en la BD
        if result and not result.get("error"):
            try:
                async with AsyncSessionFactory() as session:
                    async with session.begin():
                        repo = SQLiteConversationRepository(session)
                        # Obtener o crear conversación
                        conv = await repo.get_active_conversation_by_session(session_id)
                        if not conv:
                            conv = Conversation(session_id=session_id, language="es")
                            await repo.create_conversation(conv)
                        # Guardar mensaje del usuario
                        user_msg = Message(
                            conversation_id=conv.id,
                            role=MessageRole.USER,
                            content=message,
                        )
                        await repo.add_message(user_msg)
                        # Guardar respuesta del asistente
                        assistant_msg = Message(
                            conversation_id=conv.id,
                            role=MessageRole.ASSISTANT,
                            content=result["response"],
                        )
                        await repo.add_message(assistant_msg)
                        conv.touch()
                        await repo.update_conversation(conv)
                        logger.info(f"[{session_id}] Persisted exchange to DB (conv={conv.id})")
            except Exception as db_err:
                logger.error(f"[{session_id}] DB persistence error: {db_err}", exc_info=True)
                # No fallar el request por un error de BD — el usuario recibió su respuesta

        # Enviar screenshots de herramientas al frontend (si los hay)
        screenshots = getattr(claude_service, "_last_tool_screenshots", [])
        for b64 in screenshots:
            await ws_manager.send_event(
                session_id,
                {"type": "tool_screenshot", "data": {"image": b64}},
            )
        claude_service._last_tool_screenshots = []

        # Enviar respuesta al frontend
        await ws_manager.send_event(
            session_id,
            {
                "type": EventType.AI_RESPONSE_GENERATED.value,
                "data": {
                    "message": result["response"],
                    "timestamp": result["timestamp"],
                    "error": result.get("error", False),
                },
            },
        )

    # Registrar handler en el event bus
    event_bus.on(EventType.USER_MESSAGE_RECEIVED.value, handle_user_message)
    logger.info("✅ Chat message handler registered")

    # ── Voice pipeline: Whisper + ElevenLabs ──────────────────────────────────
    from src.adapters.voice.elevenlabs_adapter import ElevenLabsAdapter
    from src.adapters.voice.whisper_adapter import WhisperAdapter
    from src.application.use_cases.process_voice_command import \
        ProcessVoiceCommandUseCase
    from src.infrastructure.config.settings import get_settings

    settings = get_settings()

    # Inicializar servicios de voz (solo si las keys están disponibles)
    whisper_service = None
    tts_service = None

    if settings.openai_api_key:
        try:
            whisper_service = WhisperAdapter()
            logger.info("✅ WhisperAdapter initialized (STT ready)")
        except Exception as e:
            logger.warning(f"⚠️  WhisperAdapter not available: {e}")
    else:
        logger.warning("⚠️  OPENAI_API_KEY not set — voice STT disabled")

    if settings.elevenlabs_api_key:
        try:
            tts_service = ElevenLabsAdapter()
            logger.info("✅ ElevenLabsAdapter initialized (TTS ready)")
        except Exception as e:
            logger.warning(f"⚠️  ElevenLabsAdapter not available: {e}")
    else:
        logger.warning("⚠️  ELEVENLABS_API_KEY not set — TTS disabled (text-only mode)")

    # Fábrica de use cases de voz: crea una instancia con el estado de la sesión
    # tool_executor se inyecta después de crearse, pero usamos closure para referenciarlo
    _tool_executor_ref: dict = {"executor": None}

    def make_voice_use_case(assistant_state):
        return ProcessVoiceCommandUseCase(
            voice_service=whisper_service,
            ai_service=claude_service,
            assistant_state=assistant_state,
            tts_service=tts_service,
            tool_executor=_tool_executor_ref["executor"],
        )

    # Inyectar fábrica en el WebSocket manager
    if whisper_service:
        ws_manager.set_voice_use_case_factory(make_voice_use_case)
        ws_manager.set_whisper_service(whisper_service)
        logger.info("✅ Voice pipeline registered in WebSocketManager")
        logger.info("✅ Whisper registered for wake word detection")
    else:
        logger.warning("⚠️  Voice pipeline not registered (Whisper unavailable)")

    # ── Screen vision: Claude Haiku (reemplaza Tesseract) ─────────────────────
    import base64
    import time as _time

    from src.adapters.vision.claude_vision_adapter import ClaudeVisionAdapter

    screen_service = ClaudeVisionAdapter()

    # Debounce: solo llamar a Claude Haiku Vision cada 10 segundos como máximo.
    # Se eliminó analyze_screen_use_case (que hacía una segunda llamada a Claude Sonnet
    # por cada "error detectado") para reducir el consumo de API a ~6 llamadas/min.
    _last_vision_call: dict = {"ts": 0.0}
    _VISION_DEBOUNCE_SECS = 10.0

    async def handle_screen_context_updated(data: dict):
        """
        Procesa un frame de pantalla con Claude Haiku vision (solo descripción).

        Solo ejecuta la llamada de visión para obtener la descripción de pantalla
        que se inyecta en el contexto de Atlas. No hace análisis adicional de errores.
        """
        session_id = data.get("session_id")
        screenshot_b64 = data.get("screenshot_data", "")

        if not session_id or not screenshot_b64:
            return

        now = _time.monotonic()
        if now - _last_vision_call["ts"] < _VISION_DEBOUNCE_SECS:
            return
        _last_vision_call["ts"] = now

        try:
            screenshot_bytes = base64.b64decode(screenshot_b64)
            await screen_service.extract_text_from_image(screenshot_bytes)
            if hasattr(screen_service, "last_screen_description"):
                ws_manager.update_screen_context(
                    session_id, screen_service.last_screen_description
                )
        except Exception as e:
            logger.error(f"[{session_id}] Screen vision error: {e}")

    event_bus.on(EventType.SCREEN_CONTEXT_UPDATED.value, handle_screen_context_updated)
    logger.info("✅ Screen capture handler registered")

    # ── Tool use: Playwright + Notion + ToolExecutor ───────────────────────────
    from src.adapters.notion.notion_adapter import NotionAdapter
    from src.adapters.tools.tool_executor import ToolExecutor
    from src.adapters.web.playwright_adapter import PlaywrightAdapter

    playwright_adapter = PlaywrightAdapter()
    await playwright_adapter.start()

    notion_adapter = NotionAdapter()
    tool_executor = ToolExecutor(playwright_adapter, notion_adapter)

    ws_manager.set_tool_executor(tool_executor)
    # Actualizar la referencia del closure de la fábrica de voz
    _tool_executor_ref["executor"] = tool_executor
    # Inyectar en el chat use case también
    chat_use_case.tool_executor = tool_executor
    logger.info("✅ Tool executor registered (browser, terminal, files, Notion)")

    yield
    # Shutdown
    logger.info("🛑 Atlas AI Backend shutting down...")
    await playwright_adapter.stop()


# Crear aplicación FastAPI
app = FastAPI(
    title="Atlas AI Visual Companion API",
    description=(
        "Backend API para Atlas AI - Un asistente visual AI que funciona como "
        "un compañero tech-savvy siempre presente."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "*",  # En desarrollo permitir todos
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        Estado del servidor y versión
    """
    return {
        "status": "healthy",
        "service": "Atlas AI Backend",
        "version": "0.1.0",
        "architecture": "event-driven",
        "features": {
            "websocket": "enabled",
            "event_bus": "enabled",
            "continuous_loops": "enabled",
        },
    }


@app.get("/")
async def root():
    """
    Root endpoint con información del API.

    Returns:
        Mensaje de bienvenida y endpoints disponibles
    """
    return {
        "message": "Atlas AI Backend API",
        "description": "Sistema event-driven con WebSocket continuo",
        "version": "0.1.0",
        "endpoints": {
            "health": "/health",
            "websocket": "/api/ws",
            "websocket_health": "/api/ws/health",
            "docs": "/docs",
        },
    }


# Registrar routers
app.include_router(websocket.router, prefix="/api", tags=["websocket"])


# Punto de entrada para uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
