# Project State

**Last updated:** 2026-03-24
**Current milestone:** Milestone 1 — Atlas v1.0 MVP
**Active phase:** Phase 1 — Ship-Blocking Fixes (Plans 01, 02, 03 complete)
**Status:** Phase 1 execution complete — all ship-blocking fixes applied

---

## Current Position

```
Milestone 1: Atlas v1.0 MVP
  ▶ Phase 1: Ship-Blocking Fixes       ← Plans 01-03 complete (plan 04+ TBD)
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
2. ~~**DB NOT WIRED**: `SQLiteConversationRepository` fully implemented but never injected into use cases~~ **FIXED in Plan 02** (commit e9ae126)
3. ~~**Playwright leak**: Browser contexts not cleaned up on session disconnect~~ **FIXED in Plan 03** (commit e9ae126)
4. ~~**Misleading name**: `wake_word_loop()` in `manager.py` handles ALL message types, not just wake word~~ **FIXED in Plan 03** (commit e9ae126)

---

## Decisions Log

- **2026-03-24 (01-01):** Fixed WebSocket port typo in constructor default parameter only — no reconnect logic or event handler changes. JSDoc comment updated alongside code to keep documentation accurate.
- **2026-03-24 (01-02):** Added `conversation_history` param to `ProcessChatMessageUseCase.execute()` and forwarded to `ClaudeAdapter.generate_response()` (which already accepted it but was never populated). Two independent short-lived sessions used for history load and save — no long-lived session held across awaits. DB errors wrapped in try/except so failures never block user response.
- **2026-03-24 (01-03):** Playwright cleanup guarded by hasattr check to survive None tool executor during tests/early startup. DB persistence placed after TTS send so audio is never delayed by DB I/O. DB errors swallowed with logger.error — TTS already sent, pipeline must not fail retro-actively. screen_monitor_loop confirmed no-op (body was only asyncio.sleep(3)) — removed without behavior regression.

---

## Last Session

**Stopped at:** Completed 01-ship-blocking-fixes/01-03-PLAN.md
**Session date:** 2026-03-24

---

## Next Action

Check if Phase 1 has additional plans beyond 01-03, then move to Phase 2 or continue Phase 1.

---

## GSD Config

- Mode: YOLO (auto-approve)
- Depth: Standard
- Parallelization: true
- Research: enabled
- Plan check: enabled
- Verifier: enabled
- Model: Balanced (Sonnet)
