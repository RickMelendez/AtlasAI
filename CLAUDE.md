# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Atlas AI Visual Companion** is an AI-powered visual assistant that functions as a tech-savvy companion sitting beside you, observing your screen, listening to your voice, and conversing naturally about what you both see.

**Critical Architectural Decision**: Atlas is NOT a traditional request/response API. It is an **event-driven continuous system** that operates like a living being - always listening, always watching, always ready.

## Architecture Philosophy

### Event-Driven vs Traditional API

```
❌ INCORRECT (Traditional API):
User speaks → POST /chat → Response → END

✅ CORRECT (Event-Driven + WebSocket):
WebSocket always open
  ↓
Backend continuous loops:
  • Wake word detection (24/7)
  • Screen monitoring (every 3s when ACTIVE)
  • Conversation processing
  • Proactive suggestions

REST Endpoints (only for explicit commands):
  • POST /activate
  • POST /pause
  • GET /status
```

## Development Commands

### Start Everything (Windows)
```batch
# From project root — opens two CMD windows
.\dev.bat
```
- **Backend**: `http://localhost:8000` (auto-reloads on `.py` changes)
- **Frontend**: `http://localhost:5173` (hot-reloads on `.tsx/.css` changes)

### Backend
```bash
cd backend
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux
uvicorn src.main:app --reload

# Install deps
pip install -r requirements.txt

# Manual integration test (requires real API keys in .env)
python test_claude.py

# Formal tests (suite is currently empty — scaffold only)
pytest
pytest --cov=src tests/

# Code quality
black .
isort .
mypy src/
```

### Frontend
```bash
cd frontend
npm run dev          # Vite dev server (browser only, no Electron shell)
npm run build        # Full Electron build → release/{version}/
npm run lint
npm run type-check
```

## Technology Stack

### Frontend (Electron + React)
- **Runtime**: Electron 28
- **Framework**: React 18 + TypeScript 5
- **Styling**: TailwindCSS + shadcn/ui (`components.json` config)
- **Animation**: Canvas API (particle orb)
- **State**: Zustand
- **Build**: Vite + vite-plugin-electron
- **Error monitoring**: Sentry (`src/renderer/sentry.ts`)

### Backend (Python FastAPI)
- **Framework**: FastAPI + uvicorn
- **Architecture**: Clean Architecture (Domain → Application → Infrastructure)
- **AI**: Anthropic Claude API (`claude_adapter.py`)
- **Voice STT**: OpenAI Whisper (`whisper_adapter.py`)
- **Wake Word**: Picovoice Porcupine v4 (`porcupine_adapter.py`) — model file at `backend/models/Hey-Atlas_en_windows_v4_0_0.ppn`
- **TTS**: ElevenLabs (`elevenlabs_adapter.py`)
- **Vision**: Tesseract OCR (`tesseract_adapter.py`)
- **Database**: SQLite + SQLAlchemy async (`aiosqlite`)
- **Error monitoring**: Sentry (`infrastructure/monitoring/sentry.py`)

## Code Architecture

### Backend Clean Architecture

```
backend/src/
├── domain/                      # Business entities — no external dependencies
│   ├── entities/
│   │   ├── assistant_state.py   # AssistantMode enum + state transitions
│   │   ├── conversation.py
│   │   ├── message.py
│   │   └── screen_context.py
│   └── value_objects/
│
├── application/                 # Use cases (pure business logic)
│   ├── use_cases/
│   │   ├── analyze_screen.py
│   │   ├── offer_proactive_help.py
│   │   ├── process_chat_message.py
│   │   └── process_voice_command.py
│   └── interfaces/              # Abstract ports (ai_service, voice_service, screen_service, conversation_repository)
│
├── adapters/                    # Concrete implementations of interfaces
│   ├── ai/          → claude_adapter.py, openai_adapter.py
│   ├── voice/       → whisper_adapter.py, porcupine_adapter.py, elevenlabs_adapter.py
│   └── vision/      → tesseract_adapter.py
│
└── infrastructure/
    ├── api/routes/
    │   └── websocket.py         # Main WebSocket endpoint
    ├── websocket/
    │   └── manager.py           # WebSocketManager singleton
    ├── events/
    │   ├── event_bus.py         # EventBus singleton
    │   └── event_types.py       # Event name constants
    ├── loops/                   # ⚠️ Scaffold only — loop files NOT YET IMPLEMENTED
    ├── database/
    │   ├── models.py
    │   └── repositories/
    │       └── conversation_repository.py
    ├── monitoring/
    │   └── sentry.py
    └── config/
        ├── settings.py          # Pydantic Settings (reads from .env)
        └── master_prompt.py     # Claude system prompt
```

