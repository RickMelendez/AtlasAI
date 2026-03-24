# Phase 1: Ship-Blocking Fixes - Research

**Researched:** 2026-03-24
**Domain:** FastAPI WebSocket + SQLAlchemy async + Playwright + Python async patterns
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | Fix port discrepancy — frontend WebSocket URL must match backend port (8000 vs 8001) | One-line change confirmed; exact file and line identified |
| PERS-03 | Conversation history saved to DB after each exchange | Repository fully implemented; injection pattern clear from existing DI wiring in main.py |
| PERS-04 | Session restore: reconnecting client loads last N messages from DB | `get_last_n_messages()` exists; `to_claude_format()` on Message entity ready for Claude history list |
| INFRA-02 | Playwright browser context cleanup on session disconnect | `close_session()` already exists on PlaywrightAdapter; just not called on disconnect |
| INFRA-03 | Rename wake_word_loop → handle_messages for clarity | Pure rename + docstring update, zero behavior change |
| AI-09 | Conversation history persisted to SQLite DB across sessions | Requires PERS-03 + PERS-04 plumbing; DB schema already correct |
</phase_requirements>

---

## Summary

Phase 1 is a brownfield repair phase. The Atlas AI codebase is ~85% complete but blocked by five concrete defects preventing any end-to-end verification. All five fixes are surgical — no new libraries, no architecture changes, no new abstractions. The stack is already in place; it just needs to be wired.

The most critical blocker is the WebSocket port bug: the frontend connects to `ws://localhost:8001/api/ws` but uvicorn listens on port 8000. This single typo means the frontend has never successfully connected to the backend. Every other phase depends on this being fixed first.

The second major issue is that conversation persistence is fully implemented at the infrastructure layer (`SQLiteConversationRepository` with all methods) but the repository is never injected into the use cases. The `ProcessChatMessageUseCase.execute()` calls `ai_service.generate_response(conversation_history=None)` — history is always null. Fixing this requires: (a) injecting the repository into the use cases, (b) loading or creating a Conversation on each session connect, (c) saving user + assistant messages after each exchange, and (d) loading the last 10 messages as Claude history.

**Primary recommendation:** Fix the port bug first (1 minute), then wire DB persistence (the most substantial work, ~30-50 lines across 3 files), then Playwright cleanup (2 lines), then the two `manager.py` cleanups.

---

## Standard Stack

### Core (already installed — no new dependencies needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.115.6 | WebSocket + HTTP backend | Already in use; provides `AsyncSession` DI, lifespan |
| SQLAlchemy | 2.0.36 | Async ORM | Already in use; `async_sessionmaker` pattern established in `base.py` |
| aiosqlite | 0.20.0 | SQLite async driver | Already in use; backend for SQLAlchemy async engine |
| Playwright | 1.49.0 | Browser automation | Already in use; `close_session()` method exists but unused |
| pytest | 8.3.4 | Testing | Already in requirements; `tests/` scaffold exists |
| pytest-asyncio | 0.25.2 | Async test support | Already in requirements |

### No New Installations Required

All dependencies are already present in `backend/requirements.txt`. Phase 1 is purely a wiring and bug-fix phase.

---

## Architecture Patterns

### Pattern 1: Clean Architecture Dependency Injection (how to wire the repository)

**What:** The existing codebase uses FastAPI `lifespan` in `main.py` to construct all singletons and wire them together. Use cases receive dependencies through their `__init__`. The pattern for injecting services is already established (see `make_voice_use_case` factory, `chat_use_case.tool_executor = tool_executor`).

**When to use:** Whenever adding a new dependency to a use case.

**How the repository gets a session:** `AsyncSessionFactory()` is a context manager. Each request/operation that touches the DB should open its own session via `async with AsyncSessionFactory() as session`. Do NOT hold a session open for the lifetime of a WebSocket connection — SQLite will lock. Create sessions per-operation.

