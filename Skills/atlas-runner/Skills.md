---
name: atlas-runner
description: >
  Start, stop, and verify the AtlasAI development environment. Use this skill to run the
  project, check if backend and frontend are healthy, kill stuck processes, restart after
  crashes, and confirm the app is working end-to-end. Use when the user says "run it",
  "start the project", "kill everything and restart", "is it running?", or "test if it works".
---

# Atlas Runner

You know exactly how to start, stop, and verify the AtlasAI stack on Windows.

## Starting the Project

### Full dev environment (recommended)
```batch
# From project root in a terminal:
.\dev.bat
```
This opens two CMD windows: one for backend (port 8000), one for frontend Vite + Electron.

### Manual start (when dev.bat isn't working)
```bash
# Terminal 1 — Backend
cd backend
venv\Scripts\activate
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

## Killing Stuck Processes

```bash
# Kill Python/uvicorn (backend)
taskkill //F //IM python.exe 2>/dev/null || true

# Kill Node/Electron (frontend)
taskkill //F //IM node.exe 2>/dev/null || true
taskkill //F //IM electron.exe 2>/dev/null || true

# Kill all at once
taskkill //F //IM python.exe //IM node.exe //IM electron.exe 2>/dev/null || true
```

Wait 2 seconds after killing before restarting.

## Health Checks

### Backend healthy?
```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy", ...} with HTTP 200
```

### Backend WebSocket accepting?
```bash
# Python one-liner (from project root):
python -c "import websocket; ws = websocket.create_connection('ws://localhost:8000/api/ws'); print('WS OK:', ws.recv()); ws.close()"
```

### Frontend running?
Look for the orb window (small floating circle, always-on-top, bottom-right corner of screen). Also check for Vite dev server in the CMD window: `VITE v5.4.x  ready in Xms → Local: http://localhost:5173`

## Startup Sequence (what to expect)

**Healthy startup looks like this:**

Backend CMD:
```
INFO:     Application startup complete.
INFO:     ('127.0.0.1', XXXXX) - "WebSocket /api/ws" [accepted]
[session_id] ✅ WebSocket connected
[session_id] Continuous loops started
[session_id] Wake word loop started
[session_id] Porcupine wake word detection active  ← good
[session_id] Screen monitor loop started
```

Frontend CMD:
```
[Main] App is ready
[Main] Orb window created and always-on-top
[Main] Orb window ready to show
[Renderer:I] [WebSocket] ✅ Connected successfully
[Renderer:I] [AudioCapture] ✅ Mic capture started, listening for wake word...
```

**Red flags:**
- `connection closed` within 2 seconds of connecting → renderer reloaded
- `[Main] ⚠️  Renderer navigating:` → spurious Vite HMR reload
- `Disconnected in main loop` immediately → WebSocket closed from frontend
- `Error starting Porcupine` → check PICOVOICE_ACCESS_KEY in backend/.env

## Verifying End-to-End

1. Backend is up: `curl http://localhost:8000/health` returns 200
2. Orb window is visible in bottom-right corner
3. Connection dot (green) shows in UI
4. Say "computer" (fallback wake word) or click the orb → chat panel opens
5. Backend logs show `Wake word detected` or `Chat:` message

## Environment Requirements

```
backend/.env must have:
  ANTHROPIC_API_KEY=sk-ant-...
  OPENAI_API_KEY=sk-...         (for Whisper STT)
  PICOVOICE_ACCESS_KEY=...      (for wake word)
  DATABASE_URL=sqlite+aiosqlite:///./atlas.db

Python venv must be activated before uvicorn.
Node modules must be installed: cd frontend && npm install
```

## Reporting Status

After running checks, always report:
- Backend: ✅ running / ❌ down / ⚠️ starting
- Frontend: ✅ Electron window visible / ❌ not started
- WebSocket: ✅ connected and stable / ❌ disconnecting
- Wake word: ✅ Porcupine active / ⚠️ using fallback "computer" / ❌ disabled
