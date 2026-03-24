# Requirements: Atlas AI Visual Companion

**Defined:** 2026-03-23
**Core Value:** Atlas must hear "Hey Atlas", understand what's on your screen, and give you a useful response — continuous, alive, not a chatbot.

## v1 Requirements

### Foundation (Already Validated — Brownfield)

These requirements are met by existing code and are included for traceability.

- [x] **FOUND-01**: Backend runs as event-driven FastAPI app with persistent WebSocket at /api/ws
- [x] **FOUND-02**: Frontend Electron app shows animated orb (6 states) always on top
- [x] **FOUND-03**: WebSocket auto-reconnects with exponential backoff (max 50 attempts)
- [x] **FOUND-04**: Ping/pong keepalive every 10s prevents connection timeouts
- [x] **FOUND-05**: AssistantState machine: INACTIVE→ACTIVE→LISTENING→THINKING→SPEAKING→PAUSED
- [x] **FOUND-06**: State transitions broadcast to frontend via state_changed events

### Voice Pipeline

- [x] **VOICE-01**: Wake word detection via Porcupine v4 ("Hey Atlas", "Hello Atlas", "Hola Atlas", "Atlas")
- [x] **VOICE-02**: Whisper wake-word fallback when no Picovoice key (3s clip energy filter → transcribe)
- [x] **VOICE-03**: Browser SpeechRecognition trigger (wake_word_trigger message)
- [x] **VOICE-04**: Audio command → Whisper STT → language detection → transcript cleanup
- [x] **VOICE-05**: ElevenLabs TTS response (MP3 base64 via tts_audio event)
- [x] **VOICE-06**: TTS text fallback when no ElevenLabs key
- [x] **VOICE-07**: Voice pipeline runs in asyncio.Task (non-blocking, concurrent ping/pong)
- [x] **VOICE-08**: Voice pipeline guard (_voice_busy) prevents concurrent pipelines per session

### Screen Vision

- [x] **VIS-01**: Electron desktopCapturer captures screen frames (JPEG 80%, 3s interval)
- [x] **VIS-02**: Frames sent via screen_capture WebSocket message to backend
- [x] **VIS-03**: Claude Haiku Vision analyzes frames (10s debounce, ~6 calls/min max)
- [x] **VIS-04**: Screen description injected into Claude context when user references screen
- [ ] **VIS-05**: Screen capture auto-starts when assistant activates (not only on chat open)

### AI & Tools

- [x] **AI-01**: Claude claude-sonnet-4-6 generates responses with conversation history (last 10 msgs)
- [x] **AI-02**: Tool use loop (max 10 iterations): browse_web, click_element, type_text, get_page_content
- [x] **AI-03**: Tool use loop: run_terminal_command, read_file, write_file, list_directory
- [x] **AI-04**: Tool use loop: search_notion, read_notion_page, create_notion_note
- [x] **AI-05**: Fast router: deterministic 0ms routing for known site/search commands
- [x] **AI-06**: Tool screenshots forwarded to frontend as tool_screenshot events
- [x] **AI-07**: Exponential backoff retry on Claude 529 overloaded errors
- [x] **AI-08**: Language-aware system prompts (EN/ES auto-detected per message)
- [ ] **AI-09**: Conversation history persisted to SQLite DB across sessions

### Persistence

- [x] **PERS-01**: SQLite DB with async SQLAlchemy (Conversation, Message, ScreenContext models)
- [x] **PERS-02**: DB auto-initialized on backend startup (CREATE TABLE IF NOT EXISTS)
- [ ] **PERS-03**: Conversation history saved to DB after each exchange
- [ ] **PERS-04**: Session restore: reconnecting client loads last N messages from DB
- [ ] **PERS-05**: Long-term memory: semantic search across past conversations

### Testing

- [ ] **TEST-01**: pytest suite for domain entities (AssistantState transitions, all 6 modes)
- [ ] **TEST-02**: pytest suite for use cases (ProcessChatMessage, ProcessVoiceCommand)
- [ ] **TEST-03**: pytest suite for ToolExecutor (dangerous command blocking, all tools)
- [ ] **TEST-04**: pytest suite for EventBus (emit, on, error isolation)
- [ ] **TEST-05**: Integration test: end-to-end conversation flow with ANTHROPIC_MOCK=1

### Settings & UX

- [ ] **UX-01**: Settings UI panel: API keys (Anthropic, OpenAI, ElevenLabs, Picovoice, Notion, Sentry)
- [ ] **UX-02**: Settings UI: voice selection (ElevenLabs voice list + preview)
- [ ] **UX-03**: Settings UI: language preference, capture interval, screen capture quality
- [ ] **UX-04**: Global hotkey: activate/deactivate Atlas (configurable)
- [ ] **UX-05**: Global hotkey: push-to-talk (hold key → record, release → send)

### Infrastructure Fixes

- [ ] **INFRA-01**: Fix port discrepancy — frontend WebSocket URL must match backend port (8000 vs 8001)
- [ ] **INFRA-02**: Playwright browser context cleanup on session disconnect
- [ ] **INFRA-03**: Rename wake_word_loop → handle_messages for clarity
- [ ] **INFRA-04**: Multi-monitor: detect available screens, capture specific monitor

## v2 Requirements

### Advanced Features

- **ADV-01**: Voice cloning — custom Atlas voice from user recording
- **ADV-02**: Plugin/extension system for third-party integrations
- **ADV-03**: Scheduled reminders with voice alerts
- **ADV-04**: Code snippet library — save/search snippets from screen
- **ADV-05**: Learning from user patterns (frequency analysis of commands)

### Platform

- **PLAT-01**: Mobile companion app (iOS/Android)
- **PLAT-02**: Calendar/todos integration (Google Calendar, Notion tasks)
- **PLAT-03**: Multi-user workspace sharing

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time multi-user | Single-user companion — sharing breaks privacy model |
| Web deployment | Desktop-first; Electron context bridge APIs unavailable in browser |
| Voice cloning | High complexity, out of v1 focus |
| Plugin system | Premature abstraction — build more features first |
| Mobile app | Desktop-first for v1 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| VIS-05 | Phase TBD | Pending |
| AI-09 | Phase TBD | Pending |
| PERS-03 | Phase TBD | Pending |
| PERS-04 | Phase TBD | Pending |
| PERS-05 | Phase TBD | Pending |
| TEST-01 | Phase TBD | Pending |
| TEST-02 | Phase TBD | Pending |
| TEST-03 | Phase TBD | Pending |
| TEST-04 | Phase TBD | Pending |
| TEST-05 | Phase TBD | Pending |
| UX-01 | Phase TBD | Pending |
| UX-02 | Phase TBD | Pending |
| UX-03 | Phase TBD | Pending |
| UX-04 | Phase TBD | Pending |
| UX-05 | Phase TBD | Pending |
| INFRA-01 | Phase TBD | Pending |
| INFRA-02 | Phase TBD | Pending |
| INFRA-03 | Phase TBD | Pending |
| INFRA-04 | Phase TBD | Pending |

**Coverage:**
- v1 new requirements: 19 total (INFRA + TEST + UX + PERS gaps + VIS-05 + AI-09)
- Mapped to phases: 0 (pending roadmap creation)
- Unmapped: 19 ⚠️

---
*Requirements defined: 2026-03-23*
*Last updated: 2026-03-23 after brownfield initialization*