```python
# Source: backend/src/infrastructure/database/base.py — existing pattern
from src.infrastructure.database import AsyncSessionFactory
from src.infrastructure.database.repositories.conversation_repository import SQLiteConversationRepository

async with AsyncSessionFactory() as session:
    async with session.begin():
        repo = SQLiteConversationRepository(session)
        conversation = await repo.get_active_conversation_by_session(session_id)
```

**Critical:** The repository constructor takes an `AsyncSession`. Because WebSocket sessions are long-lived but DB sessions should be short-lived, create a new `SQLiteConversationRepository` instance per DB operation wrapped in `async with AsyncSessionFactory()`. Do not store the repo as a use-case attribute.

### Pattern 2: Building Claude History from DB Messages

**What:** `Message.to_claude_format()` already exists and produces `{"role": "user"|"assistant", "content": str}`. `get_last_n_messages(conversation_id, n=10)` returns them in chronological order. This maps directly to what `generate_response(conversation_history=...)` expects.

```python
# Pattern for building history list from DB
messages = await repo.get_last_n_messages(conversation_id, n=10)
history = [msg.to_claude_format() for msg in messages]
# history is List[Dict[str, str]] — matches AIService.generate_response signature
```

### Pattern 3: Playwright Context Cleanup on Disconnect

**What:** `PlaywrightAdapter.close_session(session_id)` already exists (line 264 of `playwright_adapter.py`). It pops the context from `self._contexts` and schedules `ctx.close()` on the ProactorEventLoop. It just needs to be called from `WebSocketManager.disconnect()`.

```python
# In WebSocketManager.disconnect() — add this call
def disconnect(self, session_id: str) -> None:
    self.running_loops[session_id] = False
    self.active_connections.pop(session_id, None)
    self.assistant_states.pop(session_id, None)
    self.running_loops.pop(session_id, None)
    self.screen_contexts.pop(session_id, None)
    # ADD: cleanup Playwright context
    if self._tool_executor and hasattr(self._tool_executor, '_playwright'):
        self._tool_executor._playwright.close_session(session_id)
```

**Note:** `ToolExecutor` holds a reference to `PlaywrightAdapter`. `WebSocketManager` already has `self._tool_executor`. The cleanup path is: `ws_manager._tool_executor._playwright.close_session(session_id)`.

### Pattern 4: Message Persistence Flow

**What:** After each chat exchange, persist both the user message and the assistant response.

**When:** After `chat_use_case.execute()` returns a successful result in `handle_user_message` in `main.py`, and after the voice pipeline completes in `_run_voice_pipeline` in `manager.py`.

```python
# Pattern for saving a message exchange
from src.domain.entities.message import Message, MessageRole
from src.domain.entities.conversation import Conversation

async def _save_exchange(session_id: str, user_text: str, assistant_text: str, language: str):
    async with AsyncSessionFactory() as session:
        async with session.begin():
            repo = SQLiteConversationRepository(session)
            # Get or create conversation
            conversation = await repo.get_active_conversation_by_session(session_id)
            if not conversation:
                conversation = Conversation(session_id=session_id, language=language)
                await repo.create_conversation(conversation)
            # Save user message
            user_msg = Message(
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=user_text,
            )
            await repo.add_message(user_msg)
            # Save assistant response
            assistant_msg = Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=assistant_text,
            )
            await repo.add_message(assistant_msg)
            conversation.touch()
            await repo.update_conversation(conversation)
```

### Pattern 5: Loading History on New Connection

**What:** When `handle_user_message` fires, check if there is an existing conversation for the session, load its last 10 messages, and pass them as `conversation_history` to `generate_response`.

**Note:** The `ProcessChatMessageUseCase.execute()` signature does NOT currently accept `conversation_history` — it passes it as `None` to `ai_service.generate_response()`. The fix is to add `conversation_history` as a parameter to `execute()` or pass it directly from `handle_user_message`.

Looking at the existing call in `main.py`:
```python
result = await chat_use_case.execute(message, state, screen_context=screen_context)
```

