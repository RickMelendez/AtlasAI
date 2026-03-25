# Atlas AI Visual Companion

> An AI-powered visual assistant that sits beside you, watches your screen, listens to your voice, and converses naturally about what you both see.

[![Version](https://img.shields.io/badge/version-0.6.0--alpha-blue.svg)](https://github.com/RickMelendez/AtlasAI)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)

---

## What is Atlas?

Atlas is **not** a traditional chatbot. It's an **event-driven continuous system** — a living companion:

- Listens for your wake word ("Hey Atlas") at all times
- Watches your screen and understands context
- Speaks responses aloud with a natural voice
- Browses the web on your behalf using a real Chrome window
- Responds in the same language you use (English or Spanish)

---

## Features

### Animated Orb Interface
- Three.js particle sphere — 6 visual states driven by assistant state
- States: Inactive, Active, Listening, Thinking, Speaking, Paused
- Cyan → purple → pink gradient, 60 FPS smooth animation
- Glow effect reacts to voice and speaking

### Voice Pipeline
- **Wake word**: "Hey Atlas" / "Hello Atlas" / "Hola Atlas" (OpenWakeWord)
- **STT**: Faster Whisper (local, no API key required)
- **TTS**: ElevenLabs (priority 1) → Fish Audio (priority 2) → Edge-TTS free fallback
- Voice Activity Detection (VAD) auto-triggers recording

### Screen Vision
- Screen capture every 3 seconds when active
- App context detection (VS Code, browsers, terminal, etc.)
- Vision analysis via Claude

### Web Browsing
- Atlas can navigate to URLs in a real Chromium window (Playwright)
- Click, type, and read page content
- Screenshots sent back to Atlas for context

### AI
- Powered by **Anthropic Claude** (claude-sonnet model)
- Context-aware responses based on what's visible on screen
- Conversational tone — not a formal assistant

---

## Architecture

### Event-Driven Design

```
WebSocket always open
  ↓
Backend:
  • Wake word detection (continuous)
  • Screen monitoring (every 3s when ACTIVE)
  • Voice → Whisper STT → Claude → ElevenLabs TTS
  • Proactive suggestions

REST:
  • POST /activate
  • POST /pause
  • GET /status
```

### Clean Architecture

```
frontend/                    Electron + React
  ├── Orb (Three.js)
  ├── Chat panel
  ├── WebSocket client
  └── Audio capture (VAD)
         │
         │  WebSocket
         ▼
backend/src/
  ├── domain/               Business entities (no dependencies)
  ├── application/          Use cases + interfaces (ports)
  ├── adapters/             Concrete implementations
  │   ├── ai/               claude_adapter.py
  │   ├── voice/            faster_whisper, elevenlabs, fish_audio, edge_tts, open_wake_word
  │   └── web/              playwright_adapter.py
  └── infrastructure/
      ├── websocket/        WebSocketManager singleton
      ├── events/           EventBus singleton
      └── config/           settings.py, master_prompt.py
```

---

## Tech Stack

### Frontend
- Electron 28, React 18, TypeScript 5
- Three.js (orb animation)
- TailwindCSS
- Zustand (state)
- Vite

### Backend
- Python 3.11+, FastAPI, uvicorn
- Anthropic Claude API
- Faster Whisper (local STT)
- OpenWakeWord (wake word detection)
- ElevenLabs / Fish Audio / Edge-TTS (TTS chain)
- Playwright (web browser automation)
- SQLite + SQLAlchemy async

---

## Installation

### Prerequisites

- Node.js 18+
- Python 3.11+
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

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt

# Install Playwright browser
playwright install chromium
```

### 3. Frontend

```bash
cd frontend
npm install
```

### 4. Environment Variables

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env` — required keys:

```env
# AI (required)
ANTHROPIC_API_KEY=sk-ant-...

# TTS — at least one recommended (Edge-TTS works with no key)
ELEVENLABS_API_KEY=...
# ELEVENLABS_VOICE_ID=   # optional override

# App
APP_NAME=Atlas AI
DEBUG=True
```

Get API keys:
- Anthropic: https://console.anthropic.com/
- ElevenLabs: https://elevenlabs.io/

---

## Running

### Quick start (Windows)

```batch
.\dev.bat
```

Opens two terminal windows — backend and frontend.

### Manual

```bash
# Backend
cd backend
venv\Scripts\activate
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd frontend
npm run dev
```

---

## Usage

| Action | How |
|---|---|
| Activate | Say "Hey Atlas" or click the orb |
| Talk | Speak naturally — VAD triggers automatically |
| Pause | Say "pause" or "stop" |
| Resume | Say "continue" or "Hey Atlas" |
| Browse | Say "open youtube.com" — Chrome window appears |

---

## Project Structure

```
AtlasAI/
├── backend/
│   ├── src/
│   │   ├── domain/              entities, value objects
│   │   ├── application/         use cases, interfaces
│   │   ├── adapters/
│   │   │   ├── ai/              claude_adapter.py
│   │   │   ├── voice/           whisper, wake word, TTS adapters
│   │   │   └── web/             playwright_adapter.py
│   │   └── infrastructure/
│   │       ├── api/routes/      websocket.py
│   │       ├── websocket/       manager.py
│   │       ├── events/          event_bus.py, event_types.py
│   │       └── config/          settings.py, master_prompt.py
│   ├── models/                  wake word model (.ppn)
│   ├── requirements.txt
│   └── .env
│
├── frontend/
│   ├── src/
│   │   ├── main/                Electron main process
│   │   └── renderer/
│   │       ├── components/
│   │       │   ├── Orb/         NeuralOrb.tsx, OrbCanvas.css
│   │       │   └── Chat/        ChatInterface.tsx
│   │       ├── hooks/           useAudioCapture, useTTSPlayer, useWebSocket
│   │       └── services/        websocket.ts
│   └── package.json
│
├── docs/
│   └── architecture.drawio
├── dev.bat                      Windows quick-start
├── CLAUDE.md                    Instructions for Claude Code
└── README.md
```

---

## Orb States

| State | Visual |
|---|---|
| INACTIVE | Slow dim particles |
| ACTIVE | Bright cyan, ready |
| LISTENING | Fast pulsing cyan |
| THINKING | Multicolor rotation |
| SPEAKING | Synchronized radial pulses |
| PAUSED | Near-static amber |

---

## Color Palette

```css
--bg-primary: #0D0D0D
--orb-cyan:   #00D9FF
--orb-purple: #7B2FFF
--orb-pink:   #FF006E
--accent:     #00FFA3
--paused:     #FFA500
```

---

## Development

```bash
# Backend quality
black .
isort .
mypy src/

# Frontend quality
npm run lint
npm run type-check
```

---

## License

MIT

---

## Credits

- [Anthropic](https://anthropic.com) — Claude AI
- [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) — local STT
- [OpenWakeWord](https://github.com/dscripka/openWakeWord) — wake word detection
- [ElevenLabs](https://elevenlabs.io) — neural TTS
- [Playwright](https://playwright.dev) — browser automation
- [Three.js](https://threejs.org) — 3D orb animation

---

<div align="center">
Built with Clean Architecture + Event-Driven Design
</div>
