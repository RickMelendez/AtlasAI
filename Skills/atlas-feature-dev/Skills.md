---
name: atlas-feature-dev
description: >
  Feature development for the AtlasAI project. Use this skill when adding new capabilities,
  API endpoints, voice commands, UI components, backend use cases, or any new functionality
  to Atlas. Enforces the clean architecture pattern (Domain → Application → Adapters →
  Infrastructure), event-driven WebSocket design, and the Spanish-comment convention.
  Use whenever the user says "add", "build", "implement", or "create" something new in AtlasAI.
---

# Atlas Feature Developer

You build features in AtlasAI following its clean architecture and event-driven design. Before writing a single line, understand where the feature lives in the stack.

## Architecture Layers (never skip layers)

```
Domain          → Pure business entities, no external deps
                  backend/src/domain/entities/, domain/value_objects/

Application     → Use cases (orchestrate domain + call interfaces)
                  backend/src/application/use_cases/
                  backend/src/application/interfaces/  ← abstract ports

Adapters        → Concrete implementations of interfaces
                  backend/src/adapters/ai/       (Claude, OpenAI)
                  backend/src/adapters/voice/    (Porcupine, Whisper, ElevenLabs)
                  backend/src/adapters/vision/   (Tesseract)

Infrastructure  → FastAPI routes, WebSocket manager, EventBus, DB, config
                  backend/src/infrastructure/
```

**Rule**: Use cases depend on interfaces (ports), never on adapters directly.

## WebSocket Event Flow

All features that need real-time communication go through the WebSocket:

```
Frontend sends:  { type: "event_name", data: { ... } }
Backend handles: in wake_word_loop() switch/if on msg_type
Backend sends:   await ws_manager.send_event(session_id, { type: "...", data: {...} })
Frontend listens: wsService.on('event_name', handler)
```

Add new message types to `backend/src/infrastructure/events/event_types.py`.

## Feature Development Checklist

### Backend feature
- [ ] Define domain entity if new concept (e.g., `domain/entities/new_thing.py`)
- [ ] Define interface in `application/interfaces/` if new external service
- [ ] Write use case in `application/use_cases/` (pure async, no framework deps)
- [ ] Write adapter in `adapters/` that implements the interface
- [ ] Register adapter in `main.py` lifespan startup
- [ ] Add WebSocket handler in `manager.py` if frontend needs to trigger it
- [ ] Add event type constant to `event_types.py`

### Frontend feature
- [ ] Add IPC handler in `main/index.ts` if it needs Electron APIs
- [ ] Expose via `preload/index.ts` contextBridge if renderer needs it
- [ ] Add hook in `renderer/hooks/` for new state/behavior
- [ ] Update `App.tsx` or relevant component
- [ ] Add WS message handler with `wsService.on('new_event', handler)`

## Code Conventions

**Comments**: Complex business logic commented in Spanish.
```python
# Inicializar Porcupine en thread pool para no bloquear el event loop
```

**Async**: All backend I/O must be async. Blocking calls (like C extensions) go in `run_in_executor`.

**Singletons**:
```python
# Backend
event_bus = EventBus()
ws_manager = WebSocketManager()
```
```typescript
// Frontend
export const wsService = new WebSocketService()
```

**Never** use `setInterval` for animations — use `requestAnimationFrame`.

## Adding a New Voice Command

1. Backend: add handler in `_handle_audio_command` or new `_handle_X` method in `manager.py`
2. Backend: new use case that calls Whisper → Claude → ElevenLabs pipeline
3. Frontend: `useAudioCapture` already sends `audio_command` after recording — just handle the response

## Adding a New Backend Service

1. Create interface: `application/interfaces/new_service.py`
   ```python
   class NewService(ABC):
       @abstractmethod
       async def do_thing(self, input: str) -> str: ...
   ```
2. Create adapter: `adapters/category/new_adapter.py` implementing `NewService`
3. Wire in `main.py` lifespan:
   ```python
   new_service = NewAdapter(api_key=settings.new_api_key)
   ```

## Testing New Features

The test suite is currently a scaffold (`backend/tests/` is empty). For manual testing:
```bash
cd backend && python test_claude.py  # manual integration test
```

Use the running app (via `dev.bat`) and watch both terminal windows for errors.
