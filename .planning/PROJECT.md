# Atlas AI Visual Companion

## What This Is

Atlas AI is an always-on AI-powered desktop companion that lives in your system tray as an animated orb. It observes your screen, listens for your voice via "Hey Atlas" wake word, and converses naturally about what you're both seeing — like a tech-savvy friend sitting beside you. Built with Electron + React frontend and a Python FastAPI event-driven backend.

## Core Value

Atlas must hear "Hey Atlas", understand what's on your screen, and give you a useful response — the continuous loop that makes it feel alive, not like a chatbot you open tabs to use.

## Requirements

### Validated

- ✓ Event-driven WebSocket backend with continuous loops (wake_word_loop, screen_monitor_loop) — existing
- ✓ Particle orb animation with 6 visual states (INACTIVE/ACTIVE/LISTENING/THINKING/SPEAKING/PAUSED) at 60fps — existing
- ✓ Claude claude-sonnet-4-6 integration with 11-tool agentic loop (browse_web, terminal, files, Notion) — existing
- ✓ Voice pipeline: Whisper STT + ElevenLabs TTS + Porcupine wake word (Whisper fallback) — existing
- ✓ Screen vision via Claude Haiku Vision (10s debounced) — existing
- ✓ Playwright headless browser automation per-session — existing
- ✓ Notion integration (search, read, create pages) — existing
- ✓ Electron desktop app: system tray, IPC bridge, always-on-top orb, drag support — existing
- ✓ SQLite database layer with async SQLAlchemy (Conversation, Message, ScreenContext models) — existing
- ✓ Fast router: 0ms deterministic routing for known sites/commands — existing
- ✓ Auto language detection EN/ES per message — existing
- ✓ Sentry error monitoring frontend + backend — existing
- ✓ CORS + health check endpoint — existing

### Active

**MVP Gap Closure (fix remaining 15%):**
- [ ] Wire conversation persistence to DB (ConversationRepository connected to use cases)
- [ ] Unit test suite: pytest for domain entities, use cases, tool executor
- [ ] Session restore on WebSocket reconnect (no history loss on backend restart)
- [ ] Settings UI: API key management, voice/language prefs, capture interval
- [ ] Playwright browser context cleanup on session disconnect
- [ ] Rename wake_word_loop → handle_messages (clarify naming)

**New Features:**
- [ ] Global hotkeys (activate/deactivate, push-to-talk)
- [ ] Multi-monitor support (detect screens, capture specific monitor)
- [ ] Long-term memory across sessions (SQLite-backed conversation search)
- [ ] Voice output improvements: voice selection UI, ElevenLabs voice preview
- [ ] Screen capture auto-start when assistant activates (not just on chat open)

### Out of Scope

- Voice cloning — high complexity, not core to v1 value
- Plugin/extension system — premature abstraction
- Mobile app — desktop-first, mobile is v3+
- Real-time multi-user — single-user companion
- Calendar/todos integration — out of focus for v1
- Web deployment — Electron desktop only

## Context

- **Platform**: Windows 11 primary (Electron build), macOS + Linux in build config
- **Wake word**: Picovoice Porcupine v4 model at `backend/models/Hey-Atlas_en_windows_v4_0_0.ppn` — version must match library
- **Whisper fallback**: When no Picovoice key, Whisper checks 3s PCM clips for "atlas" keyword
- **Vision**: Tesseract adapter exists but superseded by Claude Haiku Vision — Tesseract not required
- **STATUS.md is stale**: References Tesseract as active OCR and marks DB layer as incomplete — both wrong
- **loops/ scaffold**: Loop logic lives in `manager.py`, not in separate loop files as the directory implies
- **Conversation history not wired**: DB models and repository exist but `ProcessChatMessageUseCase` doesn't use them
- **Port discrepancy**: Frontend WebSocket connects to `ws://localhost:8001` but backend runs on port 8000

## Constraints

- **Tech stack**: Python 3.13 + FastAPI backend, Electron 28 + React 18 + TypeScript 5 frontend — no stack changes
- **Porcupine**: Must remain v4 — model file version is locked
- **Animation**: `requestAnimationFrame` only, never `setInterval` — project rule
- **Comments**: Complex business logic in Spanish — project convention
- **Claude model**: `claude-sonnet-4-6` for chat, Haiku for vision — balance cost/quality

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Claude Vision over Tesseract | No Windows install required, better accuracy | ✓ Good |
| Whisper wake-word fallback | Works without Picovoice key | ✓ Good |
| Fast router before Claude | 0ms for known commands vs ~2s LLM roundtrip | ✓ Good |
| asyncio.create_task for voice pipeline | Non-blocking — prevents WebSocket keepalive timeouts | ✓ Good |
| In-memory conversation history | Shipped fast, DB layer exists but not wired | ⚠️ Revisit — wire up next |
| Wake word loop handles all messages | Originally just wake word, grew to all message types | ⚠️ Revisit — rename for clarity |

---
*Last updated: 2026-03-23 after brownfield initialization*
