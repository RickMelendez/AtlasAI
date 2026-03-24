---
name: atlas-debug
description: >
  High-level debugging for the AtlasAI project. Use this skill whenever something is broken,
  crashing, not connecting, or behaving unexpectedly in Atlas — including WebSocket disconnects,
  Electron renderer reloads, Porcupine wake-word failures, audio capture issues, Vite HMR
  problems, backend loop errors, or any startup crash. Applies scientific method: observe →
  hypothesize → instrument → verify → fix. Knows the full AtlasAI architecture cold.
---

# Atlas Debugger

You are a senior engineer who knows the AtlasAI codebase deeply. Your job is to find and fix bugs using the scientific method, not guesswork.

## AtlasAI Architecture Quick Reference

```
Frontend (Electron 28 + React 18 + Vite 5)
  src/main/index.ts          — Electron main process, window creation
  src/preload/index.ts       — IPC bridge (contextBridge)
  src/renderer/App.tsx       — Root React component (StrictMode)
  src/renderer/hooks/
    useWebSocket.ts          — Singleton WebSocket hook (NO disconnect on cleanup)
    useAudioCapture.ts       — Mic capture, PCM chunks, wake-word mode
    useTTSPlayer.ts          — TTS audio playback
  src/renderer/services/
    websocket.ts             — WebSocketService singleton
  vite.config.ts             — Vite + vite-plugin-electron config with reload guards

Backend (FastAPI + Python)
  src/main.py                — FastAPI app, lifespan startup
  src/infrastructure/websocket/manager.py  — WebSocketManager, wake_word_loop
  src/adapters/voice/
    porcupine_adapter.py     — Wake word (pvporcupine v4, run in executor)
    whisper_adapter.py       — STT
    elevenlabs_adapter.py    — TTS
  src/infrastructure/config/settings.py    — Pydantic settings from .env
```

## Known Failure Modes

| Symptom | Likely Cause | Where to look |
|---------|-------------|---------------|
| WS disconnects ~1.5s after connect | Renderer page reload from Vite HMR | `vite.config.ts` reload guard, `[atlas]` log lines |
| Renderer disappears on startup | Spurious `full-reload` from vite-plugin-electron | `server.hot.send` / `server.ws.send` patches |
| "Porcupine not compatible" | pvporcupine SDK version mismatch with .ppn | `pip install 'pvporcupine>=4.0.0'` |
| Wake word never detected | No .ppn file in `backend/models/` | Falls back to built-in "computer" keyword |
| AudioContext errors | `getUserMedia` permission denied or 16kHz unsupported | `session.setPermissionRequestHandler` in `index.ts` |
| Backend loop error | Blocking sync call in async context | Move to `loop.run_in_executor()` |
| Double WebSocket connect | React 18 StrictMode double-mount | Check cleanup doesn't call `wsService.disconnect()` |

## Debug Process

### 1. Gather Symptoms
Before touching any code, collect:
- Exact error message and stack trace
- Which process it's in (main / renderer / backend)
- Timeline: when does it happen relative to startup?
- Is it consistent or intermittent?

### 2. Read the Logs

**Frontend main process logs** (CMD window running Vite):
```
[Main] *          — Electron main process events
[Renderer:I/W/E]  — Renderer console forwarded to main (if enabled)
[Tray] *          — Tray events
[atlas] 🛡️         — Reload guard firing
[Main] ⚠️ Renderer navigating  — Page reload detected
[Main] ❌ Renderer crashed      — Renderer process crash
```

**Backend logs** (CMD window running uvicorn):
```
INFO: connection open/closed     — WebSocket lifecycle
[session_id] Disconnected in main loop  — WS closed from frontend
[session_id] Wake word loop stopped     — Loops cleaning up
```

### 3. Instrument Strategically

Add logging at the exact boundary where you lose track of the execution:

```python
# Backend: before suspected blocking call
logger.info(f"[{session_id}] About to call X at {datetime.now().isoformat()}")
```

```typescript
// Frontend: track state transitions
console.log('[Debug] mode transition:', prev, '->', next, 'at', Date.now())
```

Enable renderer console forwarding in `index.ts` if not already:
```typescript
window.webContents.on('console-message', (_e, level, message, line, source) => {
  const tag = ['V','I','W','E'][level] ?? level
  console.log(`[Renderer:${tag}] ${message}  (${source?.split('/').pop()}:${line})`)
})
```

### 4. Form ONE Hypothesis

Don't chase multiple causes simultaneously. Pick the most likely one and prove or disprove it with a minimal test. Document:
- Hypothesis: "The reload is caused by X because Y"
- Test: "If I do Z, the reload should disappear"
- Result: What actually happened

### 5. Fix and Verify

- Make the smallest possible change that addresses the root cause
- Don't fix symptoms — fix causes
- Verify the fix works by restarting and observing the full startup sequence
- Check the backend logs to confirm the WS connection stays alive past the critical 2-second window

## Common Fixes Reference

**Vite HMR spurious reload** — Both `server.hot.send` AND `server.ws.send` must be patched in `vite.config.ts` with a startup time guard (15s). Check that `SPURIOUS_BUILD_GUARD_MS = 10_000` (not self-referential).

**Porcupine blocking event loop** — `pvporcupine.create()` makes a network call. Always run in executor:
```python
loop = asyncio.get_running_loop()
porcupine = await loop.run_in_executor(None, lambda: PorcupineAdapter(...))
await loop.run_in_executor(None, porcupine.start_listening)
```

**React StrictMode WebSocket disconnect** — NEVER call `wsService.disconnect()` in `useWebSocket` cleanup. Only remove event handlers.

**Media permission dialog causing navigation** — Add in `app.whenReady()`:
```typescript
session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
  callback(['media', 'display-capture', 'desktopCapture'].includes(permission))
})
```

## Output Format

After debugging, always produce:
1. **Root cause** — one sentence, precise
2. **Evidence** — log lines or code path that proves it
3. **Fix applied** — what was changed and why
4. **Verification** — how to confirm it's resolved
