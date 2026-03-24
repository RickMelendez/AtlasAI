# STRUCTURE.md — Atlas AI Directory Layout

## Root

```
AtlasAI/
├── backend/               Python FastAPI backend
├── frontend/              Electron + React frontend
├── .planning/             GSD planning docs
│   ├── codebase/          This mapping (7 docs)
│   └── debug/             Resolved debug sessions
├── Skills/                Custom Claude Code skills
│   ├── atlas-debug/
│   ├── atlas-feature-dev/
│   ├── atlas-orb-animator/
│   ├── atlas-runner/
│   ├── atlas-scrum/
│   ├── atlas-team/
│   ├── brainstormer/
│   ├── frontend-design/
│   ├── mcp-builder/
│   ├── skill-creator/
│   ├── sparring-partner/
│   └── ui-ux-pro-max/
├── INFO/
│   └── DEVELOPMENT_GUIDE.md
├── CLAUDE.md              AI assistant instructions (project rules)
├── STATUS.md              Feature completion tracker (85% done)
├── README.md
├── dev.bat                Windows launcher (opens 2 CMD windows)
├── .backend.log
└── .frontend.log
```

---

## Backend

```
backend/
├── src/
│   ├── main.py                         ← FastAPI entrypoint, lifespan wiring
│   │
│   ├── domain/                         Layer 1 — pure business logic
│   │   ├── entities/
│   │   │   ├── assistant_state.py      AssistantMode enum + AssistantState dataclass
│   │   │   ├── conversation.py         Conversation entity
│   │   │   ├── message.py              Message entity
│   │   │   └── screen_context.py       ScreenContext entity
│   │   └── value_objects/              (empty scaffold)
│   │
│   ├── application/                    Layer 2 — use cases + ports
│   │   ├── interfaces/
│   │   │   ├── ai_service.py           AIService ABC
│   │   │   ├── voice_service.py        VoiceService ABC
│   │   │   ├── screen_service.py       ScreenService ABC
│   │   │   └── conversation_repository.py  Repository ABC
│   │   └── use_cases/
│   │       ├── process_chat_message.py
│   │       ├── process_voice_command.py
│   │       ├── analyze_screen.py
│   │       ├── offer_proactive_help.py
│   │       └── results.py              Shared result types
│   │
│   ├── adapters/                       Layer 3 — concrete implementations
│   │   ├── ai/
│   │   │   ├── claude_adapter.py       ★ Main AI adapter (tool use, retry)
│   │   │   └── openai_adapter.py       (alternative, not active)
│   │   ├── voice/
│   │   │   ├── whisper_adapter.py      STT
│   │   │   ├── porcupine_adapter.py    Wake word
│   │   │   └── elevenlabs_adapter.py   TTS
│   │   ├── vision/
│   │   │   ├── claude_vision_adapter.py  ★ Active screen vision
│   │   │   └── tesseract_adapter.py    Legacy OCR
│   │   ├── web/
│   │   │   └── playwright_adapter.py   Browser automation
│   │   ├── notion/
│   │   │   └── notion_adapter.py       Notion integration
│   │   └── tools/
│   │       └── tool_executor.py        ★ Dispatches all Claude tool calls
│   │
│   └── infrastructure/                 Layer 4 — framework + cross-cutting
│       ├── api/
│       │   └── routes/
│       │       └── websocket.py        /api/ws endpoint definition
│       ├── websocket/
│       │   └── manager.py              ★★ WebSocketManager (critical singleton)
│       ├── events/
│       │   ├── event_bus.py            EventBus singleton
│       │   └── event_types.py          EventType enum (all event names)
│       ├── loops/
│       │   └── __init__.py             (scaffold — loops live in manager.py)
│       ├── database/
│       │   ├── base.py
│       │   ├── models.py               SQLAlchemy models
│       │   └── repositories/
│       │       └── conversation_repository.py
│       ├── monitoring/
│       │   └── sentry.py               init_sentry(), capture_exception()
│       └── config/
│           ├── settings.py             Pydantic Settings (reads .env)
│           └── master_prompt.py        Claude system prompts (ES + EN)
│
├── models/
│   └── Hey-Atlas_en_windows_v4_0_0.ppn  Porcupine v4 wake word model
├── tests/
│   └── __init__.py                     (empty scaffold)
├── test_claude.py                      Manual integration test script
├── .env                                Secrets (gitignored)
├── .env.example                        Template
└── requirements.txt
```