The cleanest approach is to load history in `handle_user_message` (where `session_id` is available) and pass it to the use case, which already forwards it to `generate_response`. This avoids injecting the DB into the use case class itself, keeping the use case thin.

### Anti-Patterns to Avoid

- **Long-lived DB sessions on WebSocket connections:** SQLite connections held across async I/O calls can cause lock contention. Create sessions per operation only.
- **Storing `SQLiteConversationRepository` as a class attribute initialized at startup:** The repository requires an active `AsyncSession` — it cannot be a singleton. Instantiate per operation.
- **Calling `close_session()` before `disconnect()` completes:** `close_session()` is non-blocking (schedules on ProactorEventLoop). Order doesn't matter but it must be called.
- **Forgetting `session.begin()` context manager:** `autocommit=False` and `autoflush=False` — must explicitly begin and the `async with session.begin()` block commits on exit.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async SQLite sessions | Custom connection manager | `AsyncSessionFactory()` from `base.py` | Already handles commit/rollback, `expire_on_commit=False` |
| Message to Claude format | Manual dict construction | `Message.to_claude_format()` | Already implemented on domain entity |
| Conversation lookup by session | Raw SQL | `repo.get_active_conversation_by_session()` | Fully implemented with correct index and ordering |
| Last N messages for context | Manual limit/offset | `repo.get_last_n_messages()` | Returns chronologically ordered, handles edge cases |
| Playwright cleanup logic | Manually closing ctx/page | `playwright_adapter.close_session()` | Already implemented, handles the ProactorEventLoop threading |

**Key insight:** Every tool needed to fix this phase already exists in the codebase. This is a wiring problem, not a building problem.

---

## Common Pitfalls

### Pitfall 1: Port Bug — Wrong Singleton Initialization

**What goes wrong:** The `WebSocketService` singleton is created at module load time with the default URL: `export const wsService = new WebSocketService()` — the constructor default is `'ws://localhost:8001/api/ws'`. Changing the default parameter fixes all future instantiations automatically.

**Why it happens:** The port was likely set to 8001 during early development when something else was on 8000.

**How to avoid:** Change the default from `8001` to `8000` in the constructor (line 36 of `websocket.ts`). No callers pass a custom URL, so this is sufficient.

**Warning signs:** Frontend console shows WebSocket connection refused errors every 3 seconds.

### Pitfall 2: DB Session Scope on Long-Lived WebSocket

**What goes wrong:** Creating one `AsyncSession` for the lifetime of a WebSocket session causes SQLite `database is locked` errors under concurrent access, and stale reads when other sessions modify data.

**Why it happens:** `aiosqlite` is single-writer. Long-held write sessions block other sessions.

**How to avoid:** Use `async with AsyncSessionFactory() as session: async with session.begin():` for each discrete DB operation. Keep the session open only for the duration of the read or write, then close it.

**Warning signs:** `sqlalchemy.exc.OperationalError: (aiosqlite.OperationalError) database is locked`

### Pitfall 3: `session.begin()` Nesting with `autocommit=False`

**What goes wrong:** Calling `session.begin()` when a transaction is already open raises `InvalidRequestError: A transaction is already begun`.

**Why it happens:** `AsyncSessionFactory` has `autocommit=False`. Using `async with session.begin()` is the clean pattern.

**How to avoid:** Always use the `async with AsyncSessionFactory() as session: async with session.begin():` double-context pattern for each operation. Never call `session.begin()` manually outside of this pattern.

### Pitfall 4: ToolExecutor Does Not Expose playwright_adapter as a Public Attribute

**What goes wrong:** `WebSocketManager.disconnect()` needs to call `playwright_adapter.close_session()` but `ws_manager` has access only to `self._tool_executor`. If `ToolExecutor` doesn't expose the adapter, the path is blocked.

**Why it happens:** `ToolExecutor` may store the adapter privately.

