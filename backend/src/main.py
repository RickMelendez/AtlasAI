"""
Atlas AI Backend - FastAPI Application.

Main entry point for Atlas AI backend. Configures FastAPI, CORS,
event handlers, and application lifecycle using AppContainer for
proper dependency injection.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.infrastructure.api.routes import websocket, settings as settings_routes
from src.infrastructure.config.settings import get_settings
from src.infrastructure.container import AppContainer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

# Initialize Sentry BEFORE app creation
from src.infrastructure.monitoring.sentry import init_sentry as _init_sentry

_settings = get_settings()
_init_sentry(
    dsn=_settings.sentry_dsn,
    environment="production" if not _settings.debug else "development",
    release="atlas-ai@0.1.0",
)

# Global container instance
container: Optional[AppContainer] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Handles initialization and cleanup of resources when the app
    starts and shuts down. Uses AppContainer for proper dependency injection.
    """
    global container

    # Startup
    logger.info("🚀 Atlas AI Backend starting up...")
    container = AppContainer()
    await container.initialize()

    # Register event handlers
    from src.infrastructure.events.event_bus import event_bus
    from src.infrastructure.events.event_types import EventType
    from src.infrastructure.websocket.manager import ws_manager
    from src.domain.entities.conversation import Conversation
    from src.domain.entities.message import Message, MessageRole
    from src.infrastructure.database import AsyncSessionFactory
    from src.infrastructure.database.repositories.conversation_repository import (
        SQLiteConversationRepository,
    )

    # Handler for text chat messages
    async def handle_user_message(data: dict):
        """Process text chat messages from user."""
        import time as _time_mod
        session_id = data.get("session_id")
        message = data.get("message")
        screen_context = data.get("screen_context")

        if not session_id or not message:
            logger.warning("Invalid user message data received")
            return

        state = ws_manager.get_state(session_id)
        if not state:
            logger.warning(f"No state found for session {session_id}")
            return

        # ── "Forget everything" command ─────────────────────────────────────
        if message.strip().lower() in ("forget everything", "forget it all", "clear memory"):
            try:
                from src.infrastructure.database.repositories.memory_repository import (
                    MemoryRepository,
                )
                async with AsyncSessionFactory() as db_session:
                    async with db_session.begin():
                        mem_repo = MemoryRepository(db_session)
                        count = await mem_repo.delete_all_memories()
                logger.info(f"[{session_id}] Cleared {count} memories on user request")
                await ws_manager.send_event(
                    session_id,
                    {
                        "type": EventType.AI_RESPONSE_GENERATED.value,
                        "data": {
                            "message": f"Done — I've forgotten everything ({count} memories cleared).",
                            "timestamp": _time_mod.strftime("%Y-%m-%dT%H:%M:%SZ", _time_mod.gmtime()),
                        },
                    },
                )
            except Exception as forget_err:
                logger.error(f"[{session_id}] Error clearing memories: {forget_err}")
            return

        # Load conversation history from database (single session)
        conversation_history = None
        try:
            async with AsyncSessionFactory() as session:
                async with session.begin():
                    repo = SQLiteConversationRepository(session)
                    conversation = (
                        await repo.get_active_conversation_by_session(session_id)
                    )
                    if conversation:
                        db_messages = await repo.get_last_n_messages(
                            conversation.id, n=10
                        )
                        conversation_history = [
                            msg.to_claude_format() for msg in db_messages
                        ]
                        logger.info(
                            f"[{session_id}] Loaded {len(conversation_history)} messages from DB"
                        )
        except Exception as db_err:
            logger.error(f"[{session_id}] DB history load error: {db_err}", exc_info=True)

        # ── Streaming response (token-by-token, like ChatGPT) ────────────────
        # Accumulate full text while streaming so we can persist it afterward
        full_response = ""
        try:
            async for chunk in container.claude.generate_streaming_response(
                user_message=message,
                conversation_history=conversation_history,
                screen_context=screen_context,
                language=state.language if hasattr(state, "language") else "en",
            ):
                full_response += chunk
                await ws_manager.send_event(
                    session_id,
                    {
                        "type": "ai_response_chunk",
                        "data": {"chunk": chunk, "done": False},
                    },
                )
            # Signal end of stream
            await ws_manager.send_event(
                session_id,
                {
                    "type": "ai_response_chunk",
                    "data": {"chunk": "", "done": True},
                },
            )
        except Exception as stream_err:
            logger.error(f"[{session_id}] Streaming error: {stream_err}", exc_info=True)
            # Fall back to non-streaming if streaming fails
            try:
                result = await container.chat_use_case.execute(
                    message, state,
                    screen_context=screen_context,
                    conversation_history=conversation_history,
                )
                full_response = result.get("response", "")
                await ws_manager.send_event(
                    session_id,
                    {
                        "type": EventType.AI_RESPONSE_GENERATED.value,
                        "data": {
                            "message": full_response,
                            "timestamp": result.get("timestamp"),
                            "error": result.get("error", False),
                        },
                    },
                )
            except Exception as fallback_err:
                logger.error(f"[{session_id}] Fallback response error: {fallback_err}")
            return

        # Persist exchange to database
        if full_response:
            try:
                async with AsyncSessionFactory() as session:
                    async with session.begin():
                        repo = SQLiteConversationRepository(session)
                        conv = await repo.get_active_conversation_by_session(session_id)
                        if not conv:
                            conv = Conversation(session_id=session_id, language="en")
                            await repo.create_conversation(conv)
                        user_msg = Message(
                            conversation_id=conv.id,
                            role=MessageRole.USER,
                            content=message,
                        )
                        await repo.add_message(user_msg)
                        assistant_msg = Message(
                            conversation_id=conv.id,
                            role=MessageRole.ASSISTANT,
                            content=full_response,
                        )
                        await repo.add_message(assistant_msg)
                        conv.touch()
                        await repo.update_conversation(conv)
                        logger.info(f"[{session_id}] Persisted exchange to DB (conv={conv.id})")
            except Exception as db_err:
                logger.error(
                    f"[{session_id}] DB persistence error: {db_err}", exc_info=True
                )

    # Register handler
    event_bus.on(EventType.USER_MESSAGE_RECEIVED.value, handle_user_message)
    logger.info("✅ Chat message handler registered")

    # Handler for screen context (proactive help detection)
    import base64
    import time as _time

    _last_vision_call: dict = {"ts": 0.0}
    _VISION_DEBOUNCE_SECS = 10.0
    _PROACTIVE_LAST_TRIGGER: dict = {"ts": 0.0}
    _PROACTIVE_COOLDOWN_SECS = 60.0

    async def handle_screen_context_updated(data: dict):
        """Process screen frames with Claude Vision and detect errors."""
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
            await container.screen_service.extract_text_from_image(screenshot_bytes)
            if hasattr(container.screen_service, "last_screen_description"):
                description = container.screen_service.last_screen_description
                ws_manager.update_screen_context(session_id, description)

                # Proactive error detection with cooldown
                if description and any(
                    indicator in description.lower()
                    for indicator in ["error", "exception", "traceback", "warning"]
                ):
                    state = ws_manager.get_state(session_id)
                    now_proactive = _time.monotonic()
                    if (
                        state
                        and state.mode.value == "active"
                        and now_proactive - _PROACTIVE_LAST_TRIGGER["ts"]
                        > _PROACTIVE_COOLDOWN_SECS
                    ):
                        _PROACTIVE_LAST_TRIGGER["ts"] = now_proactive
                        await event_bus.emit(
                            EventType.PROACTIVE_HELP_TRIGGERED.value,
                            {"session_id": session_id, "description": description},
                        )
                        logger.info(f"[{session_id}] Proactive help triggered")
        except Exception as e:
            logger.error(f"[{session_id}] Screen vision error: {e}")

    event_bus.on(EventType.SCREEN_CONTEXT_UPDATED.value, handle_screen_context_updated)
    logger.info("✅ Screen capture handler registered")

    # Handler for proactive help trigger
    async def handle_proactive_help_triggered(data: dict):
        """Generate proactive help and send to frontend."""
        session_id = data.get("session_id")
        description = data.get("description")

        if not session_id or not description:
            return

        try:
            help_text = await container.claude.generate_proactive_help(description)
            if help_text:
                await ws_manager.send_event(
                    session_id,
                    {
                        "type": EventType.AI_RESPONSE_GENERATED.value,
                        "data": {
                            "message": help_text,
                            "proactive": True,
                        },
                    },
                )
                # Generate TTS audio if available
                if container.tts:
                    try:
                        audio_b64 = await container.tts.synthesize(help_text)
                        await ws_manager.send_event(
                            session_id,
                            {
                                "type": "tts_audio",
                                "data": {
                                    "audio_b64": audio_b64,
                                    "format": "mp3",
                                },
                            },
                        )
                    except Exception as tts_err:
                        logger.warning(f"[{session_id}] TTS error for proactive help: {tts_err}")
        except Exception as e:
            logger.error(f"[{session_id}] Proactive help error: {e}")

    event_bus.on(
        EventType.PROACTIVE_HELP_TRIGGERED.value, handle_proactive_help_triggered
    )
    logger.info("✅ Proactive help handler registered")

    # Inject container into WebSocket manager
    if container.whisper:
        ws_manager.set_voice_use_case_factory(container.make_voice_use_case)
        ws_manager.set_whisper_service(container.whisper)
        logger.info("✅ Voice pipeline registered")
    else:
        logger.warning("⚠️  Voice pipeline not registered (FasterWhisper unavailable)")

    ws_manager.set_tool_executor(container.tool_executor)
    logger.info("✅ Tool executor registered")

    yield

    # Shutdown
    logger.info("🛑 Atlas AI Backend shutting down...")
    await container.shutdown()


