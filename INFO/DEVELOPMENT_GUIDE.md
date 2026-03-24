# Atlas AI Visual Companion - Development Guide

> **Guía completa para Claude CLI y Agentes Claude**
> Este documento define cómo construir Atlas paso a paso usando Clean Architecture + Event-Driven Architecture.

**Última actualización**: 2025-01-30
**Versión**: 2.0.0 (Event-Driven Architecture)
**Autor**: Ricky

---

## 📋 Contexto del Proyecto

### ¿Qué estamos construyendo?

Un **asistente AI visual personal** que funciona como un compañero sentado a tu lado, mirando la misma pantalla y conversando naturalmente sobre lo que ambos ven.

**Arquitectura Core**: Sistema event-driven continuo (como un droid/robot), NO una API request/response tradicional.

**Analogía clave**: Atlas es un amigo tech-savvy que está siempre presente, observando, escuchando y ayudando cuando lo necesitas.

### Características Principales

1. **Orb místico animado** con partículas flotantes (system tray icon)
2. **Wake word detection**: "Hey Atlas" siempre escuchando
3. **Control por voz**: "activate" / "pause" / "continue"
4. **Visión de pantalla continua**: Captura y analiza cada 3s cuando activo
5. **Conversación natural**: Habla en español/inglés sobre el contexto
6. **Asistencia proactiva**: Puede sugerir ayuda sin que le pidas
7. **Memoria de sesión**: Recuerda la conversación actual

---

## 🏗️ Decisión Arquitectónica Fundamental

### ❓ ¿Endpoints o Sistema Continuo?

**RESPUESTA: Sistema Event-Driven Híbrido**

```
┌──────────────────────────────────────────────────────────┐
│ ❌ Arquitectura INCORRECTA (Solo Endpoints)              │
│                                                          │
│ User habla → POST /chat → Response → FIN                │
│                                                          │
│ Problemas:                                               │
│ • No puede escuchar wake word 24/7                      │
│ • No puede monitorear pantalla continuamente            │
│ • No puede ser proactivo                                │
│ • Pierde contexto entre requests                        │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ ✅ Arquitectura CORRECTA (Event-Driven + WebSocket)      │
│                                                          │
│ WebSocket siempre abierto                               │
│   ↓                                                      │
│ Backend loops continuos:                                │
│   • Wake word detection (24/7)                          │
│   • Screen monitoring (cada 3s si ACTIVE)               │
│   • Conversation processing                             │
│   • Proactive suggestions (cuando detecta frustración)  │
│                                                          │
│ REST Endpoints (solo comandos explícitos):              │
│   • POST /activate (cuando user clickea orb)            │
│   • POST /pause                                         │
│   • GET /status                                         │
└──────────────────────────────────────────────────────────┘
```

**Atlas funciona como un ser vivo, siempre presente.**

---

## 🎨 Diseño Visual

### Color Palette (Inspirado en imágenes de referencia)

```
Primary Colors:
- Background: #0D0D0D (Almost Black)
- Orb Core: #00D9FF (Cyan brillante)
- Orb Particles: Gradient (#00D9FF → #7B2FFF → #FF006E)
- Text Primary: #E0E0E0
- Text Secondary: #8A8A8A
- Accent: #00FFA3 (Green Cyan)

UI States:
- Inactive: rgba(255, 255, 255, 0.1)
- Active: #00D9FF
- Listening: Pulsing cyan
- Thinking: Rotating particles
- Speaking: Synchronized glow
- Paused: Slow amber pulse (#FFA500)
```

### Orb Animation (Basado en Particle Sphere)

**Referencia**: Particle sphere 3D con física de partículas

```javascript
// Características del Orb:
- 500-1000 partículas en órbita
- Radio: 40-50px
- Partículas: 2-3px cada una
- Rotación suave en 3D (usando sin/cos)
- Color gradient basado en posición
- Efecto glow/blur en CSS
- Animación: 60fps smooth
```

**Estados visuales**:
- **Inactive**: Partículas lentas, colores apagados
- **Listening**: Partículas aceleran, cyan brillante
- **Thinking**: Rotación compleja, multicolor
- **Speaking**: Pulsos sincronizados con audio
- **Paused**: Partículas casi estáticas, color amber suave pulsando lentamente

---

## 🏗️ Arquitectura del Sistema

### Stack Tecnológico

```yaml
Frontend:
  Runtime: Electron 28+
  Framework: React 18 + TypeScript 5
  Styling: TailwindCSS + CSS Modules
  Animation: Canvas API (o Three.js)
  State: Zustand
  Build: Vite
  WebSocket: Native WebSocket API

Backend:
  Runtime: Python 3.11+
  Framework: FastAPI
  WebSocket: FastAPI WebSocket support
  Event Bus: Custom async event emitter
  AI: Anthropic Claude API
  Voice:
    Input: OpenAI Whisper
    Wake Word: Picovoice Porcupine
    Output: ElevenLabs (o Azure TTS)
  Vision: Tesseract OCR + Claude Vision
  Database: SQLite + SQLAlchemy
  Testing: pytest, pytest-asyncio
```

### Arquitectura Event-Driven

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (Electron)                      │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Orb UI      │  │  Audio       │  │  Screen      │      │
│  │  Component   │  │  Recorder    │  │  Capture     │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                  │              │
│  ┌──────▼─────────────────▼──────────────────▼───────┐     │
│  │         WebSocket Client (Always Connected)        │     │
│  │  • Sends audio chunks continuously                │     │
│  │  • Sends screen captures every 3s                 │     │
│  │  • Receives events from backend                   │     │
│  └────────────────────────┬───────────────────────────┘     │
└───────────────────────────┼─────────────────────────────────┘
                            │ WebSocket