**How to avoid:** Check `ToolExecutor.__init__` signature — if it stores `self._playwright = playwright_adapter`, access is `ws_manager._tool_executor._playwright.close_session(session_id)`. Alternatively, add a method to `WebSocketManager` to register the playwright adapter directly, or add a `close_session` proxy on `ToolExecutor`.

**Warning signs:** `AttributeError` on disconnect if the attribute name is wrong.

### Pitfall 5: Double Message Routing (chat vs voice)

**What goes wrong:** Chat messages are persisted in `handle_user_message` (fired via EventBus), but voice commands are processed in `_run_voice_pipeline` (directly in `manager.py`, never hits EventBus). If you only add persistence to `handle_user_message`, voice conversations won't be saved.

**Why it happens:** Two separate code paths handle the two input modalities. They both call `ai_service.generate_response` but through different channels.

**How to avoid:** Add persistence in BOTH places:
1. In `main.py` `handle_user_message` — for text chat
2. In `manager.py` `_run_voice_pipeline` — for voice commands (after step 5/Claude path)

### Pitfall 6: screen_monitor_loop Removal Side Effects

**What goes wrong:** The `screen_monitor_loop` is launched as an `asyncio.Task` in `connect()`. If removed entirely, the `asyncio.create_task(self.screen_monitor_loop(session_id))` call must also be removed. Leaving a dangling call to a removed method causes `AttributeError`.

**Why it happens:** The loop and the call-site are in different methods.

**How to avoid:** When removing `screen_monitor_loop`, also remove the `asyncio.create_task(self.screen_monitor_loop(session_id))` call on line 349 of `manager.py`.

---

## Code Examples

Verified patterns from reading the actual source files:

### DB Session Pattern (from base.py)
```python
# Source: backend/src/infrastructure/database/base.py
async with AsyncSessionFactory() as session:
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
```

### Repository Instantiation (from existing codebase pattern)
```python
# Source: backend/src/infrastructure/database/repositories/conversation_repository.py
from src.infrastructure.database import AsyncSessionFactory
from src.infrastructure.database.repositories.conversation_repository import SQLiteConversationRepository

async with AsyncSessionFactory() as session:
    async with session.begin():
        repo = SQLiteConversationRepository(session)
        result = await repo.get_active_conversation_by_session(session_id)
```

### Message.to_claude_format() (from domain entity)
```python
# Source: backend/src/domain/entities/message.py
def to_claude_format(self) -> dict:
    role = "user" if self.role == MessageRole.USER else "assistant"
    return {"role": role, "content": self.content}
# Usage:
history = [msg.to_claude_format() for msg in messages]
# Produces: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
```

### PlaywrightAdapter.close_session() (already implemented)
```python
# Source: backend/src/adapters/web/playwright_adapter.py line 264
def close_session(self, session_id: str) -> None:
    """Elimina el BrowserContext de la sesión (limpieza en disconnect)."""
    entry = self._contexts.pop(session_id, None)
    if entry:
        ctx, _ = entry
        self._schedule(ctx.close())
```

