# CONVENTIONS.md — Atlas AI Code Conventions

## Language Rules

### Backend (Python)
- **Python version**: 3.13
- **Async-first**: All I/O is `async`/`await`. No blocking calls on the event loop.
  - Exception: init that must be synchronous runs via `loop.run_in_executor()` (e.g., Porcupine init)
- **Type hints**: Required throughout. `mypy` enforced. `Optional[str]` not `str | None` style.
- **Comments**: Complex business logic commented in **Spanish** (explicit project convention)
- **Docstrings**: Google-style, in Spanish on complex methods

```python
async def handle_user_message(data: dict):
    """Procesa mensajes de chat del usuario."""
    session_id = data.get("session_id")
    ...
```

### Frontend (TypeScript)
- **Strict TypeScript**: `tsconfig.json` strict mode
- **No `any` types** (project goal, per STATUS.md)
- Comments: English or Spanish (mixed)

---

## Error Handling Patterns

### Backend — Never let errors kill the event loop

```python
# Pattern 1: Log + return in hot paths
except Exception as e:
    logger.error(f"[{session_id}] Loop error: {e}", exc_info=True)
    sentry_capture(e, session_id=session_id, context="wake_word_loop")
    await asyncio.sleep(1)  # backoff before retry

# Pattern 2: Tool executor always returns JSON, never raises
async def execute(self, tool_name: str, tool_input: dict) -> str:
    try:
        ...
    except Exception as e:
        logger.error(f"Tool executor error in {tool_name}: {e}", exc_info=True)
        return json.dumps({"error": str(e)})  # caller gets error string

# Pattern 3: Graceful degradation with logging
if settings.openai_api_key:
    try:
        whisper_service = WhisperAdapter()
    except Exception as e:
        logger.warning(f"⚠️  WhisperAdapter not available: {e}")
else:
    logger.warning("⚠️  OPENAI_API_KEY not set — voice STT disabled")
```

### Frontend — Errors don't crash the WS service

```typescript
this.ws.onmessage = (event) => {
    try {
        const data = JSON.parse(event.data)
        if (data.type) this.emit(data.type, data.data || data)
    } catch (error) {
        console.error('[WebSocket] Error parsing message:', error)
        // swallow — don't close connection
    }
}
```

---

## Singleton Pattern

Module-level singletons — initialized once, imported everywhere.

```python
# backend/src/infrastructure/events/event_bus.py
event_bus = EventBus()  # module-level

# backend/src/infrastructure/websocket/manager.py
ws_manager = WebSocketManager()  # module-level
```

```typescript
// frontend/src/renderer/services/websocket.ts
export const wsService = new WebSocketService();  // module-level export
```

**Never** instantiate these inside functions or constructors — import the singleton.

---

## State Transitions

All state changes go through `AssistantState` methods — never mutate `state.mode` directly:

```python
# ✅ Correct
state.start_listening()
state.finish_speaking()
state.reset_to_active()  # error recovery only

# ❌ Wrong
state.mode = AssistantMode.LISTENING  # bypasses validation
```

---

## WebSocket Message Protocol

Consistent envelope for all messages in both directions:

```typescript
// Frontend → Backend
wsService.send('chat_message', { message: text })
// Results in: { type: "chat_message", data: { message: text } }

// Backend → Frontend
await ws_manager.send_event(session_id, ws_manager._make_event(
    EventType.AI_RESPONSE_GENERATED.value,
    {"message": result, "timestamp": ...}
))
// Results in: { type: "ai_response_generated", data: { message: ..., timestamp: ... } }
```

Always use `_make_event()` on the backend — never build `{"type": ..., "data": ...}` dicts manually.

---

## Async Background Tasks

Long-running operations must not block the WebSocket receive loop:

```python
# ✅ Correct — fire and forget, loop stays responsive
asyncio.create_task(self._run_voice_pipeline(session_id, audio_bytes))

# ❌ Wrong — blocks wake_word_loop, connection times out
result = await voice_use_case.execute(...)
```

Use `asyncio.create_task()` for any operation >100ms.

---

## Dependency Injection Pattern

Adapters are injected into use cases via constructor. Use cases only see interfaces:

```python
# Use case only knows AIService interface
class ProcessChatMessageUseCase:
    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service

# Main.py wires concrete adapter
claude_service = ClaudeAdapter()
chat_use_case = ProcessChatMessageUseCase(claude_service)
```

Late injection via attribute assignment is used for circular deps:

```python
# tool_executor created after chat_use_case
chat_use_case.tool_executor = tool_executor  # late inject
```

---

## Animation Rules

**No `setInterval` for animations** — always `requestAnimationFrame`:

```typescript
// ✅ Correct
const animate = () => {
    draw()
    animationRef.current = requestAnimationFrame(animate)
}
animationRef.current = requestAnimationFrame(animate)

// ❌ Wrong
setInterval(draw, 16)
```

---

## Logging Convention

Structured logging with emoji prefixes for quick scanning:

```python
logger.info("🚀 Atlas AI Backend starting up...")
logger.info("✅ ClaudeAdapter initialized with model: claude-sonnet-4-6")
logger.warning("⚠️  OPENAI_API_KEY not set — voice STT disabled")
logger.info(f"[{session_id}] 🎙️ Wake word detected: '{detected}'")
logger.info(f"[{session_id}] ⚡ Fast route: {route['tool']}({route['args']})")
logger.error(f"[{session_id}] Voice pipeline error: {e}", exc_info=True)
```

Session-scoped log lines always include `[{session_id}]` prefix.

---

## Configuration Access

Always use the cached settings singleton:

```python
from src.infrastructure.config.settings import get_settings
settings = get_settings()  # lru_cache — same instance every call
if settings.openai_api_key: ...
```

---

## Security: Dangerous Command Blocking

`ToolExecutor` has a regex blocklist for terminal commands. New dangerous patterns go in `_DANGEROUS_PATTERNS`:

```python
_DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"format\s+[a-z]:",
    r"shutdown",
    r"reboot",
    # ...
]
```

---

## Language Detection Heuristics

Built-in lightweight language detection (no external library):

```python
def _detect_language(text: str) -> str:
    if any(c in _ES_CHARS for c in text):   # á é í ó ú ü ñ ¿ ¡
        return "es"
    words = {w.strip("'.,!?") for w in text.lower().split()}
    return "en" if words & _EN_WORDS else "es"
```

Used on every user message to auto-set `state.language`, which drives the Claude system prompt selection.

---

## Fast Router Pattern

Deterministic routing before hitting Claude — zero LLM latency for known commands:

```python
def _fast_route(text: str) -> Optional[dict]:
    """Returns tool+args dict if high-confidence match, None to fall through to Claude."""
    t = text.lower().strip()
    if t.startswith("open "):
        target = t[5:].strip()
        if target in _KNOWN_SITES:
            return {"tool": "browse_web", "args": {"url": _KNOWN_SITES[target]}}
    ...
    return None  # → Claude handles it
```

Add new deterministic patterns here before adding Claude prompt instructions.