┌───────────────────────────▼─────────────────────────────────┐
│                  BACKEND (FastAPI + Event Bus)               │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         WebSocket Manager (Connection Handler)       │   │
│  │                                                       │   │
│  │  • Accepts WebSocket connections                     │   │
│  │  • Manages active sessions                           │   │
│  │  • Routes events to/from frontend                    │   │
│  └────────────────────────┬─────────────────────────────┘   │
│                           │                                  │
│  ┌────────────────────────▼─────────────────────────────┐   │
│  │              Continuous Loops (Always Running)        │   │
│  │                                                       │   │
│  │  ┌─────────────────────────────────────────────┐     │   │
│  │  │  Wake Word Loop (24/7)                      │     │   │
│  │  │  • Receives audio chunks via WebSocket      │     │   │
│  │  │  • Detects "Hey Atlas" / "Atlas"            │     │   │
│  │  │  • Emits: wake_word_detected event          │     │   │
│  │  └─────────────────────────────────────────────┘     │   │
│  │                                                       │   │
│  │  ┌─────────────────────────────────────────────┐     │   │
│  │  │  Screen Monitor Loop (every 3s if ACTIVE)   │     │   │
│  │  │  • Receives screenshots via WebSocket       │     │   │
│  │  │  • Analyzes with OCR + Claude Vision        │     │   │
│  │  │  • Emits: screen_context_updated event      │     │   │
│  │  │  • Detects: error_detected, frustration     │     │   │
│  │  └─────────────────────────────────────────────┘     │   │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────▼─────────────────────────────┐   │
│  │              Event Bus (Internal Communication)       │   │
│  │                                                       │   │
│  │  Events emitted:                                      │   │
│  │  • wake_word_detected                                │   │
│  │  • screen_context_updated                            │   │
│  │  • error_detected                                    │   │
│  │  • user_frustrated (heuristic)                       │   │
│  │  • conversation_message                              │   │
│  │  • state_changed                                     │   │
│  └────────────────────────┬─────────────────────────────┘   │
│                           │                                  │
│  ┌────────────────────────▼─────────────────────────────┐   │
│  │           USE CASES (Subscribe to Events)             │   │
│  │                                                       │   │
│  │  • ActivateAssistantUseCase                          │   │
│  │    Listens: wake_word_detected                       │   │
│  │                                                       │   │
│  │  • GenerateResponseUseCase                           │   │
│  │    Listens: conversation_message, screen_updated     │   │
│  │                                                       │   │
│  │  • OfferProactiveHelpUseCase                         │   │
│  │    Listens: error_detected, user_frustrated          │   │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         REST Endpoints (Explicit Commands Only)       │   │
│  │                                                       │   │
│  │  POST /api/assistant/activate  (manual click)        │   │
│  │  POST /api/assistant/pause                           │   │
│  │  GET  /api/assistant/status                          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Estructura de Carpetas

```
atlas-ai-companion/
├── frontend/                          # Electron + React
│   ├── src/
│   │   ├── main/                     # Electron main process
│   │   │   ├── index.ts
│   │   │   ├── tray.ts               # System tray
│   │   │   └── capture.ts            # Screen capture
│   │   │
│   │   ├── renderer/                 # React UI
│   │   │   ├── components/
│   │   │   │   ├── Orb/
│   │   │   │   │   ├── OrbCanvas.tsx
│   │   │   │   │   ├── OrbParticles.ts
│   │   │   │   │   └── orb.module.css
│   │   │   │   ├── Chat/
│   │   │   │   │   ├── ChatPanel.tsx
│   │   │   │   │   └── Message.tsx
│   │   │   │   └── Settings/
│   │   │   │       └── SettingsPanel.tsx
│   │   │   │
│   │   │   ├── hooks/
│   │   │   │   ├── useAssistant.ts
│   │   │   │   ├── useVoice.ts
│   │   │   │   └── useWebSocket.ts    # NEW
│   │   │   │
│   │   │   ├── services/
│   │   │   │   ├── websocket.ts       # NEW
│   │   │   │   └── audio-recorder.ts
│   │   │   │
│   │   │   └── store/
│   │   │       └── assistant-store.ts  # Zustand
│   │   │
│   │   └── preload/
│   │       └── index.ts
│   │
│   └── package.json
│
├── backend/                           # Python FastAPI
│   ├── src/
│   │   ├── domain/                   # ENTITIES
│   │   │   ├── entities/
│   │   │   │   ├── assistant_state.py
│   │   │   │   ├── conversation.py
│   │   │   │   ├── message.py
│   │   │   │   └── screen_context.py
│   │   │   │
│   │   │   └── value_objects/
│   │   │       ├── assistant_mode.py
│   │   │       └── language.py
│   │   │
│   │   ├── application/              # USE CASES
│   │   │   ├── use_cases/
│   │   │   │   ├── activate_assistant.py
│   │   │   │   ├── process_voice_command.py
│   │   │   │   ├── analyze_screen.py
│   │   │   │   ├── generate_response.py
│   │   │   │   └── offer_proactive_help.py  # NEW
│   │   │   │
│   │   │   └── interfaces/
│   │   │       ├── ai_service.py
│   │   │       ├── voice_service.py
│   │   │       └── screen_service.py
│   │   │
│   │   ├── adapters/                 # EXTERNAL INTEGRATIONS
│   │   │   ├── ai/
│   │   │   │   └── claude_adapter.py
│   │   │   ├── voice/
│   │   │   │   ├── whisper_adapter.py
│   │   │   │   ├── porcupine_adapter.py
│   │   │   │   └── elevenlabs_adapter.py
│   │   │   └── vision/
│   │   │       └── tesseract_adapter.py
│   │   │
│   │   ├── infrastructure/
│   │   │   ├── api/
│   │   │   │   ├── routes/
│   │   │   │   │   ├── assistant.py
│   │   │   │   │   └── websocket.py      # NEW
│   │   │   │   │
│   │   │   │   └── app.py
│   │   │   │
│   │   │   ├── websocket/               # NEW
│   │   │   │   ├── manager.py           # WebSocket Manager
│   │   │   │   └── handlers.py          # Event handlers
│   │   │   │
│   │   │   ├── events/                  # NEW
│   │   │   │   ├── event_bus.py         # Event Bus
│   │   │   │   └── event_types.py       # Event definitions
│   │   │   │
│   │   │   ├── loops/                   # NEW
│   │   │   │   ├── wake_word_loop.py
│   │   │   │   └── screen_monitor_loop.py
│   │   │   │
│   │   │   ├── database/
│   │   │   │   └── sqlite_client.py
│   │   │   │
│   │   │   └── config/
│   │   │       ├── settings.py
│   │   │       └── master_prompt.py
│   │   │
│   │   └── main.py
│   │
│   └── requirements.txt
│
└── docs/
    ├── DEVELOPMENT_GUIDE.md (este archivo)
    ├── FEATURES_CHECKLIST.md
    ├── MASTER_PROMPT.md
    └── ARCHITECTURE.md
```

---

## 🚀 Plan de Desarrollo (Feature por Feature)

### Phase 1: Foundation (Week 1)

#### Feature 1.1: System Tray Icon + Orb Window

**Objetivo**: Tener un icono en la taskbar que al clickear abre el orb flotante.

**Instrucciones para Claude CLI:**

```
Contexto:
Estoy construyendo un AI visual companion con Electron. Necesito crear el
sistema de system tray que permita mostrar/ocultar el orb.

Tarea:
Crea los siguientes archivos con Clean Code:

1. frontend/src/main/tray.ts
   - Función createTrayIcon() que crea icon en system tray
   - Menu con opciones: "Show Orb", "Settings", "Quit"
   - Icon path: assets/icons/orb-icon.png (32x32px)

2. frontend/src/main/index.ts
   - Setup Electron app
   - Crear BrowserWindow transparente para el orb
   - Window properties:
     * transparent: true
     * frame: false
     * alwaysOnTop: true
     * skipTaskbar: true
     * width: 120, height: 120

3. frontend/assets/icons/orb-icon.png
   - Genera un icono simple del orb (puedes usar un placeholder SVG)

Reglas:
- TypeScript estricto
- Comentarios en español
- Error handling con try-catch
- Logging con electron-log

Ejemplo de código esperado en tray.ts:
```typescript
import { Tray, Menu, app } from 'electron';
import path from 'path';

