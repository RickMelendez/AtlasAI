# 🌟 Atlas AI Visual Companion

> An AI-powered visual assistant that functions as a tech-savvy companion sitting beside you, observing your screen, listening to your voice, and conversing naturally about what you both see.

[![Version](https://img.shields.io/badge/version-0.5.0--alpha-blue.svg)](https://github.com/yourusername/atlas-ai)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)
[![Progress](https://img.shields.io/badge/progress-75%25-yellow.svg)](STATUS.md)

---

## 📖 What is Atlas?

Atlas is **NOT** a traditional chatbot. It's an **event-driven continuous system** that operates like a living companion:

- 🎤 **Always listening** for "Hey Atlas" wake word
- 👁️ **Always watching** your screen (when active)
- 💬 **Naturally conversing** about what you both see
- 🔮 **Proactively helping** without being asked

**Think of it as:** A tech-savvy friend sitting beside you, ready to help when you need it.

---

## ✨ Key Features

### 🔮 Animated Orb Interface
- Particle sphere with 500-800 particles
- 6 visual states (Inactive, Active, Listening, Thinking, Speaking, Paused)
- Beautiful gradients: cyan → purple → pink
- 60 FPS smooth animation

### 🎤 Voice Control
- **Wake word detection**: "Hey Atlas" / "Hola Atlas"
- **Voice commands**: activate, pause, continue, deactivate
- **Natural conversation**: Speak naturally, Atlas understands context
- **Bilingual**: Spanish and English support

### 👁️ Screen Vision
- Captures screen every 3 seconds when active
- OCR text extraction with Tesseract
- App context detection (VS Code, browsers, terminal, etc.)
- Error detection (TypeScript, Python, HTTP errors, etc.)

### 🤖 AI-Powered Responses
- Powered by **Anthropic Claude 3.5 Sonnet**
- Contextual responses based on what it sees
- Conversational tone (like a friend, not a bot)
- Concise, actionable suggestions

### 🎯 Proactive Assistance
- Detects errors on screen
- Offers help without being asked
- Context-aware suggestions
- Non-intrusive design

### ⏸️ Focus Mode
- Pause with "pause" or "stop"
- Screen capture stops
- Resume with "continue" or "Hey Atlas"
- Visual feedback (amber orb)

---

## 🏗️ Architecture

### Event-Driven Design

**Traditional API (Wrong):**
```
User speaks → POST /chat → Response → END
```

**Atlas (Correct):**
```
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

### Clean Architecture

```
┌─────────────────────────────────────────┐
│         Frontend (Electron + React)      │
│  • Orb Animation (Canvas API)            │
│  • Audio Recording                       │
│  • Screen Capture                        │
│  • WebSocket Client                      │
└──────────────┬──────────────────────────┘
               │ WebSocket
┌──────────────▼──────────────────────────┐
│         Backend (FastAPI + Python)       │
│                                          │
│  ┌────────────────────────────────┐     │
│  │  WebSocket Manager              │     │
│  │  • Connection handling          │     │
│  │  • Continuous loops             │     │
│  └────────────────────────────────┘     │
│                                          │
│  ┌────────────────────────────────┐     │
│  │  Event Bus                      │     │
│  │  • Internal communication       │     │
│  └────────────────────────────────┘     │
│                                          │
│  ┌────────────────────────────────┐     │
│  │  Domain Layer                   │     │
│  │  • AssistantState (6 modes)     │     │
│  │  • Business logic               │     │
│  └────────────────────────────────┘     │
│                                          │
│  ┌────────────────────────────────┐     │
│  │  Adapters                       │     │
│  │  • Claude (AI)                  │     │
│  │  • Whisper (voice → text)       │     │
│  │  • Porcupine (wake word)        │     │
│  │  • Tesseract (OCR)              │     │
│  └────────────────────────────────┘     │
└─────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

### Frontend
- **Runtime**: Electron 28+
- **Framework**: React 18 + TypeScript 5
- **Styling**: TailwindCSS + CSS Modules
- **Animation**: Canvas API (particle system)
- **State**: Zustand
- **Build**: Vite
- **WebSocket**: Native WebSocket API

### Backend
- **Runtime**: Python 3.11+
- **Framework**: FastAPI
- **Architecture**: Clean Architecture (Domain → Application → Infrastructure)
- **WebSocket**: FastAPI WebSocket support
- **Event Bus**: Custom async event emitter
- **AI**: Anthropic Claude 3.5 Sonnet
- **Voice**: OpenAI Whisper (transcription), Picovoice Porcupine (wake word)
- **Vision**: Tesseract OCR
- **Database**: SQLite + SQLAlchemy (planned)

---

## 🚀 Installation

### Prerequisites

- **Node.js** 18+ and npm
- **Python** 3.11+
- **Git**
- **Tesseract OCR** (for screen vision)

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/atlas-ai-companion.git
cd atlas-ai-companion
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows Git Bash)
source venv/Scripts/activate

# Or Windows CMD
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install
```

### 4. Install Tesseract OCR

**Windows:**
Download and install from: https://github.com/UB-Mannheim/tesseract/wiki

**Mac:**
```bash
brew install tesseract
```

**Linux:**
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-spa
```

### 5. Configure Environment Variables

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env`:

```env
# AI Services (Required)
ANTHROPIC_API_KEY=sk...
OPENAI_API_KEY=sk-...

# Voice Output (Optional)
ELEVENLABS_API_KEY=...

# App Configuration
APP_NAME=Atlas AI
DEBUG=True
```

**Get API Keys:**
- Anthropic: https://console.anthropic.com/
- OpenAI: https://platform.openai.com/api-keys
- ElevenLabs: https://elevenlabs.io/

---

## 🎯 Usage

### Start Backend

```bash
cd backend
source venv/Scripts/activate  # Windows: venv\Scripts\activate
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at: `http://localhost:8000`

### Start Frontend

In a separate terminal:

```bash
cd frontend
npm run dev
```

The Electron app will launch automatically.

### Interacting with Atlas

1. **Activate Atlas:**
   - Say "Hey Atlas" (wake word)
   - Or click the system tray icon → "Show Orb"
   - Or click the orb

2. **Talk to Atlas:**
   - Speak naturally
   - Atlas sees your screen and responds in context

3. **Pause (Focus Mode):**
   - Say "pause" or "stop"
   - Orb turns amber
   - Screen capture stops

4. **Resume:**
   - Say "continue" or "Hey Atlas"
   - Orb returns to cyan

5. **Deactivate:**
   - Say "deactivate"
   - Orb goes to sleep

---

## 📁 Project Structure

```
AtlasAI/
├── backend/                          # Python FastAPI
│   ├── src/
│   │   ├── domain/                  # Business entities
│   │   │   ├── entities/
│   │   │   │   ├── assistant_state.py    # 6 states (INACTIVE, ACTIVE, ...)
│   │   │   │   ├── conversation.py
│   │   │   │   └── screen_context.py
│   │   │   └── value_objects/
│   │   │
│   │   ├── application/             # Use cases (business logic)
│   │   │   ├── use_cases/
│   │   │   │   ├── process_voice_command.py
│   │   │   │   ├── analyze_screen.py
│   │   │   │   ├── generate_response.py
│   │   │   │   └── offer_proactive_help.py
│   │   │   └── interfaces/          # Port definitions
│   │   │
│   │   ├── adapters/                # External integrations
│   │   │   ├── ai/
│   │   │   │   └── claude_adapter.py
│   │   │   ├── voice/
│   │   │   │   ├── whisper_adapter.py
│   │   │   │   └── porcupine_adapter.py
│   │   │   └── vision/
│   │   │       └── tesseract_adapter.py
│   │   │
│   │   ├── infrastructure/
│   │   │   ├── api/
│   │   │   │   └── routes/
│   │   │   │       ├── assistant.py
│   │   │   │       └── websocket.py
│   │   │   ├── websocket/
│   │   │   │   └── manager.py           # WebSocket manager (singleton)
│   │   │   ├── events/
│   │   │   │   ├── event_bus.py         # Event Bus (singleton)
│   │   │   │   └── event_types.py
│   │   │   └── config/
│   │   │       ├── settings.py
│   │   │       └── master_prompt.py
│   │   │
│   │   └── main.py                      # FastAPI app entry point
│   │
│   ├── requirements.txt
│   └── .env
│
├── frontend/                             # Electron + React
│   ├── src/
│   │   ├── main/                        # Electron main process
│   │   │   ├── index.ts                 # App initialization
│   │   │   ├── tray.ts                  # System tray
│   │   │   └── capture.ts               # Screen capture
│   │   │
│   │   ├── renderer/                    # React UI
│   │   │   ├── components/
│   │   │   │   ├── Orb/
│   │   │   │   │   ├── OrbCanvas.tsx    # Particle animation
│   │   │   │   │   └── OrbCanvas.css
│   │   │   │   ├── Chat/
│   │   │   │   │   ├── ChatInterface.tsx
│   │   │   │   │   └── Message.tsx
│   │   │   │   └── Settings/
│   │   │   │
│   │   │   ├── hooks/
│   │   │   │   ├── useWebSocket.ts
│   │   │   │   └── useVoice.ts
│   │   │   │
│   │   │   ├── services/
│   │   │   │   └── websocket.ts         # WebSocket service (singleton)
│   │   │   │
│   │   │   └── store/
│   │   │       └── assistant-store.ts   # Zustand state
│   │   │
│   │   └── preload/
│   │       └── index.ts                 # IPC bridge
│   │
│   └── package.json
│
├── CLAUDE.md                             # Instructions for Claude Code
├── README.md                             # This file
└── STATUS.md                             # Current progress & next steps
```

---

## 🎨 Visual Design

### Color Palette

```css
--bg-primary: #0D0D0D        /* Almost black */
--orb-cyan: #00D9FF          /* Cyan brilliant */
--orb-purple: #7B2FFF        /* Purple */
--orb-pink: #FF006E          /* Pink */
--accent-green: #00FFA3      /* Green cyan */
--text-primary: #E0E0E0      /* Light gray */
--text-secondary: #8A8A8A    /* Medium gray */
--paused-amber: #FFA500      /* Amber for paused state */
```

### Orb States

| State | Visual | Behavior |
|---|---|---|
| **INACTIVE** | Slow particles, dim colors (opacity 0.3) | Off, not listening |
| **ACTIVE** | Normal speed, bright cyan | Ready for conversation |
| **LISTENING** | Fast particles, pulsing cyan | Recording user's voice |
| **THINKING** | Complex rotation, multicolor | Processing with AI |
| **SPEAKING** | Synchronized pulses | Delivering response |
| **PAUSED** | Almost static, slow amber pulse | Focus mode - no screen capture |

---

## 🔑 Key Concepts

### Assistant States

Atlas has 6 distinct modes managed by `AssistantState`:

```python
class AssistantMode(Enum):
    INACTIVE = "inactive"      # Off, not listening
    ACTIVE = "active"          # Ready for conversation
    LISTENING = "listening"    # Recording user's voice
    THINKING = "thinking"      # Processing with AI
    SPEAKING = "speaking"      # Delivering response
    PAUSED = "paused"          # Focus mode
```

### Wake Word Detection

Listens continuously for:
- "Hey Atlas" / "Hello Atlas" / "Hola Atlas"
- "Atlas" (alone or in context)
- Commands: "activate", "pause", "continue", "deactivate"

### Screen Monitoring

When ACTIVE:
- Captures screen every 3 seconds
- Extracts text with Tesseract OCR
- Detects app context (VS Code, browsers, terminal)
- Identifies errors and issues
- Sends context to Claude for intelligent responses

### Event Bus System

Internal communication via events:
- `wake_word_detected`
- `screen_context_updated`
- `error_detected`
- `user_frustrated`
- `conversation_message`
- `state_changed`

---

## 🧪 Development

### Running Tests

```bash
# Backend tests
cd backend
pytest
pytest --cov=src tests/

# Frontend tests
cd frontend
npm test
```

### Code Quality

```bash
# Backend
black .
isort .
mypy src/

# Frontend
npm run lint
npm run type-check
```

### Development Principles

1. **Clean Architecture**: Strict separation of concerns
2. **Event-Driven**: Communication based on events
3. **Type Safety**: TypeScript strict + Python type hints
4. **Error Handling**: Comprehensive try-catch/try-except
5. **Testing**: Unit tests + Integration tests

---

## 📊 Current Status

**Version**: 0.5.0 Alpha
**Progress**: 75% Complete

See [STATUS.md](STATUS.md) for detailed progress tracking.

### What's Working ✅
- Backend FastAPI server
- WebSocket infrastructure
- Event Bus system
- Orb animation (60 FPS)
- State management
- Voice command detection (implementation ready)
- Screen capture (implementation ready)

### What's Blocked ⚠️
- **Anthropic API**: Credits depleted (blocking AI responses)
- **Tesseract OCR**: Needs Windows installation (blocking screen vision)

---

## 🐛 Troubleshooting

### Backend won't start

```bash
# Check Python version
python --version  # Should be 3.11+

# Reinstall dependencies
pip install -r requirements.txt

# Check environment variables
cat .env  # Linux/Mac
type .env  # Windows
```

### Frontend won't start

```bash
# Clear node_modules
rm -rf node_modules
npm install

# Clear cache
npm cache clean --force
```

### WebSocket connection fails

```bash
# Verify backend is running
curl http://localhost:8000/health

# Check CORS settings in backend/src/main.py
# Should allow localhost:5173 (Vite default port)
```

### Orb animation is laggy

- Reduce particle count in `OrbCanvas.tsx` (default 500-800)
- Check browser console for performance warnings
- Ensure using `requestAnimationFrame`, not `setInterval`

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the project
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Contribution Guidelines

- Follow Clean Architecture principles
- Write tests for new features
- Document complex logic in Spanish
- Use TypeScript strict / Python type hints
- Keep code simple and readable

---

## 📄 License

This project is licensed under the MIT License.

---

## 🙏 Credits

- **Anthropic** - Claude AI
- **OpenAI** - Whisper
- **Tesseract** - OCR Engine
- Inspired by the vision of ambient AI assistants

---

<div align="center">

**Built with ❤️ using Clean Architecture + Event-Driven Design**

[⬆ Back to top](#-atlas-ai-visual-companion)

</div>
