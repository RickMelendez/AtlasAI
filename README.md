# Atlas AI — AI Visual Companion

> An event-driven AI companion that watches your screen, listens for your voice, and holds a real conversation — powered by Anthropic Claude.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-blue.svg)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-blue.svg)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## What is Atlas?

Atlas is **not** a traditional chatbot. It's a **continuous, event-driven AI companion**:

- Listens for your wake word ("Hey Atlas") at all times, even when you're not interacting with it
- Watches your screen every few seconds and understands what you're working on
- Speaks back with natural TTS audio (ElevenLabs → Fish Audio → Edge-TTS fallback chain)
- Browses the web using a real Chromium window (Playwright automation)
- Remembers facts about you across sessions — type **"forget everything"** to wipe memory
- Detects errors on screen and proactively offers help before you even ask
- Streams responses token-by-token, like ChatGPT

---

## Live Demo

> **Try it without installing anything:**
>
> - Frontend: [https://atlas-ai.vercel.app](https://atlas-ai.vercel.app) *(add after deployment)*
> - Backend health check: [https://atlas-ai.railway.app/health](https://atlas-ai.railway.app/health) *(add after deployment)*

---

## Architecture

### Event-Driven System

Atlas is built around an **EventBus** — nothing blocks. Every component communicates through events:

```
Browser / Desktop
       │
       │  WebSocket (persistent)
       ▼
FastAPI Backend
  ├── EventBus (async pub/sub)
  ├── SessionManager (per-connection state)
  ├── CommandRouter (fast deterministic routing)
  ├── VoicePipeline (Whisper → Claude → TTS)
  └── ScreenCapture (Vision → proactive help)
```

### Clean Architecture (Hexagonal)

```
backend/src/
  ├── domain/               Pure business logic — no dependencies
  │   ├── entities/         AssistantState, Conversation, Message
  │   └── interfaces/       AIService port (abstract)
  │
  ├── application/          Use cases — orchestrate domain + adapters
  │   └── use_cases/        ProcessChatMessage, ProcessVoiceCommand
  │
  ├── adapters/             Concrete implementations of ports
  │   ├── ai/               claude_adapter.py (Anthropic SDK)
  │   ├── vision/           claude_vision_adapter.py
  │   ├── voice/            faster_whisper, elevenlabs, edge_tts, open_wake_word
  │   ├── web/              playwright_adapter.py (Chromium browser)
  │   └── notion/           notion_adapter.py
  │
  └── infrastructure/       Framework glue — FastAPI, SQLAlchemy, WebSocket
      ├── container.py      AppContainer (dependency injection root)
      ├── websocket/        manager.py, session_manager.py, command_router.py, voice_pipeline.py
      ├── events/           event_bus.py, event_types.py
      ├── database/         models.py, repositories/
      └── config/           settings.py, master_prompt.py
```

### Frontend Layout (3-Zone)

```
┌──────────────────────────────────────────────────┐
│ 64px │           Main Area                         │
│      │                                             │
│  🗨  │         [ Neural Orb ]                     │
│  🧠  │       (Three.js animation)                 │
│  ⚙  │                                             │
│      │                            ┌─────────────┐ │
│  ●   │                            │ Chat / Mem  │ │
│      │                            │  / Settings │ │
└──────┴────────────────────────────┴─────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript 5, Vite, Three.js, Lucide icons |
| Styling | GitHub dark design system (CSS variables, Inter font) |
| Backend | Python 3.11, FastAPI, uvicorn, asyncio |
| AI | Anthropic Claude (claude-sonnet-4-6) — streaming responses |
| STT | Faster Whisper (local, no API key) |
| Wake word | OpenWakeWord (local ONNX model) |
| TTS | ElevenLabs → Fish Audio → Edge-TTS (free fallback) |
| Vision | Claude Vision (proactive error detection) |
| Browser | Playwright (real Chromium automation) |
| Database | SQLite + SQLAlchemy async (conversations + memories) |
| Integrations | Notion API |

---

## Running Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git

### 1. Clone

```bash
git clone https://github.com/RickMelendez/AtlasAI.git
cd AtlasAI
```

### 2. Backend

```bash
cd backend

python -m venv venv
source venv/bin/activate      # Mac/Linux
# or: venv\Scripts\activate   # Windows

pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum
```

Start the backend:

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install

cp .env.example .env.local
# Default values work for local dev — no edits needed

npm run dev
```

Open http://localhost:5173

---

## Deploying for Recruiters (Railway + Vercel)

### Backend on Railway

1. Push your code to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select the `backend/` folder (or set root directory to `backend`)
4. Add environment variables in Railway dashboard:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ELEVENLABS_API_KEY=...
   NOTION_API_KEY=...
   CORS_ORIGINS=https://your-frontend.vercel.app
   ```
5. Railway will build using `backend/Dockerfile` and deploy automatically
6. Copy the Railway URL (e.g. `https://atlas-ai-backend.railway.app`)

### Frontend on Vercel

1. Go to [vercel.com](https://vercel.com) → New Project → Import from GitHub
2. Set root directory to `frontend/`
3. Add environment variables in Vercel dashboard:
   ```
   VITE_WS_URL=wss://atlas-ai-backend.railway.app/api/ws
   VITE_API_URL=https://atlas-ai-backend.railway.app
   ```
4. Deploy — Vercel builds automatically with `vercel.json` config

---

## Key Features in Detail

### Streaming Responses
Responses stream token-by-token from Claude, so text appears as it's generated — no waiting for the full reply.

### Persistent Memory
Atlas remembers facts you tell it between sessions (stored in SQLite). Type **"forget everything"** in chat to wipe all memories. The Memory panel (brain icon in sidebar) shows all stored facts.

### Proactive Error Detection
When Atlas sees an error, exception, or traceback on your screen, it speaks up automatically — without you asking. Respects a 60-second cooldown so it doesn't interrupt constantly.

### Voice Pipeline
```
Wake word ("Hey Atlas")
       ↓
VAD detects speech end
       ↓
Faster Whisper (local STT)
       ↓
Claude generates response (streaming)
       ↓
ElevenLabs → speech audio
       ↓
Plays in browser
```

### Settings Panel
All API keys configurable from inside the app UI (gear icon in sidebar). No need to edit `.env` files after initial setup.

---

## Project Structure

```
AtlasAI/
├── backend/
│   ├── src/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── adapters/
│   │   └── infrastructure/
│   │       ├── container.py          ← DI root
│   │       ├── websocket/            ← 4 focused modules
│   │       ├── database/repositories/
│   │       └── api/routes/
│   ├── Dockerfile
│   ├── railway.toml
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/renderer/
│   │   ├── components/
│   │   │   ├── Orb/          NeuralOrb.tsx (Three.js)
│   │   │   ├── Chat/         ChatInterface.tsx
│   │   │   ├── Memory/       MemoryPanel.tsx
│   │   │   └── Settings/     SettingsPanel.tsx
│   │   ├── hooks/            useAudioCapture, useTTSPlayer, useWebSocket
│   │   └── services/         websocket.ts
│   ├── vercel.json
│   └── .env.example
│
└── README.md
```

---

## Orb Visual States

| State | Appearance | Meaning |
|---|---|---|
| `active` | Bright cyan, slow pulse | Ready, listening for wake word |
| `listening` | Fast cyan pulse | Hearing you speak |
| `thinking` | Multicolor spin | Claude processing |
| `speaking` | Radial pulses sync with TTS | Playing audio response |
| `inactive` | Dim, slow | Paused / idle |

---

## License

MIT — see [LICENSE](LICENSE)

---

## Credits

- [Anthropic](https://anthropic.com) — Claude AI (claude-sonnet-4-6)
- [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) — local speech-to-text
- [OpenWakeWord](https://github.com/dscripka/openWakeWord) — offline wake word detection
- [ElevenLabs](https://elevenlabs.io) — neural text-to-speech
- [Playwright](https://playwright.dev) — browser automation
- [Three.js](https://threejs.org) — 3D orb animation

---

<div align="center">
<strong>Built with Clean Architecture · Event-Driven Design · Anthropic Claude</strong>
</div>