### WebSocket URL Fix (exact change)
```typescript
// Source: frontend/src/renderer/services/websocket.ts line 36
// BEFORE:
constructor(url: string = 'ws://localhost:8001/api/ws') {
// AFTER:
constructor(url: string = 'ws://localhost:8000/api/ws') {
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `conversation_history=None` always passed to Claude | Load last 10 messages from DB, pass as history | Claude has context continuity across messages |
| Playwright BrowserContexts leak on disconnect | `close_session()` called in `disconnect()` | Memory stable across 10+ reconnects |
| `wake_word_loop()` handles all message types | Renamed `handle_messages()` with accurate docstring | New developers understand the codebase correctly |
| `screen_monitor_loop()` burns CPU with `asyncio.sleep(3)` | Removed or replaced with a state-check log | Saves one asyncio Task per connection |

---

## File Map: Exact Changes Required

This phase touches exactly 4 files (5 tasks, 2 tasks are in manager.py):

| Task | File | Nature of Change |
|------|------|-----------------|
| 1. Port fix | `frontend/src/renderer/services/websocket.ts` line 36 | Change `8001` → `8000` in default constructor arg |
| 2. DB persistence | `backend/src/main.py` in `handle_user_message` | Load history before `execute()`, save exchange after |
| 2. DB persistence | `backend/src/infrastructure/websocket/manager.py` in `_run_voice_pipeline` | Save exchange after Claude voice response |
| 3. Playwright cleanup | `backend/src/infrastructure/websocket/manager.py` in `disconnect()` | Call `self._tool_executor._playwright.close_session(session_id)` |
| 4. Rename loop | `backend/src/infrastructure/websocket/manager.py` | Rename method + all call sites + log messages |
| 5. Remove no-op | `backend/src/infrastructure/websocket/manager.py` | Remove `screen_monitor_loop` method + `create_task` call in `connect()` |

**Key finding:** Tasks 3, 4, and 5 are all in `manager.py` — plan them as sequential edits to the same file to avoid conflicts.

---

## Open Questions

1. **ToolExecutor attribute name for PlaywrightAdapter**
   - What we know: `WebSocketManager` has `self._tool_executor`; `PlaywrightAdapter` has `close_session()`
   - What's unclear: Whether `ToolExecutor` stores it as `self._playwright` or another name
   - Recommendation: Read `backend/src/adapters/tools/tool_executor.py` before implementing Task 3 to confirm the attribute path. If not exposed, add a `close_browser_session(session_id)` method to `ToolExecutor` that delegates to the adapter.

2. **Should voice pipeline persistence go in manager.py or a separate helper?**
   - What we know: `_run_voice_pipeline` is already 100+ lines; adding DB persistence inline adds ~20 more
   - What's unclear: Whether this violates the single-responsibility of the manager
   - Recommendation: Keep it inline for this phase (it's a fix, not a refactor). Extract to a helper in Phase 2 if complexity grows.

3. **Conversation identity on reconnect**
   - What we know: A new `session_id` is generated on each WebSocket connection (`str(uuid.uuid4())` in `websocket.py`)
   - What's unclear: Whether "chat history survives backend restart" means the same session_id reconnects, or whether the frontend should send a stable client ID
   - Recommendation: For Phase 1, interpret "survives restart" as: the LAST active conversation by session_id is loaded if it exists. On reconnect, a new session_id is generated but the previous conversation stays in the DB (browseable later). True session continuity across restarts requires the frontend to persist and re-send a session_id — out of scope for this phase.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection — all findings verified by reading actual source files
  - `frontend/src/renderer/services/websocket.ts` — port bug confirmed at line 36
  - `backend/src/infrastructure/websocket/manager.py` — `wake_word_loop` name, `screen_monitor_loop` no-op confirmed at line 919-936
  - `backend/src/infrastructure/database/repositories/conversation_repository.py` — full implementation confirmed, not injected
  - `backend/src/adapters/web/playwright_adapter.py` — `close_session()` confirmed at line 264, not called on disconnect
  - `backend/src/main.py` — no DB injection in `handle_user_message` confirmed
  - `backend/src/domain/entities/message.py` — `to_claude_format()` confirmed
  - `backend/src/domain/entities/conversation.py` — `touch()`, `Conversation()` constructor confirmed
  - `backend/src/infrastructure/database/base.py` — `AsyncSessionFactory` pattern confirmed

### Secondary (MEDIUM confidence)
- SQLAlchemy 2.0 async session management pattern (async context manager) — consistent with official SQLAlchemy 2.0 async docs pattern and confirmed by existing `get_db_session()` implementation in `base.py`

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in use, no new dependencies
- Architecture: HIGH — all patterns sourced directly from existing codebase code
- Pitfalls: HIGH — sourced from direct code inspection, not hypothetical
- Open questions: MEDIUM — ToolExecutor internals not yet read (one file to verify)

**Research date:** 2026-03-24
**Valid until:** 2026-05-24 (stable internal codebase — no external library churn risk)
