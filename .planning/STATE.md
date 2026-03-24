# Project State

**Last updated:** 2026-03-24
**Current milestone:** Milestone 1 — Atlas v1.0 MVP
**Active phase:** Phase 1 not started
**Status:** 🟡 Initialized — ready to execute Phase 1

---

## Current Position

```
Milestone 1: Atlas v1.0 MVP
  ◻ Phase 1: Ship-Blocking Fixes       ← START HERE
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

1. **PORT BUG**: `frontend/src/renderer/services/websocket.ts:36` — `ws://localhost:8001` should be `ws://localhost:8000`
2. **DB NOT WIRED**: `SQLiteConversationRepository` fully implemented but never injected into use cases
3. **Playwright leak**: Browser contexts not cleaned up on session disconnect
4. **Misleading name**: `wake_word_loop()` in `manager.py` handles ALL message types, not just wake word

---

## Next Action

Run `/gsd:plan-phase 1` to create the detailed execution plan for Phase 1.

---

## GSD Config

- Mode: YOLO (auto-approve)
- Depth: Standard
- Parallelization: true
- Research: enabled
- Plan check: enabled
- Verifier: enabled
- Model: Balanced (Sonnet)