---

## Frontend

```
frontend/
├── src/
│   ├── main/                           Electron main process (Node.js)
│   │   ├── index.ts                    App init, BrowserWindow, IPC handlers
│   │   ├── tray.ts                     System tray icon + context menu
│   │   └── capture.ts                  Screen capture via desktopCapturer
│   │
│   ├── preload/
│   │   └── index.ts                    contextBridge — exposes electronAPI
│   │
│   └── renderer/                       React UI (Chromium renderer)
│       ├── main.tsx                    React root mount
│       ├── App.tsx                     ★ Main component, all state + event wiring
│       ├── App.css
│       ├── index.css                   Global styles, CSS variables
│       ├── sentry.ts                   Frontend Sentry init
│       ├── vite-env.d.ts
│       │
│       ├── components/
│       │   ├── Orb/
│       │   │   ├── OrbCanvas.tsx       ★ Canvas particle animation (6 states)
│       │   │   └── OrbCanvas.css
│       │   ├── Chat/
│       │   │   ├── ChatInterface.tsx   Chat panel (messages + input)
│       │   │   └── ChatInterface.css
│       │   └── ui/                     shadcn-style primitives
│       │       ├── ai-voice-input.tsx
│       │       ├── loader.tsx
│       │       ├── prompt-input-dynamic-grow.tsx
│       │       └── glowing-ai-chat-assistant.tsx
│       │
│       ├── hooks/
│       │   ├── useWebSocket.ts         WS connection singleton wrapper
│       │   ├── useAudioCapture.ts      Mic capture, wake word, recording
│       │   ├── useScreenCapture.ts     Screen frame forwarding
│       │   └── useTTSPlayer.ts         ElevenLabs audio playback
│       │
│       └── services/
│           └── websocket.ts            ★ WebSocketService singleton
│                                       (auto-reconnect, event emitter)
│
├── components.json                     shadcn/ui config
├── package.json
├── package-lock.json
├── tailwind.config.ts
├── tsconfig.json
├── tsconfig.node.json
└── vite.config.ts
```

---

## Key File Locations Quick Reference

| What | Where |
|---|---|
| App entrypoint (backend) | `backend/src/main.py` |
| WebSocket logic (critical) | `backend/src/infrastructure/websocket/manager.py` |
| Claude AI adapter | `backend/src/adapters/ai/claude_adapter.py` |
| All Claude tools defined | `backend/src/adapters/ai/claude_adapter.py` (`ATLAS_TOOLS`) |
| Tool execution dispatch | `backend/src/adapters/tools/tool_executor.py` |
| State machine | `backend/src/domain/entities/assistant_state.py` |
| System prompts | `backend/src/infrastructure/config/master_prompt.py` |
| All event names | `backend/src/infrastructure/events/event_types.py` |
| Settings / env vars | `backend/src/infrastructure/config/settings.py` |
| App component | `frontend/src/renderer/App.tsx` |
| Orb animation | `frontend/src/renderer/components/Orb/OrbCanvas.tsx` |
| WebSocket service | `frontend/src/renderer/services/websocket.ts` |
| IPC bridge | `frontend/src/preload/index.ts` |
| Electron main | `frontend/src/main/index.ts` |
| Wake word model | `backend/models/Hey-Atlas_en_windows_v4_0_0.ppn` |

---

## Naming Conventions

### Backend (Python)
- Files: `snake_case.py`
- Classes: `PascalCase` (e.g., `WebSocketManager`, `ClaudeAdapter`)
- Methods: `snake_case` (e.g., `generate_response`, `start_listening`)
- Private methods: `_single_underscore` (e.g., `_browse_web`, `_handle_audio_chunk`)
- Singletons: module-level lowercase (e.g., `event_bus = EventBus()`)
- Comments: Spanish for complex business logic (project convention)

### Frontend (TypeScript)
- Files: `PascalCase.tsx` for components, `camelCase.ts` for utilities
- Components: `PascalCase` (e.g., `OrbCanvas`, `ChatInterface`)
- Hooks: `use` prefix + `PascalCase` (e.g., `useWebSocket`, `useAudioCapture`)
- Singletons: module-level const export (e.g., `export const wsService = new WebSocketService()`)
- CSS: component-scoped `.css` files beside component
