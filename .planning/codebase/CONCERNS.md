# CONCERNS.md — Atlas AI Technical Debt & Concerns

## Critical / High Priority

### 1. No Test Suite
**Severity**: High
**Files**: `backend/tests/__init__.py` (empty)

Zero automated tests. All verification is manual. Any refactor or new feature risks silent regressions. The domain layer (`AssistantState`, use cases) is pure Python and trivially testable — this is low-hanging fruit.

**Risk**: Breaking state machine or pipeline logic with no safety net.

---

### 2. Wake Word Loop is Actually the Main Message Loop
**Severity**: High — misleading name causes confusion
**File**: `backend/src/infrastructure/websocket/manager.py:wake_word_loop()`

`wake_word_loop()` handles ALL incoming WebSocket messages (chat, audio, screen, ping) despite the name. This is the main receive loop. The name is a legacy artifact from before it became the universal handler.

**Risk**: New developers adding message handlers in the wrong place.

---

### 3. Screen Monitor Loop is a No-op
**Severity**: Medium
**File**: `backend/src/infrastructure/websocket/manager.py:screen_monitor_loop()`

```python
async def screen_monitor_loop(self, session_id: str) -> None:
    while self.running_loops.get(session_id, False):
        try:
            await asyncio.sleep(3)  # does nothing
        except Exception as e:
            ...
```

This loop starts as a background task but only sleeps. The actual screen monitoring happens via the WebSocket `screen_capture` message handler in the main loop. The loop is dead weight but still starts as a `asyncio.Task`.

---

### 4. `loops/` Directory Is Empty Scaffold
**Severity**: Medium
**File**: `backend/src/infrastructure/loops/__init__.py`

CLAUDE.md warns: "loops/ directory is a scaffold — wake_word_loop.py / screen_monitor_loop.py are not yet implemented." The loops live inside `manager.py` instead of dedicated files. The directory implies structure that doesn't exist.

---

### 5. STATUS.md Is Stale
**Severity**: Medium
**File**: `STATUS.md`

STATUS.md says "Last Updated: 2026-03-18" and lists several items as pending that are actually implemented (Tesseract replaced by Claude Vision, database layer present). The document references Tesseract as the active OCR system but `claude_vision_adapter.py` is the actual implementation. Use CLAUDE.md as the authoritative source.

---

### 6. CORS Allows Wildcard in "Dev" Mode
**Severity**: Medium (acceptable for local desktop app)
**File**: `backend/src/main.py:248`

```python
"*",  # En desarrollo permitir todos
```

This is acceptable for a local Electron app but should be removed or explicitly conditional before any web deployment.

---

## Medium Priority

### 7. Tool Executor Has No Auth/Sandbox Boundaries
**Severity**: Medium
**File**: `backend/src/adapters/tools/tool_executor.py`

`run_terminal_command` executes arbitrary shell commands filtered only by regex. The blocklist (`_DANGEROUS_PATTERNS`) covers obvious destructive commands but:
- No working directory restriction
- No output size limit beyond 4000 chars (stdout) / 1000 chars (stderr)
- `write_file` can write anywhere on the filesystem
- `read_file` can read any file (including secrets)

For a trusted local assistant this is acceptable, but the tool executor should not be exposed to untrusted input.

---

### 8. Conversation History Not Persisted
**Severity**: Medium
**Files**: `backend/src/infrastructure/websocket/manager.py`

Conversation history is in-memory per session. The database layer exists (`ConversationRepository`, SQLAlchemy models) but is not wired into `ProcessChatMessageUseCase`. All history is lost on backend restart or disconnect.

---

### 9. Session State Lost on Reconnect
**Severity**: Medium

When the WebSocket reconnects (auto-reconnect after backend restart), a new session is created with a fresh UUID. Previous conversation context and assistant state are lost. There is no session restore mechanism.

---

### 10. Voice Pipeline Has Duplicate Language Detection
**Severity**: Low
**File**: `backend/src/infrastructure/websocket/manager.py`

Language is detected twice in `_run_voice_pipeline`:
1. After Whisper transcription (sets `state.language`)
2. `_detect_language()` is also called for chat messages in the main loop

This is benign but inconsistent — language should be derived once per message from a single source.

---

### 11. `finish_speaking()` Guard Is Bypassed in Voice Pipeline
**Severity**: Low
**File**: `backend/src/infrastructure/websocket/manager.py:910`

```python
finally:
    self._voice_busy[session_id] = False
    # Ensure state always resets to ACTIVE after voice pipeline,
    # even if finish_speaking() guard failed earlier.
    if state and state.mode != AssistantMode.ACTIVE:
        state.reset_to_active()
```

The `finish_speaking()` method only works from `SPEAKING` state. If the pipeline errors before reaching `SPEAKING`, the `finally` block force-resets via `reset_to_active()`. This works but bypasses state machine validation. The comment acknowledges this.

---

### 12. Frontend WebSocket URL Is Hardcoded
**Severity**: Low
**File**: `frontend/src/renderer/services/websocket.ts:36`

```typescript
constructor(url: string = 'ws://localhost:8001/api/ws') {
```

Port 8001 hardcoded (though backend runs on 8000 per CLAUDE.md — there may be a port mismatch). Should come from a `VITE_` environment variable.

---

### 13. `claude_adapter.py` Has Unused Singleton
**Severity**: Low
**File**: `backend/src/adapters/ai/claude_adapter.py:599`

```python
_claude_adapter_instance: Optional[ClaudeAdapter] = None

def get_claude_adapter() -> ClaudeAdapter:
    ...
```

This singleton factory exists but is never called — `main.py` instantiates `ClaudeAdapter()` directly. Dead code.

---

### 14. Playwright Per-Session Browsers Not Cleaned Up on Disconnect
**Severity**: Low
**File**: `backend/src/adapters/web/playwright_adapter.py`

Sessions open browser contexts. On WebSocket disconnect, `ws_manager.disconnect()` only cleans WebSocket state — it doesn't notify `PlaywrightAdapter` to close the session's browser context. Long-running backends with many reconnects could accumulate orphaned browser contexts.

---

## Performance Notes

- **Vision debounce**: `_VISION_DEBOUNCE_SECS = 10.0` limits Claude Haiku calls to ~6/min per backend (global, not per-session). Multiple concurrent sessions share this debounce window.
- **Tool use max iterations**: `max_iterations = 10` in `ClaudeAdapter.generate_response()` — upper bound on agentic loops.
- **Whisper energy filter**: `avg_abs < 1200` threshold filters silence before API calls. Threshold may need tuning per environment noise floor.
- **Audio command drops when busy**: `_voice_busy` guard drops concurrent commands rather than queuing. Users get no feedback that their command was dropped.

---

## Fragile Areas

| Area | Why Fragile |
|---|---|
| Porcupine version | Must be v4 exactly — model file version must match library version |
| Wake word detection fallback | Whisper-based wake word is expensive (~1 API call per 3s of audio when energy > threshold) |
| Tool use loop content serialization | `[{"type": b.type, **{k: v for k, v in vars(b).items() if k != "type"}}]` in `claude_adapter.py:409` — fragile SDK internal attribute iteration |
| Base64 audio path | Two possible payload locations (`data.get("data", {}).get("audio")` or `data.get("audio")`) handled with `or` chaining — reflects evolving protocol |