let tray: Tray | null = null;

export function createTrayIcon(window: BrowserWindow): void {
  const iconPath = path.join(__dirname, '../../assets/icons/orb-icon.png');
  tray = new Tray(iconPath);

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Orb',
      click: () => window.show()
    },
    // ... más opciones
  ]);

  tray.setContextMenu(contextMenu);
  tray.setToolTip('AI Visual Companion');
}
```

Criterio de éxito:
- Al correr la app, aparece icono en system tray
- Click derecho muestra menu
- "Show Orb" abre ventana transparente
```

#### Feature 1.2: Particle Orb Animation

**Instrucciones para Claude CLI:**

```
Contexto:
Necesito el orb visual con animación de partículas en 3D, similar a un
particle sphere con física de partículas.

Tarea:
Crea un componente React que renderize un orb animado usando Canvas API
(o Three.js si lo prefieres).

Archivo: frontend/src/renderer/components/Orb/OrbCanvas.tsx

Especificaciones del Orb:
- Canvas circular de 100x100px
- 500-800 partículas orbitando
- Cada partícula:
  * Tamaño: 2-3px
  * Color: Gradient cyan (#00D9FF) → purple (#7B2FFF) → pink (#FF006E)
  * Posición: Distribución esférica usando sin/cos
- Animación:
  * Rotación suave en ejes X, Y, Z
  * 60 FPS
  * Velocidad variable según estado (inactive, active, listening)

Estados visuales:
1. INACTIVE: Partículas lentas, colores apagados (opacity 0.3)
2. ACTIVE: Velocidad normal, colores brillantes
3. LISTENING: Velocidad rápida, partículas más grandes, pulsing effect
4. THINKING: Rotación compleja, colores cambiando

Datos de entrada (props):
```typescript
interface OrbProps {
  state: 'inactive' | 'active' | 'listening' | 'thinking' | 'speaking';
  onClick?: () => void;
}
```

Reglas:
- Performance: requestAnimationFrame, no setInterval
- TypeScript con tipos estrictos
- CSS Modules para estilos
- Optimizar con useMemo/useCallback
- Comentarios explicando la física

Criterio de éxito:
- Orb se renderiza sin lag
- Animación smooth a 60fps
- Cambios de estado se ven claramente
- Click en el orb dispara evento
```

#### Feature 1.3: Backend Básico

**Instrucciones para Claude CLI:**

```
Contexto:
Configurar el backend Python con FastAPI siguiendo Clean Architecture.

Tarea:
1. Setup inicial de FastAPI con estructura de carpetas
2. Health check endpoint
3. CORS configuration para permitir requests del frontend
4. Environment variables setup

Archivos a crear:

1. backend/src/main.py
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.infrastructure.api.routes import assistant, voice, screen
from src.infrastructure.config.settings import get_settings

settings = get_settings()

app = FastAPI(
    title="AI Visual Companion API",
    description="Backend para el asistente visual AI",
    version="0.1.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción: solo localhost:port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}

# Include routers
app.include_router(assistant.router, prefix="/api/assistant", tags=["assistant"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(screen.router, prefix="/api/screen", tags=["screen"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
```

2. backend/src/infrastructure/config/settings.py
```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # API Keys
    anthropic_api_key: str
    openai_api_key: str
    elevenlabs_api_key: str
    picovoice_access_key: str  # Para wake word detection

    # App Config
    app_name: str = "AI Visual Companion"
    debug: bool = True

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
```

3. backend/.env.example
```
# AI Services
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
ELEVENLABS_API_KEY=your_key_here

# Wake Word Detection
PICOVOICE_ACCESS_KEY=your_key_here

# App Configuration
APP_NAME=AI Visual Companion
DEBUG=True
```

Reglas:
- Type hints en todo el código Python
- Async/await donde sea posible
- Error handling con try/except + logging
- Pydantic para validación

Criterio de éxito:
- `uvicorn src.main:app --reload` corre sin errores
- GET /health retorna 200
- Frontend puede hacer requests
```

---

#### Feature 1.4: WebSocket Infrastructure ⭐ NUEVO

**Objetivo**: Establecer la base event-driven con WebSocket continuo, Event Bus, y loops asíncronos.

**Instrucciones para Claude CLI:**

```
Contexto:
Atlas necesita una conexión WebSocket continua entre frontend y backend
para mantener loops de wake word detection y screen monitoring.

Esta es la base fundamental que diferencia Atlas de un chatbot tradicional.

Tarea:
Implementar WebSocket Manager, Event Bus, y cliente frontend.

--- BACKEND ---

1. backend/src/infrastructure/events/event_bus.py
```python
from typing import Callable, Dict, List, Any
import asyncio
import logging

logger = logging.getLogger(__name__)

class EventBus:
    """Event bus asíncrono para comunicación interna"""

    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = {}

    def on(self, event_name: str, handler: Callable) -> None:
        """Registra listener para un evento"""
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(handler)
        logger.debug(f"Registered handler for event: {event_name}")

    async def emit(self, event_name: str, data: Any = None) -> None:
        """Emite evento a todos los listeners"""
        if event_name in self.listeners:
            logger.debug(f"Emitting event: {event_name} with {len(self.listeners[event_name])} listeners")
            for handler in self.listeners[event_name]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"Error in handler for {event_name}: {e}")

# Singleton instance
event_bus = EventBus()
```

