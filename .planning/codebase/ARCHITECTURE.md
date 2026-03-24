# ARCHITECTURE.md — Atlas AI System Architecture

## Core Philosophy

Atlas is **not** a request/response API. It is an **event-driven continuous system** — always listening, always watching, always ready. This distinction drives every architectural decision.

```
❌ Traditional:  User speaks → POST /chat → Response → END
✅ Atlas:        WebSocket always open → continuous loops → proactive system
```

---

## High-Level System Diagram

```
┌─────────────────────────────────────────────────────┐
│                  ELECTRON DESKTOP APP                │
│  ┌──────────────┐    ┌──────────────────────────┐   │
│  │  Main Process│    │     Renderer (React)      │   │
│  │  index.ts    │IPC │  App.tsx                  │   │
│  │  tray.ts     │◄──►│  OrbCanvas (Canvas/RAF)   │   │
│  │  capture.ts  │    │  ChatInterface            │   │
│  └──────────────┘    │  Hooks: useWebSocket,     │   │
│                      │         useAudioCapture,  │   │
│                      │         useTTSPlayer       │   │
│                      └──────────┬───────────────┘   │
└─────────────────────────────────┼───────────────────┘
                                  │ WebSocket (ws://localhost:8001/api/ws)
┌─────────────────────────────────▼───────────────────┐
│                  FASTAPI BACKEND                      │
│                                                       │
│  WebSocketManager (singleton)                        │
│  ├── wake_word_loop() — processes ALL inbound msgs   │
│  ├── screen_monitor_loop() — heartbeat/state         │
│  └── _run_voice_pipeline() — Whisper→Claude→TTS      │
│                    │                                  │
│           EventBus (singleton)                       │
│           ├── USER_MESSAGE_RECEIVED                  │
│           ├── SCREEN_CONTEXT_UPDATED                 │
│           └── WEBSOCKET_CONNECTED/DISCONNECTED       │
│                    │                                  │
│  ┌─────────────────▼──────────────────────────────┐ │
│  │            Application Layer (Use Cases)         │ │
│  │  ProcessChatMessageUseCase                       │ │
│  │  ProcessVoiceCommandUseCase                      │ │
│  │  AnalyzeScreenUseCase                            │ │
│  │  OfferProactiveHelpUseCase                       │ │
│  └─────────────────┬──────────────────────────────┘ │
│                    │ (via interfaces)                 │
│  ┌─────────────────▼──────────────────────────────┐ │
│  │               Adapters                           │ │
│  │  ClaudeAdapter  WhisperAdapter  PorcupineAdapter │ │
│  │  ElevenLabsAdapter  ClaudeVisionAdapter          │ │
│  │  PlaywrightAdapter  NotionAdapter                │ │
│  │  TesseractAdapter (legacy)                       │ │
│  └────────────────────────────────────────────────┘ │
│                                                       │
│  Infrastructure: SQLite DB, Sentry, Config           │
└──────────────────────────────────────────────────────┘
```

---

## Backend: Clean Architecture

Four concentric layers — dependencies point inward only.

### Layer 1: Domain (`backend/src/domain/`)
Zero external dependencies. Pure Python dataclasses and enums.

```python
# AssistantMode: INACTIVE | ACTIVE | LISTENING | THINKING | SPEAKING | PAUSED
# AssistantState: session_id, mode, language, timestamps + state transition methods
# Conversation, Message, ScreenContext entities
```

**State machine transitions**:
```
INACTIVE/PAUSED → activate() → ACTIVE
INACTIVE/ACTIVE → start_listening() → LISTENING
LISTENING/ACTIVE → start_thinking() → THINKING
THINKING → start_speaking() → SPEAKING
SPEAKING → finish_speaking() → ACTIVE
any → reset_to_active() → ACTIVE  (error recovery)
```

### Layer 2: Application (`backend/src/application/`)
Use cases + abstract interfaces (ports). No concrete implementations.

**Interfaces** (abstract ports):
- `AIService` — `generate_response()`, `analyze_screen_context()`, `offer_proactive_help()`
- `VoiceService` — `transcribe_audio()`, `text_to_speech()`
- `ScreenService` — `extract_text_from_image()`
- `ConversationRepository` — persistence port

**Use Cases**:
- `ProcessChatMessageUseCase` — text chat → Claude → response
- `ProcessVoiceCommandUseCase` — audio → Whisper → fast-route/Claude → ElevenLabs
- `AnalyzeScreenUseCase` — screenshot → Vision → description
- `OfferProactiveHelpUseCase` — screen context → proactive suggestion

### Layer 3: Adapters (`backend/src/adapters/`)
Concrete implementations of interfaces. Each adapter wraps one external service.

