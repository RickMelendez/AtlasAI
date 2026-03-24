# Project State

**Last updated:** 2026-03-24
**Current milestone:** Milestone 1 — Atlas v1.0 MVP
**Active phase:** Phase 1 — Ship-Blocking Fixes (Plan 01 complete)
**Status:** 🟢 Executing Phase 1 — Plan 01 complete, Plan 02+ pending

---

## Current Position

```
Milestone 1: Atlas v1.0 MVP
  ▶ Phase 1: Ship-Blocking Fixes       ← IN PROGRESS (Plan 01/0N complete)
  ◻ Phase 2: Offline Resilience + Tests
  ◻ Phase 3: Settings UI + Voice UX
  ◻ Phase 4: Local AI + Long-term Memory
```

---

## What Was Done Before Initialization

Atlas AI v0.6 alpha was built (~85% complete):
- ✅ Event-driven WebSocket backend with continuous loops
- ✅ Particle orb animation (6 states, 60fps, Canvas/requestAnimationFrame)
- ✅ Claude claude-sonnet-4-6 with 11-tool agentic loop (browser, terminal, files, Notion)
- ✅ Voice pipeline: Whisper STT + ElevenLabs TTS + Porcupine wake word (Whisper fallback)
- ✅ Screen vision via Claude Haiku Vision (10s debounced)
- ✅ Playwright headless browser per session
- ✅ SQLite DB layer with async SQLAlchemy (models + repository — NOT YET WIRED)
- ✅ Fast router (0ms for known sites/commands)
- ✅ Sentry monitoring frontend + backend
- ✅ GitHub repo initialized and pushed to https://github.com/RickMelendez/AtlasAI.git

---

## Known Issues to Fix in Phase 1

1. ~~**PORT BUG**: `frontend/src/renderer/services/websocket.ts:36` — `ws://localhost:8001` should be `ws://localhost:8000`~~ **FIXED in Plan 01** (commit 9139b56)
2. **DB NOT WIRED**: `SQLiteConversationRepository` fully implemented but never injected into use cases
3. **Playwright leak**: Browser contexts not cleaned up on session disconnect
4. **Misleading name**: `wake_word_loop()` in `manager.py` handles ALL message types, not just wake word

---

## Decisions Log

- **2026-03-24 (01-01):** Fixed WebSocket port typo in constructor default parameter only — no reconnect logic or event handler changes. JSDoc comment updated alongside code to keep documentation accurate.

---

## Next Action

Execute Phase 1 Plan 02 (DB wiring or next plan in sequence).

---

## GSD Config

- Mode: YOLO (auto-approve)
- Depth: Standard
- Parallelization: true
- Research: enabled
- Plan check: enabled
- Verifier: enabled
- Model: Balanced (Sonnet)