2. backend/src/infrastructure/websocket/manager.py
```python
from fastapi import WebSocket
from typing import Dict
import asyncio
import logging
from src.infrastructure.events.event_bus import event_bus
from src.domain.entities.assistant_state import AssistantState, AssistantMode

logger = logging.getLogger(__name__)

class WebSocketManager:
    """Maneja conexiones WebSocket y loops continuos"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.assistant_states: Dict[str, AssistantState] = {}
        self.running_loops: Dict[str, bool] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """Acepta conexión y arranca loops"""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        self.assistant_states[session_id] = AssistantState(session_id=session_id)
        self.running_loops[session_id] = True

        logger.info(f"WebSocket connected: {session_id}")

        # Arranca loops continuos
        asyncio.create_task(self.wake_word_loop(session_id))
        asyncio.create_task(self.screen_monitor_loop(session_id))

    def disconnect(self, session_id: str):
        """Cierra conexión y para loops"""
        self.running_loops[session_id] = False
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        if session_id in self.assistant_states:
            del self.assistant_states[session_id]
        logger.info(f"WebSocket disconnected: {session_id}")

    async def send_event(self, session_id: str, event: dict):
        """Envía evento al frontend via WebSocket"""
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_json(event)
            except Exception as e:
                logger.error(f"Error sending event to {session_id}: {e}")

    async def wake_word_loop(self, session_id: str):
        """Loop continuo esperando wake word"""
        logger.info(f"Wake word loop started for {session_id}")

        while self.running_loops.get(session_id, False):
            try:
                # Espera data del frontend
                websocket = self.active_connections.get(session_id)
                if not websocket:
                    break

                data = await websocket.receive_json()

                if data.get("type") == "audio_chunk":
                    # TODO: Procesar con Porcupine
                    # Por ahora, placeholder
                    pass

            except Exception as e:
                logger.error(f"Error in wake word loop: {e}")
                await asyncio.sleep(1)

        logger.info(f"Wake word loop stopped for {session_id}")

    async def screen_monitor_loop(self, session_id: str):
        """Loop continuo monitoreando pantalla"""
        logger.info(f"Screen monitor loop started for {session_id}")

        while self.running_loops.get(session_id, False):
            try:
                state = self.assistant_states.get(session_id)

                if state and state.mode == AssistantMode.ACTIVE:
                    # Espera screenshot del frontend
                    # El frontend enviará screenshots cada 3s
                    pass

                await asyncio.sleep(3)  # Check every 3 seconds

            except Exception as e:
                logger.error(f"Error in screen monitor loop: {e}")
                await asyncio.sleep(3)

        logger.info(f"Screen monitor loop stopped for {session_id}")

# Singleton instance
ws_manager = WebSocketManager()
```