| Adapter | Implements | External |
|---|---|---|
| `ClaudeAdapter` | `AIService` | Anthropic API |
| `ClaudeVisionAdapter` | `ScreenService` | Anthropic Haiku Vision |
| `WhisperAdapter` | `VoiceService` (STT) | OpenAI Whisper |
| `PorcupineAdapter` | — | Picovoice wake word |
| `ElevenLabsAdapter` | `VoiceService` (TTS) | ElevenLabs |
| `TesseractAdapter` | `ScreenService` | Tesseract OCR (legacy) |
| `PlaywrightAdapter` | — | Browser automation |
| `NotionAdapter` | — | Notion API |

### Layer 4: Infrastructure (`backend/src/infrastructure/`)
Framework glue, singleton orchestration, and cross-cutting concerns.

**Key singletons** (module-level):
```python
event_bus = EventBus()       # event_bus.py
ws_manager = WebSocketManager()  # manager.py
```

**FastAPI lifespan** (`main.py`) wires everything:
1. Init Sentry → init DB → create adapters
2. Register event handlers on `event_bus`
3. Inject factories/services into `ws_manager`
4. Start Playwright browser
5. Yield (app runs)
6. Stop Playwright

---

## Frontend Architecture

### Electron Multi-Process Model
```
Main Process (Node.js)          Renderer Process (Chrome/React)
  index.ts — window mgmt    IPC    App.tsx
  tray.ts — system tray    ◄────►  components/
  capture.ts — screen grab         hooks/
                                   services/

Preload (index.ts) — contextBridge exposes electronAPI to renderer
```

### React Component Tree
```
App.tsx
├── useWebSocket()    — WS connection, send/on/off
├── useAudioCapture() — mic, wake word detection, recording
├── useTTSPlayer()    — ElevenLabs audio playback
│
├── <OrbCanvas state={assistantState} />  — Canvas particle animation
└── {isChatOpen && <ChatInterface />}     — slides in below orb
```

### Window Sizing
- **Orb only**: 200×200px (frameless, always on top)
- **With chat**: 420×660px (expanded on wake word / orb click)

---

## Data Flow: Voice Command (Happy Path)

```
1. Frontend: mic always recording PCM at 16kHz
2. Frontend: sends audio_chunk via WebSocket
3. Backend: PorcupineAdapter.detect_wake_word(pcm) → detected
4. Backend: ws_manager sends wake_word_detected event to frontend
5. Frontend: setAssistantState('listening'), showOrbWindow()
6. Frontend: records full command, sends audio_command
7. Backend: _run_voice_pipeline() in asyncio.Task (non-blocking)
   a. WhisperAdapter.transcribe_audio() → text
   b. _detect_language() → "en"|"es"
   c. _clean_transcript() — strip fillers, last-intent bias
   d. _fast_route() → if known site, execute immediately (0ms)
   e. Otherwise: ClaudeAdapter.generate_response() with tool use loop
   f. ElevenLabsAdapter.text_to_speech() → MP3 bytes
8. Backend: sends ai_response_generated + tts_audio events
9. Frontend: useTTSPlayer plays MP3, state → 'speaking' → 'active'
```

## Data Flow: Text Chat

```
1. User types in ChatInterface, submits
2. App.tsx: send('chat_message', {message})
3. Backend: wake_word_loop receives chat_message
4. Backend: _detect_language(), _needs_screen_context() check
5. Backend: event_bus.emit(USER_MESSAGE_RECEIVED, {message, screen_context?})
6. Backend: handle_user_message → ProcessChatMessageUseCase.execute()
7. Backend: ClaudeAdapter.generate_response() with optional tool use
8. Backend: send ai_response_generated event
9. Frontend: setMessages([...prev, {role: 'assistant', content}])
```

---

## Event Bus Pattern

The EventBus is the internal nervous system — decouples producers from consumers.

```python
# Register handler
event_bus.on(EventType.USER_MESSAGE_RECEIVED.value, handle_user_message)

# Emit event
await event_bus.emit(EventType.USER_MESSAGE_RECEIVED.value, {
    "session_id": session_id, "message": text, ...
})
```

Handlers run sequentially. Async handlers are `await`ed. Errors in one handler don't stop others.

---

## Tool Use Loop (Claude Agentic Behavior)

```python
for _ in range(10):           # max iterations
    response = await claude(messages, tools=ATLAS_TOOLS)

    if response.stop_reason == "end_turn":
        return extract_text(response)   # done

    if response.stop_reason == "tool_use":
        for block in tool_use_blocks:
            result = await tool_executor.execute(block.name, block.input)
            # capture screenshots for tool_screenshot WS event
        messages += [assistant_turn, tool_results]
        continue   # loop again

# exhausted → return error message
```

Available tools: `browse_web`, `click_element`, `type_text`, `get_page_content`, `run_terminal_command`, `read_file`, `write_file`, `list_directory`, `search_notion`, `read_notion_page`, `create_notion_note`
