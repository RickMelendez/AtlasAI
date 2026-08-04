"""
Atlas AI Backend - FastAPI Application.

Main entry point for Atlas AI backend. Configures FastAPI, CORS,
event handlers, and application lifecycle using AppContainer for
proper dependency injection.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.infrastructure.api.routes import websocket, settings as settings_routes
from src.infrastructure.config.settings import get_settings
from src.infrastructure.container import AppContainer
from src.infrastructure.rate_limit import limiter

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
    from src.infrastructure.database.repositories.memory_repository import MemoryRepository

    # ── Wire the WebSocket manager to the container services ─────────────────
    # Sin esto, el pipeline de voz (audio_command) muere en silencio: los
    # setters existen pero nadie los llamaba (ver CODE-REVIEW.md, Critical).
    ws_manager.set_tool_executor(container.tool_executor)
    if container.whisper:
        ws_manager.set_whisper_service(container.whisper)
    if container.tts:
        ws_manager.set_tts_service(container.tts)
    ws_manager.set_voice_use_case_factory(
        lambda state, include_tts=True: container.make_voice_use_case(
            state, include_tts=include_tts
        )
    )
    logger.info("✅ WebSocket manager wired to container services")

    # ── Memory helpers ────────────────────────────────────────────────────────

    async def _load_memories() -> list[str]:
        """Load all stored memories as plain strings."""
        try:
            async with AsyncSessionFactory() as db_sess:
                repo = MemoryRepository(db_sess)
                mems = await repo.get_all_memories()
                return [m.content for m in mems]
        except Exception as e:
            logger.error(f"Failed to load memories: {e}")
            return []

    async def _auto_extract_memory(user_msg: str, assistant_msg: str) -> None:
        """
        Ask Claude to extract any new facts worth remembering from this exchange.
        Runs in the background after each conversation turn.
        """
        try:
            extraction_prompt = (
                "You are a memory extraction system. Given a conversation exchange, "
                "identify facts about the user that are worth remembering long-term "
                "(name, job, preferences, ongoing projects, personal details, tools they use, etc.).\n\n"
                "Rules:\n"
                "- Only extract facts that are NEW and specific to this user\n"
                "- Skip generic information or things already obvious\n"
                "- Respond with a JSON array of strings, each a single fact\n"
                "- If there is nothing worth remembering, respond with: []\n"
                "- Maximum 3 facts per exchange\n\n"
                "Example output: [\"User's name is Ricky\", \"User works with Python and FastAPI\", \"User prefers concise responses\"]\n"
                "Or if nothing new: []"
            )
            exchange = f"User: {user_msg}\n\nAssistant: {assistant_msg}"

            response = await container.claude.client.messages.create(
                model="claude-haiku-4-5-20251001",  # cheap + fast for extraction
                max_tokens=256,
                temperature=0.1,
                system=extraction_prompt,
                messages=[{"role": "user", "content": exchange}],
            )

            import json as _json
            text = response.content[0].text.strip() if response.content else "[]"
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            facts: list = _json.loads(text)

            if not isinstance(facts, list) or not facts:
                return

            async with AsyncSessionFactory() as db_sess:
                async with db_sess.begin():
                    mem_repo = MemoryRepository(db_sess)
                    for fact in facts[:3]:
                        if isinstance(fact, str) and fact.strip():
                            await mem_repo.add_memory(fact.strip(), source="auto")
            logger.info(f"[memory] Auto-extracted {len(facts)} fact(s)")
        except Exception as e:
            logger.warning(f"[memory] Auto-extraction failed (non-critical): {e}")

    # Handler for text chat messages
    async def handle_user_message(data: dict):
        """Process text chat messages from user."""
        import time as _time_mod
        session_id = data.get("session_id")
        message = data.get("message")
        screen_context = data.get("screen_context")
        image_data = data.get("image_data")

        if not session_id or not message:
            logger.warning("Invalid user message data received")
            return

        state = ws_manager.get_state(session_id)
        if not state:
            logger.warning(f"No state found for session {session_id}")
            return

        # ── "Remember that..." explicit memory command ───────────────────────
        msg_lower = message.strip().lower()
        _remember_prefixes = ("remember that ", "remember: ", "remember this: ", "nota: ", "anota que ")
        for _prefix in _remember_prefixes:
            if msg_lower.startswith(_prefix):
                fact = message.strip()[len(_prefix):].strip()
                if fact:
                    try:
                        async with AsyncSessionFactory() as db_session:
                            async with db_session.begin():
                                mem_repo = MemoryRepository(db_session)
                                await mem_repo.add_memory(fact, source="user")
                        logger.info(f"[{session_id}] User saved memory: '{fact[:60]}'")
                        await ws_manager.send_event(
                            session_id,
                            {
                                "type": EventType.AI_RESPONSE_GENERATED.value,
                                "data": {
                                    "message": f"Got it, I'll remember that: {fact}",
                                    "timestamp": _time_mod.strftime("%Y-%m-%dT%H:%M:%SZ", _time_mod.gmtime()),
                                },
                            },
                        )
                    except Exception as mem_err:
                        logger.error(f"[{session_id}] Error saving memory: {mem_err}")
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

        # Load long-term memories for this session
        memories = await _load_memories()

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
                            conversation.id, n=20
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
                image_data=image_data,
                memories=memories,
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
                    memories=memories,
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

            # Auto-extract memories in the background (non-blocking)
            import asyncio as _asyncio
            _asyncio.ensure_future(_auto_extract_memory(message, full_response))

    # Register handler
    event_bus.on(EventType.USER_MESSAGE_RECEIVED.value, handle_user_message)
    logger.info("✅ Chat message handler registered")

    # Handler: create conversation row immediately on WebSocket connect
    # so history is available from the very first message
    async def handle_websocket_connected(data: dict):
        session_id = data.get("session_id")
        if not session_id:
            return
        try:
            async with AsyncSessionFactory() as db_sess:
                async with db_sess.begin():
                    repo = SQLiteConversationRepository(db_sess)
                    existing = await repo.get_active_conversation_by_session(session_id)
                    if not existing:
                        conv = Conversation(session_id=session_id, language="en")
                        await repo.create_conversation(conv)
                        logger.info(f"[{session_id}] Conversation created on connect")
        except Exception as e:
            logger.error(f"[{session_id}] Error creating conversation on connect: {e}")

    event_bus.on(EventType.WEBSOCKET_CONNECTED.value, handle_websocket_connected)
    logger.info("✅ WebSocket connect handler registered")

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

        # Skip re-analysis if the event was already processed by screen_monitor_loop
        # (which sets source="server_loop" and has already called Claude Vision).
        if data.get("source") == "server_loop":
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
                        audio_bytes = await container.tts.synthesize_speech(help_text)
                        import base64 as _b64
                        audio_b64 = _b64.b64encode(audio_bytes).decode("utf-8")
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

    logger.info("🎮 Atlas AI Backend fully initialized — ready to accept connections")

    # ── Start local desktop loops (optional, disabled in cloud deployments) ────
    # Controlled by SCREEN_MONITOR_ENABLED and WAKE_WORD_LOCAL_ENABLED in .env
    _loop_stop_event = asyncio.Event()
    _loop_tasks = []

    from src.infrastructure.loops import run_screen_monitor_loop, run_wake_word_loop

    if get_settings().screen_monitor_enabled:
        logger.info("🖥️  Starting server-side screen monitor loop…")
        _loop_tasks.append(
            asyncio.create_task(
                run_screen_monitor_loop(
                    stop_event=_loop_stop_event,
                    screen_service=container.screen_service,
                    ws_manager=ws_manager,
                    interval_secs=float(get_settings().screen_capture_interval),
                ),
                name="screen_monitor_loop",
            )
        )
    else:
        logger.info(
            "ℹ️  Server-side screen monitor disabled "
            "(SCREEN_MONITOR_ENABLED=false). Frontend sends screen frames via WebSocket."
        )

    if get_settings().wake_word_local_enabled:
        logger.info("🎙️  Starting server-side wake word loop…")

        async def _on_wake_word_detected() -> None:
            """Notify all active sessions when wake word is detected from mic."""
            active = list(ws_manager.active_connections.keys())
            for _sid in active:
                state = ws_manager.get_state(_sid)
                if state and state.mode.value not in ("listening",):
                    state.start_listening()
                await ws_manager.send_event(
                    _sid,
                    {
                        "type": EventType.WAKE_WORD_DETECTED.value,
                        "data": {
                            "wake_word": "hey atlas",
                            "source": "server_microphone",
                        },
                    },
                )

        # Build wake word adapter (loads ONNX models — runs in executor on first call)
        try:
            from src.adapters.voice.open_wake_word_adapter import OpenWakeWordAdapter
            _oww = await asyncio.get_running_loop().run_in_executor(
                None, OpenWakeWordAdapter
            )
            _loop_tasks.append(
                asyncio.create_task(
                    run_wake_word_loop(
                        stop_event=_loop_stop_event,
                        wake_word_adapter=_oww,
                        on_detected=_on_wake_word_detected,
                    ),
                    name="wake_word_loop",
                )
            )
        except Exception as _oww_err:
            logger.warning(f"\u26a0\ufe0f  Could not start wake word loop: {_oww_err}")
    else:
        logger.info(
            "\u2139\ufe0f  Server-side wake word loop disabled "
            "(WAKE_WORD_LOCAL_ENABLED=false). Frontend sends audio_chunk via WebSocket."
        )

    yield  # app is live, waiting for shutdown signal

    # Shutdown
    logger.info("\U0001f6d1 Atlas AI Backend shutting down...")

    # Stop background loops gracefully
    if _loop_tasks:
        logger.info(f"\U0001f6d1 Stopping {len(_loop_tasks)} background loop(s)\u2026")
        _loop_stop_event.set()
        await asyncio.gather(*_loop_tasks, return_exceptions=True)
        logger.info("\u2705 Background loops stopped")

    if container:
        await container.shutdown()
    logger.info("\u2705 Atlas AI Backend stopped cleanly")


# FastAPI App

app = FastAPI(
    title="Atlas AI Backend",
    description="Backend API for Atlas AI Visual Companion",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting — per-IP, applied per-route via @limiter.limit(...) in routes
# that trigger paid API calls (game/chat, settings writes). See rate_limit.py.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS
_cors_origins_raw = os.environ.get("CORS_ORIGINS", "")
CORS_ORIGINS = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()] or [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://atlas-ai.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Atlas-Key"],
)

# Routers
from src.infrastructure.api.routes import game as game_routes  # noqa: E402

app.include_router(websocket.router, prefix="/api")
app.include_router(settings_routes.router, prefix="/api")
app.include_router(game_routes.router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "status": "Atlas AI Backend running",
        "mode": get_settings().atlas_mode,
        "version": "0.1.0",
    }


@app.get("/health")
async def health():
    """Health check for load balancers."""
    return {"status": "ok", "mode": get_settings().atlas_mode}
