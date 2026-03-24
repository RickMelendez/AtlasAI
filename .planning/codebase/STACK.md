# STACK.md — Atlas AI Technology Stack

## Overview

Full-stack desktop AI assistant. Python backend + Electron/React frontend communicating via persistent WebSocket.

---

## Backend

### Runtime & Language
- **Python 3.13** (inferred from `.mypy_cache/3.13/`)
- **Async-first**: `asyncio` throughout, `await` on all I/O

### Framework
- **FastAPI** — ASGI web framework
- **uvicorn** — ASGI server (`uvicorn src.main:app --reload`)
- **Pydantic Settings** (`pydantic-settings`) — env/config management

### AI / LLM
- **Anthropic SDK** (`anthropic`) — `AsyncAnthropic`, model `claude-sonnet-4-6`
  - Tool use loop (up to 10 iterations)
  - Streaming support via `messages.stream()`
  - Retry on 529 overloaded (exponential backoff, 3 attempts)
- Mock mode via `ANTHROPIC_MOCK=1` env var

### Voice
- **OpenAI Whisper** (`openai`) — STT (`whisper-1` model, auto language detect)
- **Picovoice Porcupine v4** (`pvporcupine`) — wake word detection
  - Model file: `backend/models/Hey-Atlas_en_windows_v4_0_0.ppn`
  - Fallback: Whisper-based wake word detection when no Porcupine key
- **ElevenLabs** (`elevenlabs`) — TTS, voice ID `onwK4e9ZLuTAKqWW03F9` (Daniel, British male)

### Vision
- **Claude Haiku Vision** (`claude_vision_adapter.py`) — primary screen analysis (replaces Tesseract)
  - Debounced to 10s max rate
  - Returns `last_screen_description`
- **Tesseract OCR** (`pytesseract`) — legacy, still present but superseded

### Web Automation
- **Playwright** (`playwright_adapter.py`) — headless browser for `browse_web`, `click_element`, `type_text`, `get_page_content`
  - Per-session browser contexts
  - Started/stopped in FastAPI lifespan

### Database
- **SQLite** via `aiosqlite` + **SQLAlchemy async**
  - URL: `sqlite+aiosqlite:///./atlas.db`
  - Models: Conversation, Message, ScreenContext
  - Auto-created via `init_db()` on startup

### Integrations
- **Notion API** (`notion_adapter.py`) — search, read, create pages
- **Sentry** (`sentry-sdk`) — error monitoring, initialized before app startup

### Code Quality
- `black` — formatter
- `isort` — import ordering
- `mypy` — type checking

---

## Frontend

### Runtime
- **Electron 28** — desktop shell (Windows primary target, mac/linux in build config)
- **Node.js** — build tooling

### UI Framework
- **React 18** + **TypeScript 5.3**
- **Vite 5** — dev server + build tool (`vite-plugin-electron` + `vite-plugin-electron-renderer`)

### Styling
- **TailwindCSS 3.4** — utility classes
- **shadcn/ui** pattern (`components.json`) — component primitives in `src/renderer/components/ui/`
- `class-variance-authority`, `clsx`, `tailwind-merge`

### State
- **Zustand 4.4** — global state store

### Animation
- **Canvas API** — particle orb (`OrbCanvas.tsx`), `requestAnimationFrame` at 60fps
- No `setInterval` for animations (project rule)

### Icons
- `lucide-react 0.577`

### Error Monitoring
- `@sentry/react 8.55` — frontend Sentry (`src/renderer/sentry.ts`)

### Build Output
- `dist-electron/` — compiled Electron main process
- `release/{version}/` — packaged app
- Windows: NSIS installer (x64), `.ico` at `public/assets/icons/orb-icon.ico`
- Mac: DMG
- Linux: AppImage

---

## Dev Tooling

| Tool | Purpose |
|---|---|
| `dev.bat` | Opens two CMD windows (backend + frontend) |
| `uvicorn --reload` | Backend hot-reload on `.py` changes |
| `vite dev` | Frontend hot-reload (browser preview only, no Electron) |
| `electron-builder` | Full Electron packaging |
| `eslint` + `@typescript-eslint` | Frontend linting |
| `tsc --noEmit` | TypeScript type check |

---

## Environment Variables (`backend/.env`)

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude API |
| `OPENAI_API_KEY` | ✅ | Whisper STT |
| `PICOVOICE_ACCESS_KEY` | ⚠️ Optional | Wake word (Porcupine) |
| `ELEVENLABS_API_KEY` | ⚠️ Optional | TTS voice output |
| `NOTION_API_KEY` | ⚠️ Optional | Notion integration |
| `SENTRY_DSN` | ⚠️ Optional | Error monitoring |
| `DATABASE_URL` | Default | `sqlite+aiosqlite:///./atlas.db` |
| `DEBUG` | Default `True` | Dev/prod mode |
| `ANTHROPIC_MOCK` | Test | `1` = offline mock mode |

Frontend: `frontend/.env.local` — `VITE_` prefixed vars (Vite convention)