3. backend/src/infrastructure/api/routes/websocket.py
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.infrastructure.websocket.manager import ws_manager
import uuid
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint principal"""
    session_id = str(uuid.uuid4())

    try:
        await ws_manager.connect(websocket, session_id)

        # Mantiene conexión abierta
        while True:
            # El manager ya está procesando mensajes en los loops
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        ws_manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(session_id)
```

4. Registrar router en backend/src/main.py
```python
from src.infrastructure.api.routes import websocket

app.include_router(websocket.router, prefix="/api", tags=["websocket"])
```

--- FRONTEND ---

5. frontend/src/renderer/services/websocket.ts
```typescript
type EventHandler = (data: any) => void;

class WebSocketService {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectInterval: number = 3000;
  private eventHandlers: Map<string, EventHandler[]> = new Map();

  constructor(url: string = 'ws://localhost:8000/api/ws') {
    this.url = url;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected');
      return;
    }

    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.emit('connected', {});
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('WebSocket received:', data);

      if (data.type) {
        this.emit(data.type, data);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected, reconnecting...');
      setTimeout(() => this.connect(), this.reconnectInterval);
    };
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(type: string, data: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, ...data }));
    } else {
      console.warn('WebSocket not connected');
    }
  }

  on(eventType: string, handler: EventHandler): void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, []);
    }
    this.eventHandlers.get(eventType)!.push(handler);
  }

  private emit(eventType: string, data: any): void {
    const handlers = this.eventHandlers.get(eventType) || [];
    handlers.forEach(handler => handler(data));
  }
}

export const wsService = new WebSocketService();
```

6. frontend/src/renderer/hooks/useWebSocket.ts
```typescript
import { useEffect } from 'react';
import { wsService } from '../services/websocket';

export function useWebSocket() {
  useEffect(() => {
    wsService.connect();

    return () => {
      wsService.disconnect();
    };
  }, []);

  return {
    send: wsService.send.bind(wsService),
    on: wsService.on.bind(wsService),
  };
}
```

7. Integrar en frontend/src/renderer/App.tsx
```typescript
import { useWebSocket } from './hooks/useWebSocket';

function App() {
  const { send, on } = useWebSocket();

  useEffect(() => {
    // Listen for events from backend
    on('wake_word_detected', (data) => {
      console.log('Wake word detected!', data);
      // Update orb state
    });

    on('state_changed', (data) => {
      console.log('State changed:', data);
      // Update UI
    });
  }, []);

  return (
    <div className="app">
      {/* Orb and other components */}
    </div>
  );
}
```

Reglas:
- TypeScript estricto en frontend
- Type hints en Python
- Error handling robusto
- Auto-reconnect en frontend
- Logging para debugging
- Singleton patterns para managers

Criterio de éxito:
- WebSocket conecta al iniciar frontend
- Backend logs muestran "WebSocket connected"
- Loops se inician correctamente
- Auto-reconnect funciona
- Eventos fluyen bidireccional
```

---

### Phase 2: Voice Control (Week 2)

#### Feature 2.1: Voice Input (Whisper Integration)

**Instrucciones para Claude CLI:**

```
Contexto:
Implementar grabación de audio desde el frontend y transcripción con Whisper API.

Tareas:

1. Frontend: Hook para grabar audio
   Archivo: frontend/src/renderer/hooks/useVoice.ts

   Funcionalidad:
   - startRecording(): Inicia grabación desde micrófono
   - stopRecording(): Para y retorna Blob de audio
   - Estado: isRecording, error
   - Usar MediaRecorder API
   - Formato: webm o wav

2. Backend: Adapter de Whisper
   Archivo: backend/src/adapters/voice/whisper_adapter.py

   ```python
   from openai import OpenAI
   from src.application.interfaces.voice_service import VoiceService

   class WhisperAdapter(VoiceService):
       def __init__(self, api_key: str):
           self.client = OpenAI(api_key=api_key)

       async def transcribe(self, audio_file: bytes) -> str:
           """Transcribe audio usando Whisper API"""
           # Implementar transcripción
           # Detectar idioma (es/en)
           # Return texto transcrito
   ```

3. Backend: Endpoint para procesar audio
   Archivo: backend/src/infrastructure/api/routes/voice.py

   ```python
   from fastapi import APIRouter, UploadFile, File

   router = APIRouter()

   @router.post("/transcribe")
   async def transcribe_audio(audio: UploadFile = File(...)):
       """Recibe audio y retorna transcripción"""
       # Validar formato
       # Llamar WhisperAdapter
       # Detectar comando (activate/deactivate)
       # Return {"transcription": "...", "command": "activate"}
   ```

Datos de entrada/salida:
- Input: Audio file (webm, wav, mp3)
- Output: {"transcription": string, "language": "es"|"en", "command": null|"activate"|"deactivate"}

Criterio de éxito:
- Grabar audio desde frontend
- Enviar a backend
- Recibir transcripción correcta
- Detectar comandos "activate"/"deactivate"
```

#### Feature 2.2: Command Detection + State Management

**Instrucciones para Claude CLI:**

```
Contexto:
Implementar la lógica de detección de comandos y manejo de estado del asistente.

Tareas:

1. Domain Entity: AssistantState
   Archivo: backend/src/domain/entities/assistant_state.py

   ```python
   from enum import Enum
   from dataclasses import dataclass
   from datetime import datetime

   class AssistantMode(Enum):
       INACTIVE = "inactive"
       ACTIVE = "active"
       LISTENING = "listening"
       THINKING = "thinking"
       SPEAKING = "speaking"

   @dataclass
   class AssistantState:
       mode: AssistantMode
       language: str  # "es" | "en"
       last_interaction: datetime
       session_id: str

       def activate(self) -> None:
           """Cambia estado a ACTIVE"""
           self.mode = AssistantMode.ACTIVE
           self.last_interaction = datetime.now()

       def deactivate(self) -> None:
           """Cambia estado a INACTIVE"""
           self.mode = AssistantMode.INACTIVE
   ```

2. Use Case: ActivateAssistantUseCase
   Archivo: backend/src/application/use_cases/activate_assistant.py

   ```python
   from src.domain.entities.assistant_state import AssistantState, AssistantMode

   class ActivateAssistantUseCase:
       def __init__(self, state: AssistantState):
           self.state = state

       def execute(self) -> dict:
           """Activa el asistente"""
           self.state.activate()
           return {
               "success": True,
               "mode": self.state.mode.value,
               "message": "Activo! ¿En qué te ayudo?"
           }
   ```

3. Use Case: ProcessVoiceCommandUseCase
   Archivo: backend/src/application/use_cases/process_voice_command.py

   ```python
   class ProcessVoiceCommandUseCase:
       def __init__(
           self,
           state: AssistantState,
           activate_use_case: ActivateAssistantUseCase,
           deactivate_use_case: DeactivateAssistantUseCase
       ):
           self.state = state
           self.activate = activate_use_case
           self.deactivate = deactivate_use_case

       def execute(self, transcription: str) -> dict:
           """Procesa comando de voz"""
           text_lower = transcription.lower().strip()

           # Detectar activate
           if "activate" in text_lower or "activa" in text_lower:
               return self.activate.execute()

           # Detectar deactivate
           if "deactivate" in text_lower or "desactiva" in text_lower:
               return self.deactivate.execute()

           # No es comando, return transcription
           return {
               "success": True,
               "command": None,
               "transcription": transcription
           }
   ```

Criterio de éxito:
- Decir "activate" cambia estado a ACTIVE
- Decir "deactivate" cambia estado a INACTIVE
- Estado se persiste en memoria
- Frontend recibe update de estado
```

#### Feature 2.3: Wake Word Detection

**Instrucciones para Claude CLI:**

```
Contexto:
Implementar detección de wake word para activar Atlas de manera natural,
sin necesidad de presionar botones. El asistente debe escuchar
constantemente por "Hey Atlas", "Hello Atlas", "Hola Atlas", o simplemente "Atlas".

Tareas:

1. Backend: Wake Word Adapter con Porcupine
   Archivo: backend/src/adapters/voice/porcupine_adapter.py

   ```python
   import pvporcupine
   import struct
   from typing import Callable, Optional

   class PorcupineAdapter:
       def __init__(self, access_key: str, keywords: list[str] = None):
           """
           Inicializa Porcupine para wake word detection

           Args:
               access_key: Picovoice API key
               keywords: Lista de wake words ["hey atlas", "atlas"]
           """
           self.access_key = access_key
           self.keywords = keywords or ["hey siri"]  # Placeholder, usar custom keyword
           self.porcupine: Optional[pvporcupine.Porcupine] = None
           self.is_listening = False

       def start_listening(self, callback: Callable[[str], None]) -> None:
           """
           Inicia escucha continua de wake word

           Args:
               callback: Función a llamar cuando se detecta wake word
           """
           self.porcupine = pvporcupine.create(
               access_key=self.access_key,
               keywords=self.keywords
           )

           self.is_listening = True

           # Stream audio desde micrófono
           # Procesar chunks de audio
           # Si detecta keyword -> callback(keyword)

       def stop_listening(self) -> None:
           """Detiene la escucha de wake word"""
           self.is_listening = False
           if self.porcupine:
               self.porcupine.delete()
   ```

   **Alternativa con Whisper Streaming**:
   Si prefieres no usar Porcupine, implementa detección con Whisper:

   ```python
   class WhisperWakeWordAdapter:
       def __init__(self, openai_client, wake_words: list[str]):
           self.client = openai_client
           self.wake_words = [w.lower() for w in wake_words]
           # wake_words = ["hey atlas", "hello atlas", "hola atlas", "atlas"]

       async def listen_for_wake_word(self, audio_stream) -> bool:
           """
           Transcribe audio chunks y detecta wake words
           Return True si detecta wake word
           """
           # Transcribir chunk pequeño de audio
           transcription = await self.transcribe_chunk(audio_stream)
           text_lower = transcription.lower().strip()

           # Detectar wake words
           for wake_word in self.wake_words:
               if wake_word in text_lower:
                   return True

           return False
   ```

2. Backend: WebSocket para streaming de audio
   Archivo: backend/src/infrastructure/api/routes/voice.py

   Agregar endpoint WebSocket:
   ```python
   from fastapi import WebSocket, WebSocketDisconnect

   @router.websocket("/ws/listen")
   async def websocket_listen(websocket: WebSocket):
       """
       WebSocket para streaming continuo de audio
       Detecta wake word y activa asistente
       """
       await websocket.accept()

       wake_word_adapter = get_wake_word_adapter()

       try:
           while True:
               # Recibir audio chunk del frontend
               audio_data = await websocket.receive_bytes()

               # Procesar con wake word detector
               detected = await wake_word_adapter.detect(audio_data)

               if detected:
                   # Wake word detectado, activar asistente
                   await websocket.send_json({
                       "event": "wake_word_detected",
                       "keyword": detected
                   })

       except WebSocketDisconnect:
           print("Client disconnected")
   ```

3. Frontend: Continuous Audio Stream
   Archivo: frontend/src/renderer/hooks/useWakeWord.ts

   ```typescript
   import { useEffect, useRef, useState } from 'react';

   interface UseWakeWordReturn {
     isListening: boolean;
     startListening: () => Promise<void>;
     stopListening: () => void;
     wakeWordDetected: boolean;
   }

   export function useWakeWord(
     wsUrl: string = 'ws://localhost:8000/api/voice/ws/listen'
   ): UseWakeWordReturn {
     const [isListening, setIsListening] = useState(false);
     const [wakeWordDetected, setWakeWordDetected] = useState(false);
     const wsRef = useRef<WebSocket | null>(null);
     const mediaRecorderRef = useRef<MediaRecorder | null>(null);

     const startListening = async (): Promise<void> => {
       try {
         // Obtener stream de micrófono
         const stream = await navigator.mediaDevices.getUserMedia({
           audio: true
         });

         // Conectar WebSocket
         const ws = new WebSocket(wsUrl);
         wsRef.current = ws;

         ws.onopen = () => {
           console.log('Wake word listener connected');
           setIsListening(true);
         };

         ws.onmessage = (event) => {
           const data = JSON.parse(event.data);

           if (data.event === 'wake_word_detected') {
             console.log('Wake word detected:', data.keyword);
             setWakeWordDetected(true);

             // Reset después de 1 segundo
             setTimeout(() => setWakeWordDetected(false), 1000);
           }
         };

         // Configurar MediaRecorder para enviar chunks
         const mediaRecorder = new MediaRecorder(stream, {
           mimeType: 'audio/webm',
         });

         mediaRecorder.ondataavailable = (event) => {
           if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
             // Enviar audio chunk al backend
             ws.send(event.data);
           }
         };

         // Enviar chunks cada 500ms
         mediaRecorder.start(500);
         mediaRecorderRef.current = mediaRecorder;

       } catch (error) {
         console.error('Error starting wake word listener:', error);
       }
     };

     const stopListening = (): void => {
       if (mediaRecorderRef.current) {
         mediaRecorderRef.current.stop();
       }

       if (wsRef.current) {
         wsRef.current.close();
       }

       setIsListening(false);
     };

     return {
       isListening,
       startListening,
       stopListening,
       wakeWordDetected
     };
   }
   ```

4. Domain: Update AssistantState para wake word
   Archivo: backend/src/domain/entities/assistant_state.py

   Agregar método:
   ```python
   def wake_up(self, detected_keyword: str) -> None:
       """
       Activa el asistente mediante wake word

       Args:
           detected_keyword: Wake word que fue detectado ("hey atlas", etc)
       """
       self.mode = AssistantMode.ACTIVE
       self.last_interaction = datetime.now()
       self.last_wake_word = detected_keyword
   ```

Configuración:
- Si usas Porcupine: Necesitas API key de Picovoice (free tier disponible)
- Wake words configurables: ["hey atlas", "hello atlas", "hola atlas", "atlas"]
- También detecta contexto: "How are you today Atlas?" -> activa igual

Datos esperados:
- Input: Audio stream continuo (WebSocket)
- Output: {"event": "wake_word_detected", "keyword": "hey atlas"}

Criterio de éxito:
- Audio streaming continuo funciona sin lag
- Detecta "Hey Atlas" consistentemente
- Detecta "Atlas" solo (sin false positives)
- Latencia de detección < 500ms
- Frontend recibe notificación y activa asistente
```

#### Feature 2.4: Pause/Resume (Focus Mode)

**Instrucciones para Claude CLI:**

```
Contexto:
Implementar funcionalidad de pausa para que el usuario pueda decirle
a Atlas "stop" o "pause" cuando necesita concentrarse, y "continue" o
"resume" para retomar la asistencia sin interrupciones.

Tareas:

1. Domain: Actualizar AssistantMode enum
   Archivo: backend/src/domain/entities/assistant_state.py

   ```python
   from enum import Enum
   from dataclasses import dataclass
   from datetime import datetime

   class AssistantMode(Enum):
       INACTIVE = "inactive"      # Apagado, no escucha
       ACTIVE = "active"          # Activo, listo para conversar
       LISTENING = "listening"    # Escuchando comando de usuario
       THINKING = "thinking"      # Procesando con AI
       SPEAKING = "speaking"      # Respondiendo
       PAUSED = "paused"          # Pausado, escucha wake word pero no interrumpe

   @dataclass
   class AssistantState:
       mode: AssistantMode
       language: str
       last_interaction: datetime
       session_id: str
       paused_at: datetime | None = None

       def pause(self) -> None:
           """
           Pausa el asistente (Focus Mode)
           - No captura pantalla
           - No procesa conversaciones
           - Solo escucha wake word para reactivar
           """
           if self.mode in [AssistantMode.ACTIVE, AssistantMode.LISTENING]:
               self.mode = AssistantMode.PAUSED
               self.paused_at = datetime.now()

       def resume(self) -> None:
           """
           Resume el asistente desde pausa
           """
           if self.mode == AssistantMode.PAUSED:
               self.mode = AssistantMode.ACTIVE
               self.last_interaction = datetime.now()
               self.paused_at = None

       def is_paused(self) -> bool:
           """Check si está en modo pausa"""
           return self.mode == AssistantMode.PAUSED
   ```

2. Use Cases: Pause y Resume
   Archivo: backend/src/application/use_cases/pause_assistant.py

   ```python
   from src.domain.entities.assistant_state import AssistantState

   class PauseAssistantUseCase:
       def __init__(self, state: AssistantState):
           self.state = state

       def execute(self) -> dict:
           """
           Pausa el asistente
           """
           self.state.pause()

           return {
               "success": True,
               "mode": self.state.mode.value,
               "message": "En pausa. Di 'continue' cuando estés listo."
           }
   ```

   Archivo: backend/src/application/use_cases/resume_assistant.py

   ```python
   class ResumeAssistantUseCase:
       def __init__(self, state: AssistantState):
           self.state = state

       def execute(self) -> dict:
           """
           Resume el asistente desde pausa
           """
           self.state.resume()

           return {
               "success": True,
               "mode": self.state.mode.value,
               "message": "De vuelta! ¿En qué te ayudo?"
           }
   ```

3. Update ProcessVoiceCommandUseCase
   Archivo: backend/src/application/use_cases/process_voice_command.py

   Agregar detección de comandos pause/resume:
   ```python
   class ProcessVoiceCommandUseCase:
       def __init__(
           self,
           state: AssistantState,
           activate_use_case: ActivateAssistantUseCase,
           deactivate_use_case: DeactivateAssistantUseCase,
           pause_use_case: PauseAssistantUseCase,
           resume_use_case: ResumeAssistantUseCase
       ):
           self.state = state
           self.activate = activate_use_case
           self.deactivate = deactivate_use_case
           self.pause = pause_use_case
           self.resume = resume_use_case

       def execute(self, transcription: str) -> dict:
           """Procesa comando de voz"""
           text_lower = transcription.lower().strip()

           # Detectar pause/stop
           if any(word in text_lower for word in ["pause", "stop", "para", "detente"]):
               return self.pause.execute()

           # Detectar resume/continue
           if any(word in text_lower for word in ["continue", "resume", "continua", "vuelve"]):
               return self.resume.execute()

           # Detectar activate
           if "activate" in text_lower or "activa" in text_lower:
               return self.activate.execute()

           # Detectar deactivate
           if "deactivate" in text_lower or "desactiva" in text_lower:
               return self.deactivate.execute()

           # No es comando, return transcription
           return {
               "success": True,
               "command": None,
               "transcription": transcription
           }
   ```

4. Frontend: Visual feedback de PAUSED state
   Archivo: frontend/src/renderer/components/Orb/OrbCanvas.tsx

   Agregar estado PAUSED al componente:
   ```typescript
   interface OrbProps {
     state: 'inactive' | 'active' | 'listening' | 'thinking' | 'speaking' | 'paused';
     onClick?: () => void;
   }

   // En la lógica de animación:
   function getStateConfig(state: OrbProps['state']) {
     switch (state) {
       case 'paused':
         return {
           speed: 0.001,           // Casi estático
           particleSize: 2,
           colors: ['#FFA500'],    // Amber
           opacity: 0.5,
           pulseSpeed: 0.5,        // Pulso lento
         };
       // ... otros estados
     }
   }
   ```

5. Comportamiento durante PAUSED:
   - Screen capture: DESACTIVADO (no captura pantalla)
   - Conversación: DESACTIVADA (no procesa mensajes)
   - Wake word detection: ACTIVO (escucha "continue"/"resume")
   - Visual: Orb amber pulsando lentamente

Comandos soportados:
- Para pausar: "stop", "pause", "para", "detente", "cállate un momento"
- Para resumir: "continue", "resume", "continua", "vuelve", "hey atlas"

Criterio de éxito:
- Decir "pause" cambia estado a PAUSED
- Orb muestra color amber pulsando
- Screen capture se detiene
- No procesa conversaciones
- Decir "continue" vuelve a ACTIVE
- Orb vuelve a cyan brillante
- Screen capture se reanuda
```

---

### Phase 3: Screen Capture + Vision (Week 3)

#### Feature 3.1: Screen Capture

**Instrucciones para Claude CLI:**

```
Contexto:
Capturar la pantalla periódicamente cuando el asistente está activo.

Tareas:

1. Electron Main: Screen Capture Service
   Archivo: frontend/src/main/capture.ts

   ```typescript
   import { desktopCapturer, screen } from 'electron';

   interface CaptureOptions {
     interval?: number;  // ms, default 3000
     quality?: number;   // 0-100, default 80
   }

   export class ScreenCaptureService {
     private intervalId: NodeJS.Timer | null = null;

     async captureScreen(): Promise<Buffer> {
       // Capturar pantalla principal
       // Return PNG buffer
     }

     startAutoCapture(callback: (image: Buffer) => void, options: CaptureOptions): void {
       // Iniciar captura periódica
     }

     stopAutoCapture(): void {
       // Detener captura
     }
   }
   ```

2. Backend: OCR con Tesseract
   Archivo: backend/src/adapters/vision/tesseract_adapter.py

   ```python
   import pytesseract
   from PIL import Image
   import io

   class TesseractAdapter:
       def extract_text(self, image_bytes: bytes) -> str:
           """Extrae texto de imagen usando OCR"""
           image = Image.open(io.BytesIO(image_bytes))
           text = pytesseract.image_to_string(image, lang='eng+spa')
           return text.strip()
   ```

3. Backend: Screen Analysis Endpoint
   Archivo: backend/src/infrastructure/api/routes/screen.py

   ```python
   @router.post("/analyze")
   async def analyze_screen(
       screenshot: UploadFile = File(...),
       context: Optional[dict] = None
   ):
       """Analiza screenshot y retorna contexto"""
       # Convertir a bytes
       # Extraer texto con OCR
       # Detectar app/window (del context)
       # Return structured data
       return {
           "ocr_text": "...",
           "app_name": "...",
           "detected_elements": [...]
       }
   ```

Datos esperados:
- Input: Screenshot (PNG), app context (opcional)
- Output:
  ```json
  {
    "ocr_text": "extracted text",
    "app_context": {
      "app_name": "Visual Studio Code",
      "window_title": "index.ts"
    },
    "detected_elements": [
      {"type": "error", "text": "Type mismatch..."}
    ]
  }
  ```

Criterio de éxito:
- Captura automática cada 3 segundos cuando activo
- OCR extrae texto correctamente
- Backend retorna contexto estructurado
```

---

### Phase 4: AI Response Generation (Week 4)

#### Feature 4.1: Claude API Integration

**Instrucciones para Claude CLI:**

```
Contexto:
Integrar Claude API para generar respuestas basadas en el contexto visual.

Tareas:

1. Adapter de Claude
   Archivo: backend/src/adapters/ai/claude_adapter.py

   ```python
   from anthropic import Anthropic
   from src.application.interfaces.ai_service import AIService
   from src.infrastructure.config.master_prompt import MASTER_SYSTEM_PROMPT

   class ClaudeAdapter(AIService):
       def __init__(self, api_key: str):
           self.client = Anthropic(api_key=api_key)

       async def generate_response(
           self,
           user_message: str,
           screen_context: dict,
           conversation_history: list
       ) -> str:
           """Genera respuesta usando Claude"""

           # Build context string
           context_str = self._build_context(screen_context)

           # Build messages con historial
           messages = self._build_messages(
               conversation_history,
               user_message,
               context_str
           )

           # Call Claude API
           response = self.client.messages.create(
               model="claude-sonnet-4-20250514",
               max_tokens=1024,
               system=MASTER_SYSTEM_PROMPT,
               messages=messages
           )

           return response.content[0].text

       def _build_context(self, screen_context: dict) -> str:
           """Convierte screen context a string descriptivo"""
           # Formato:
           # "Estás viendo VS Code con archivo index.ts.
           #  Hay un error visible: Type mismatch en línea 47..."
   ```

2. Master System Prompt
   Archivo: backend/src/infrastructure/config/master_prompt.py

   ```python
   MASTER_SYSTEM_PROMPT = """
   Eres un compañero visual AI. Actúas como un amigo tech-savvy sentado
   al lado del usuario, mirando la misma pantalla.

   IMPORTANTE:
   - Tono conversacional, no formal
   - Respuestas concisas
   - Usa "veo que..." en vez de "I have detected"
   - Habla en español o inglés según el usuario
   - Si ves un error, explícalo simple y sugiere solución

   Contexto actual:
   - Recibirás información sobre lo que está en pantalla
   - Usa ese contexto para dar respuestas precisas
   - Nunca inventes información que no veas

   [... resto del prompt del artifact que creamos antes ...]
   """
   ```

3. Use Case: GenerateResponseUseCase
   Archivo: backend/src/application/use_cases/generate_response.py

   ```python
   class GenerateResponseUseCase:
       def __init__(
           self,
           ai_service: AIService,
           conversation_repo: ConversationRepository
       ):
           self.ai_service = ai_service
           self.conversation_repo = conversation_repo

       async def execute(
           self,
           user_message: str,
           screen_context: dict,
           session_id: str
       ) -> str:
           """Genera respuesta AI"""

           # Get conversation history
           history = await self.conversation_repo.get_history(session_id)

           # Generate response
           response = await self.ai_service.generate_response(
               user_message,
               screen_context,
               history
           )

           # Save to conversation
           await self.conversation_repo.add_message(
               session_id,
               "user",
               user_message
           )
           await self.conversation_repo.add_message(
               session_id,
               "assistant",
               response
           )

           return response
   ```

Criterio de éxito:
- Claude API retorna respuestas coherentes
- Respuestas referencian el screen context
- Tono conversacional y natural
- Funciona en español e inglés
```

---

## 📝 Estructura de Prompts Perfectos (Para Claude CLI)

**Basado en imagen de referencia "Estructura de un Prompt Perfecto":**

Cuando le pidas a Claude CLI que genere código, usa esta estructura:

```
1. Contexto de la tarea:
   "Estoy construyendo [X]. Actualmente tengo [Y]. Necesito [Z]."

2. Contexto del tono:
   "Mantén un tono profesional y técnico. Código limpio."

3. Datos de contexto, documentos e imágenes:
   "Aquí está el archivo actual: [código]"
   "Basándote en esta arquitectura: [diagrama]"

4. Descripción detallada de las reglas:
   "Reglas:
    - TypeScript estricto
    - Clean Architecture
    - Comentarios en español
    - Error handling completo"

5. Ejemplos:
   "Ejemplo de output esperado:
    ```typescript
    // código ejemplo
    ```"

6. Historial de la conversación:
   "Anteriormente creamos el adapter de Whisper..."

7. Descripción de la tarea:
   "Crea el use case para procesar comandos de voz..."

8. Formato de salida:
   "Devuelve solo el código, sin explicaciones adicionales."
```

---

## 🔄 Workflow de Desarrollo (Micro-build, Micro-commit)

**Inspirado en imagen de TikTok sobre desarrollo con Claude:**

### Principio: Build Small, Test Fast, Commit Often

```bash
# Ciclo de desarrollo:

1. Pide a Claude que construya 1 feature pequeña
   - "Crea solo el OrbCanvas component"

2. Prueba inmediatamente
   - npm run dev
   - Verifica que funciona

3. Commit si funciona
   - git add .
   - git commit -m "feat: add orb canvas animation"

4. Si no funciona, iteración rápida
   - "Claude, el orb no rota. Aquí está el error: [error]"
   - Fix
   - Test again

5. Repite con el siguiente feature
```

### Reglas de Oro

1. **No construyas todo de una vez**: Feature por feature
2. **Si Claude repite malas ideas**: Cierra el tab, empieza nuevo chat
3. **Siempre da contexto**: "Basándote en el código que generaste antes..."
4. **Test antes de avanzar**: No acumules código sin probar

---

## 🎯 Criterios de Éxito por Phase

### Phase 1 ✅
- [ ] Icono en system tray funcionando
- [ ] Orb window se abre/cierra
- [ ] Orb con animación de partículas smooth
- [ ] Backend corre sin errores
- [ ] /health endpoint responde

### Phase 2 ✅
- [ ] Grabar audio desde frontend
- [ ] Whisper transcribe correctamente
- [ ] "activate" cambia estado a ACTIVE
- [ ] "deactivate" cambia estado a INACTIVE
- [ ] Wake word detection funciona ("Hey Atlas", "Atlas")
- [ ] Audio streaming continuo sin lag
- [ ] Pause/Resume funciona correctamente
- [ ] Orb muestra estado PAUSED (amber)
- [ ] Screen capture se detiene en PAUSED
- [ ] Orb cambia visualización según estado

### Phase 3 ✅
- [ ] Screen capture automático cada 3s
- [ ] OCR extrae texto de pantalla
- [ ] Backend retorna contexto estructurado
- [ ] Detecta tipo de app (VS Code, browser, etc)

### Phase 4 ✅
- [ ] Claude API responde con contexto visual
- [ ] Respuestas en español/inglés
- [ ] Tono conversacional
- [ ] Memoria de conversación funciona

---

## 🐛 Debugging Tips

### Si algo no funciona:

1. **Frontend no conecta a backend**
   ```bash
   # Verificar que backend está corriendo
   curl http://localhost:8000/health

   # Check CORS en browser console
   # Fix: Agregar allow_origins correcto
   ```

2. **Orb animation laggy**
   ```typescript
   // Usar requestAnimationFrame
   // Limitar partículas a 500-800
   // Check console para warnings de performance
   ```

3. **Voice recording no funciona**
   ```javascript
   // Verificar permisos de micrófono
   navigator.permissions.query({ name: 'microphone' })

   // MediaRecorder browser support
   if (!window.MediaRecorder) {
     console.error('MediaRecorder not supported');
   }
   ```

4. **Claude API errors**
   ```python
   # Check API key
   # Verificar rate limits
   # Log request/response para debug
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

---

## 📚 Referencias y Recursos

### Documentación Oficial
- Electron: https://www.electronjs.org/docs
- FastAPI: https://fastapi.tiangolo.com
- Anthropic Claude: https://docs.anthropic.com
- OpenAI Whisper: https://platform.openai.com/docs
- Picovoice Porcupine: https://picovoice.ai/docs/porcupine/

### Code Examples
- Particle Animation: Canvas API + requestAnimationFrame
- System Tray: Electron Tray docs
- Screen Capture: desktopCapturer API

### Color References
```css
/* Palette del proyecto */
:root {
  --bg-primary: #0D0D0D;
  --orb-cyan: #00D9FF;
  --orb-purple: #7B2FFF;
  --orb-pink: #FF006E;
  --accent-green: #00FFA3;
  --text-primary: #E0E0E0;
  --text-secondary: #8A8A8A;
}
```

---

## 🚨 Reglas Importantes para Claude CLI

1. **Siempre genera código completo**: No uses `// ... rest of the code`
2. **TypeScript types explícitos**: No uses `any`
3. **Python type hints**: Usa `from typing import ...`
4. **Error handling**: Siempre try-catch o try-except
5. **Comentarios**: En español, explica la lógica compleja
6. **Testing**: Sugiere cómo testear cada feature
7. **Dependencies**: Lista las librerías nuevas que necesitas
8. **Environment**: Especifica variables de entorno requeridas

---

## 📌 Próximos Pasos

Una vez completadas las 4 phases, podemos agregar:

- [ ] Voice output (TTS con ElevenLabs)
- [ ] Long-term memory (persistencia entre sesiones)
- [ ] Hotkeys globales
- [ ] Settings UI
- [ ] Multiple language support mejorado
- [ ] Plugin system para extender funcionalidad

---

**Última actualización**: 2025-01-30
**Versión del documento**: 1.1.0
**Autor**: Ricky (con ayuda de Claude)

**Changelog v1.1.0**:
- ✨ Agregada Feature 2.3: Wake Word Detection ("Hey Atlas", "Atlas")
- ✨ Agregada Feature 2.4: Pause/Resume (Focus Mode)
- 🎨 Nuevo estado visual: PAUSED (amber pulse)
- 📦 Nueva dependencia: Porcupine (wake word detection)
- 🔧 Actualizado AssistantMode enum con estado PAUSED