# Create FastAPI app
app = FastAPI(
    title="Atlas AI Visual Companion API",
    description=(
        "Backend API for Atlas AI - An AI visual assistant that acts as "
        "a tech-savvy companion."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS - allow localhost + any production origins set via env
_base_origins = [
    "http://localhost:8000",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
_extra = os.environ.get("CORS_ORIGINS", "")
_allowed_origins = _base_origins + [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
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
    """Root endpoint with API information."""
    return {
        "message": "Atlas AI Backend API",
        "description": "Event-driven system with continuous WebSocket",
        "version": "0.1.0",
        "endpoints": {
            "health": "/health",
            "websocket": "/api/ws",
            "settings": "/api/settings",
            "memories": "/api/memories",
            "docs": "/docs",
        },
    }


# Memory endpoints
@app.get("/api/memories")
async def get_memories():
    """Get all stored memories."""
    try:
        from src.infrastructure.database import AsyncSessionFactory
        from src.infrastructure.database.repositories.memory_repository import (
            MemoryRepository,
        )

        async with AsyncSessionFactory() as session:
            repo = MemoryRepository(session)
            memories = await repo.get_all_memories()
            return {
                "memories": [
                    {"id": m.id, "content": m.content, "source": m.source}
                    for m in memories
                ]
            }
    except Exception as e:
        logger.error(f"Failed to get memories: {e}")
        return {"memories": []}


@app.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: int):
    """Delete a single memory by ID."""
    try:
        from src.infrastructure.database import AsyncSessionFactory
        from src.infrastructure.database.repositories.memory_repository import (
            MemoryRepository,
        )

        async with AsyncSessionFactory() as session:
            async with session.begin():
                repo = MemoryRepository(session)
                deleted = await repo.delete_memory(memory_id)
        if deleted:
            return {"deleted": True, "id": memory_id}
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Memory not found")
    except Exception as e:
        logger.error(f"Failed to delete memory {memory_id}: {e}")
        raise


@app.delete("/api/memories")
async def delete_all_memories():
    """Delete all memories."""
    try:
        from src.infrastructure.database import AsyncSessionFactory
        from src.infrastructure.database.repositories.memory_repository import (
            MemoryRepository,
        )

        async with AsyncSessionFactory() as session:
            async with session.begin():
                repo = MemoryRepository(session)
                count = await repo.delete_all_memories()
                logger.info(f"Deleted {count} memories")
        return {"deleted": count}
    except Exception as e:
        logger.error(f"Failed to delete memories: {e}")
        raise


# Register routers
app.include_router(websocket.router, prefix="/api", tags=["websocket"])
app.include_router(settings_routes.router, prefix="/api", tags=["settings"])


# Entry point for uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
