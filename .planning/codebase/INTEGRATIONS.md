# INTEGRATIONS.md — Atlas AI External Integrations

## Anthropic Claude API

**Adapter**: `backend/src/adapters/ai/claude_adapter.py`
**Interface**: `backend/src/application/interfaces/ai_service.py`

- **Model**: `claude-sonnet-4-6` (conversation + tool use)
- **Model**: Claude Haiku Vision (screen analysis via `claude_vision_adapter.py`)
- **Auth**: `ANTHROPIC_API_KEY` env var → `AsyncAnthropic(api_key=...)`
- **Usage patterns**:
  - `messages.create()` — standard chat + tool use loop
  - `messages.stream()` — streaming responses (prepared, not yet wired to UI)
  - `messages.create(temperature=0.3)` — screen analysis (low temp for accuracy)
- **Tool use**: 11 tools defined in `ATLAS_TOOLS` array — browser, terminal, files, Notion
- **Rate limit handling**: Exponential backoff on 529 (`overloaded`) — 1s, 2s, abort
- **Mock mode**: `ANTHROPIC_MOCK=1` or `api_key='mock'` → in-memory mock client

---

## OpenAI Whisper (STT)

**Adapter**: `backend/src/adapters/voice/whisper_adapter.py`
**Interface**: `backend/src/application/interfaces/voice_service.py`

- **Model**: `whisper-1`
- **Auth**: `OPENAI_API_KEY`
- **Input**: WAV bytes (PCM Int16 16kHz mono, wrapped in WAV header by `_pcm16_to_wav()`)
- **Language**: `None` = auto-detect (used for voice commands); `"en"` = forced (wake word check)
- **Wake word fallback**: When Porcupine unavailable, Whisper transcribes 3s PCM clips, checks if `'atlas'` in transcript
- **Energy filter**: avg abs < 1200 → skip call (silence detection)

---

## Picovoice Porcupine (Wake Word)

**Adapter**: `backend/src/adapters/voice/porcupine_adapter.py`

- **Version**: Porcupine v4 (must match `.ppn` model file)
- **Model file**: `backend/models/Hey-Atlas_en_windows_v4_0_0.ppn`
- **Auth**: `PICOVOICE_ACCESS_KEY`
- **Wake words**: "Hey Atlas", "Hello Atlas", "Hola Atlas", "Atlas"
- **Input**: PCM Int16 chunks ~512 samples at 16kHz
- **Init**: Runs in thread pool executor to avoid blocking event loop during key validation
- **Fallback**: If no key, Whisper-based detection kicks in

---

## ElevenLabs (TTS)

**Adapter**: `backend/src/adapters/voice/elevenlabs_adapter.py`
**Interface**: `backend/src/application/interfaces/voice_service.py`

- **Auth**: `ELEVENLABS_API_KEY`
- **Voice**: `onwK4e9ZLuTAKqWW03F9` (Daniel — calm British male, configurable via `ELEVENLABS_VOICE_ID`)
- **Output**: MP3 base64 sent via `tts_audio` WebSocket event
- **Fallback**: Text-only mode when key absent (frontend still gets text)

---

## Notion API

**Adapter**: `backend/src/adapters/notion/notion_adapter.py`

- **Auth**: `NOTION_API_KEY`
- **Capabilities** (exposed as Claude tools):
  - `search_notion(query, max_results=5)` → page list
  - `read_notion_page(page_id)` → page content
  - `create_notion_note(title, content, parent_page_id?)` → new page
- **Integration path**: Claude tool use → `ToolExecutor._notion` → `NotionAdapter`

---

## Playwright (Browser Automation)

**Adapter**: `backend/src/adapters/web/playwright_adapter.py`

- **Lifecycle**: Started/stopped in FastAPI `lifespan` context manager
- **Per-session contexts**: Each session_id gets isolated browser context
- **Capabilities** (Claude tools):
  - `browse_web(url)` → navigate + screenshot
  - `click_element(selector)` → click by CSS/XPath/text
  - `type_text(selector, text)` → form fill
  - `get_page_content()` → visible text
- **Screenshots**: Returned as `screenshot_b64`, forwarded to frontend as `tool_screenshot` WS events

---

## Sentry (Error Monitoring)

**Backend**: `backend/src/infrastructure/monitoring/sentry.py`
**Frontend**: `frontend/src/renderer/sentry.ts`

- **Backend init**: Before FastAPI app object creation (module-level in `main.py`)
- **Environment**: `"production"` when `DEBUG=False`, `"development"` otherwise
- **Release**: `atlas-ai@0.1.0`
- **Usage**: `capture_exception(e, session_id=..., context=...)` in error handlers
- **Session tagging**: `set_session_context(session_id)` on WebSocket connect

---

## SQLite (Local Database)

**ORM**: SQLAlchemy async (`aiosqlite`)
**Models**: `backend/src/infrastructure/database/models.py`
**Repository**: `backend/src/infrastructure/database/repositories/conversation_repository.py`

- **Tables**: Conversation, Message, ScreenContext
- **Init**: `init_db()` called in FastAPI lifespan (CREATE TABLE IF NOT EXISTS)
- **Pattern**: Repository pattern via interface `ConversationRepository`

---

## Electron IPC (Internal — Main ↔ Renderer)

**Bridge**: `frontend/src/preload/index.ts`
**Main handlers**: `frontend/src/main/index.ts`, `frontend/src/main/capture.ts`

- `electronAPI.resizeWindow(w, h)` — expand/collapse window for chat panel
- `electronAPI.getWindowPosition()` / `setWindowPosition(x, y)` — drag support
- `electronAPI.showOrbWindow()` / `hideOrbWindow()` — visibility
- `electronAPI.startScreenCapture()` / `stopScreenCapture()` — Electron `desktopCapturer`
- `electronAPI.onScreenCaptureFrame(cb)` — push frames to renderer
- `electronAPI.onOpenChat(cb)` — tray menu → open chat

---

## WebSocket Protocol (Frontend ↔ Backend)

**Endpoint**: `ws://localhost:8001/api/ws`
**Auth**: None (session_id in connection)

### Frontend → Backend
| Message type | Payload | Purpose |
|---|---|---|
| `ping` | `{}` | Keepalive (every 10s) |
| `audio_chunk` | `{data: {audio: b64_pcm}}` | Wake word detection stream |
| `wake_word_trigger` | `{data: {wake_word}}` | Browser SpeechRecognition trigger |
| `audio_command` | `{data: {audio: b64_webm}}` | Full voice command → STT pipeline |
| `chat_message` | `{data: {message: str}}` | Text chat |
| `screen_capture` | `{data: {data: b64, timestamp, format}}` | Screen frame |
| `set_language` | `{data: {language: "en"\|"es"}}` | Language override |

### Backend → Frontend
| Event type | Payload | Purpose |
|---|---|---|
| `websocket_connected` | `{session_id, status}` | Connection ack |
| `wake_word_detected` | `{wake_word, timestamp}` | "Hey Atlas" heard |
| `state_changed` | `{old_mode, new_mode, state}` | State machine change |
| `ai_response_generated` | `{message, timestamp, error?}` | Claude response text |
| `tts_audio` | `{audio_b64, format, text}` | ElevenLabs MP3 |
| `tool_screenshot` | `{image: b64}` | Browser screenshot |
| `ui_command` | `{action: "dismiss"\|"open_chat"}` | Voice UI commands |
| `message_received` | `{status: "processing"}` | Ack |
| `pong` | — | Keepalive response |