#### App startup (`backend/src/main.py`)
The FastAPI `lifespan` context manager wires everything together:
1. Initializes Sentry, SQLite, all adapters
2. Registers event handlers on the EventBus (user message → chat use case, audio → Whisper → ElevenLabs, screen frame → OCR → Claude)
3. Includes the WebSocket router at `/api` prefix
4. CORS allows `localhost:3000`, `localhost:5173`, and wildcard in dev

### Frontend Structure

```
frontend/src/
├── main/                        # Electron main process
│   ├── index.ts                 # App init, window creation
│   ├── tray.ts                  # System tray
│   └── capture.ts               # Screen capture service
│
├── renderer/                    # React UI (runs in Electron renderer)
│   ├── App.tsx
│   ├── components/
│   │   ├── Orb/
│   │   │   └── OrbCanvas.tsx    # Canvas particle animation
│   │   ├── Chat/
│   │   │   └── ChatInterface.tsx
│   │   └── ui/                  # shadcn-style UI primitives
│   ├── hooks/
│   │   ├── useWebSocket.ts
│   │   ├── useAudioCapture.ts
│   │   ├── useScreenCapture.ts
│   │   └── useTTSPlayer.ts
│   └── services/
│       └── websocket.ts         # WebSocketService singleton
│
└── preload/
    └── index.ts                 # Electron IPC bridge
```

## Key Concepts

### Assistant States
Six states drive both UI and backend behavior:
- **INACTIVE** → **ACTIVE** → **LISTENING** → **THINKING** → **SPEAKING**
- **PAUSED**: keeps wake word active, stops screen capture and conversation

### Wake Word Detection
Model file: `backend/models/Hey-Atlas_en_windows_v4_0_0.ppn` (Porcupine v4 — version must match)
Trigger phrases: "Hey Atlas", "Hello Atlas", "Hola Atlas", bare "Atlas"

### Event Bus System
Central nervous system of the backend. All singletons communicate through it:
```python
# Events defined in event_types.py:
wake_word_detected | screen_context_updated | error_detected
user_frustrated | conversation_message | state_changed
```

### Singleton Pattern
```python
# backend — module-level singletons
event_bus = EventBus()
ws_manager = WebSocketManager()
```
```typescript
// frontend
export const wsService = new WebSocketService();
```

## Environment Variables

Copy `backend/.env.example` → `backend/.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-...          # Required for Whisper STT
PICOVOICE_ACCESS_KEY=...       # Required for wake word
ELEVENLABS_API_KEY=...         # Optional TTS
DATABASE_URL=sqlite+aiosqlite:///./atlas.db
DEBUG=True
```

Frontend: `frontend/.env.local` (Vite env vars, `VITE_` prefix required)

## Visual Design

### Color Palette
```css
--bg-primary: #0D0D0D
--orb-cyan: #00D9FF
--orb-purple: #7B2FFF
--orb-pink: #FF006E
--accent-green: #00FFA3
--paused-amber: #FFA500
```

### Orb Animation States
- **INACTIVE**: slow particles, opacity 0.3
- **ACTIVE**: normal speed, bright
- **LISTENING**: fast particles, pulsing cyan
- **THINKING**: complex rotation, multicolor
- **SPEAKING**: synchronized pulses
- **PAUSED**: near-static, slow amber pulse

## Critical Notes

1. **`loops/` directory is a scaffold** — `wake_word_loop.py` / `screen_monitor_loop.py` are not yet implemented
2. **Porcupine must be v4** — matches the `.ppn` model file; do not change the version
3. **`npm run dev` runs Vite only** (browser preview) — full Electron shell requires `npm run build`
4. **No formal test suite yet** — `backend/test_claude.py` is a manual integration script; `backend/tests/` is an empty scaffold
5. **Comments in Spanish** for complex business logic (project convention)
6. **Do not use `setInterval` for animations** — use `requestAnimationFrame`

## Master System Prompt Principles

When modifying `master_prompt.py`:
- Conversational tone, not formal
- Use "veo que..." instead of "I have detected"
- Respond in same language as user (Spanish or English)
- Never invent information not visible on screen
- Explain errors simply and suggest solutions
