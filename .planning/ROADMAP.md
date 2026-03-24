# Roadmap: Atlas AI Visual Companion v1.0

**Created:** 2026-03-24
**Target:** Ship MVP v1.0 — the always-on AI companion that actually works end-to-end

---

## Milestone 1: Atlas v1.0 MVP

### Phase 1: Ship-Blocking Fixes
**Goal:** Atlas works end-to-end — WebSocket connects, conversations persist, no critical bugs

| # | Task | File(s) | Notes |
|---|------|---------|-------|
| 1 | Fix WebSocket port 8001→8000 | `frontend/src/renderer/services/websocket.ts:36` | 1 char — frontend has never connected |
| 2 | Wire conversation persistence to DB | `process_chat_message.py`, `process_voice_command.py`, `main.py` | Repo exists, not injected |
| 3 | Playwright browser context cleanup on disconnect | `playwright_adapter.py` | Orphan browser contexts on reconnect |
| 4 | Rename `wake_word_loop` → `handle_messages` | `manager.py` | Clarity — it handles all message types |
| 5 | Remove no-op `screen_monitor_loop` or give it real behavior | `manager.py` | Currently just `asyncio.sleep(3)` |

**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md — Fix WebSocket port 8001→8000 in websocket.ts (commit 9139b56, 2026-03-24)
- [ ] 01-02-PLAN.md — Wire DB persistence into text chat path (main.py)
- [ ] 01-03-PLAN.md — manager.py: Playwright cleanup + rename loop + remove no-op + voice persistence

**Success criteria:**
- Frontend "connected" dot goes green immediately
- Chat history survives backend restart
- No orphan Playwright contexts after 10 reconnects

---

### Phase 2: Offline Resilience + Test Suite
**Goal:** Atlas works without OpenAI API key; codebase has a safety net

| # | Task | File(s) | Notes |
|---|------|---------|-------|
| 1 | Add `VoskAdapter` for offline STT | `backend/src/adapters/voice/vosk_adapter.py` (new) | Apache 2.0, ~50MB model, no API key |
| 2 | Conditional STT init in main.py | `main.py` | if `OPENAI_API_KEY` absent → use Vosk |
| 3 | pytest: AssistantState all 6 transitions | `backend/tests/test_domain.py` (new) | Pure Python, trivial |
| 4 | pytest: ProcessChatMessageUseCase | `backend/tests/test_use_cases.py` (new) | Use ANTHROPIC_MOCK=1 |
| 5 | pytest: ToolExecutor dangerous command blocking | `backend/tests/test_tool_executor.py` (new) | Test all 8 regex patterns |
| 6 | pytest: EventBus emit/on/error isolation | `backend/tests/test_event_bus.py` (new) | Simple pub/sub |

**Success criteria:**
- Atlas starts and accepts voice with no OpenAI key (Vosk mode)
- `pytest` green (all new tests)
- `ANTHROPIC_MOCK=1 pytest` green (integration test)

---

### Phase 3: Settings UI + Voice UX
**Goal:** Users can configure Atlas without editing `.env`; voice experience polished

| # | Task | File(s) | Notes |
|---|------|---------|-------|
| 1 | Settings panel UI | `frontend/src/renderer/components/Settings/` (new) | API keys, voice, language, capture interval |
| 2 | Settings persistence (Electron store) | `frontend/src/main/settings.ts` (new) | electron-store or JSON file |
| 3 | Global hotkeys — activate/deactivate | `frontend/src/main/index.ts` | `Electron.globalShortcut` |
| 4 | Global hotkeys — push-to-talk | `frontend/src/main/index.ts` | Hold key → record, release → send |
| 5 | Screen capture auto-start on activation | `frontend/src/renderer/App.tsx` | Not just on chat open |
| 6 | Multi-step task planning (JARVIS pattern) | `backend/src/infrastructure/config/master_prompt.py` | Prompt injection for complex commands |

**Success criteria:**
- Settings panel opens, saves, reloads on restart
- Hotkey activates Atlas from any app
- Screen capture starts without opening chat

---

### Phase 4: Local AI + Long-term Memory
**Goal:** Atlas works fully offline; remembers past conversations

| # | Task | File(s) | Notes |
|---|------|---------|-------|
| 1 | `OllamaAdapter` implementing `AIService` | `backend/src/adapters/ai/ollama_adapter.py` (new) | Drop-in for ClaudeAdapter |
| 2 | `AI_BACKEND=anthropic\|ollama` env switch | `settings.py`, `main.py` | Auto-detect Ollama if no Anthropic key |
| 3 | Long-term memory: conversation search | `backend/src/` | TF-IDF or sqlite-vss, REST endpoint |
| 4 | Multi-monitor screen capture | `frontend/src/main/capture.ts`, `frontend/src/preload/index.ts` | Detect screens, user picks one |

**Success criteria:**
- `AI_BACKEND=ollama` routes to local model (e.g., llama3, mistral)
- "What did I work on last Tuesday?" returns real history
- Multi-monitor picker in settings

---

## Open Source Influences

| Source | Idea Borrowed | Phase |
|--------|--------------|-------|
| Priler/jarvis (Rust) | Vosk as offline STT fallback | 2 |
| microsoft/JARVIS (HuggingGPT) | Multi-step task planning before tool execution | 3 |
| open-jarvis/OpenJarvis (Stanford) | Ollama local inference adapter | 4 |

---

## Dependency Order

```
Phase 1 (fixes) → Phase 2 (resilience + tests) → Phase 3 (UX) → Phase 4 (advanced)
```

Phase 1 is a blocker for everything — the port bug alone prevents end-to-end testing.

---

## Out of Scope for v1.0

- Voice cloning
- Plugin/extension system
- Mobile app
- Web deployment
- Multi-user

---
*Created: 2026-03-24 | Research-informed from open source analysis*
