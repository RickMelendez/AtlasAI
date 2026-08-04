"""
Definiciones de tipos de eventos del sistema.

Este módulo define todas las constantes de eventos que se emiten en el sistema
Atlas. Esto ayuda a mantener consistencia y evitar errores de typo.
"""

from enum import Enum


class EventType(str, Enum):
    """
    Tipos de eventos del sistema Atlas.

    Cada evento representa una acción o cambio de estado importante
    que otros componentes pueden necesitar saber.
    """

    # Eventos de wake word
    WAKE_WORD_DETECTED = "wake_word_detected"

    # Eventos de estado del asistente
    STATE_CHANGED = "state_changed"
    ASSISTANT_ACTIVATED = "assistant_activated"
    ASSISTANT_DEACTIVATED = "assistant_deactivated"
    ASSISTANT_PAUSED = "assistant_paused"
    ASSISTANT_RESUMED = "assistant_resumed"

    # Eventos de pantalla
    SCREEN_CONTEXT_UPDATED = "screen_context_updated"
    SCREEN_CAPTURE_STARTED = "screen_capture_started"
    SCREEN_CAPTURE_STOPPED = "screen_capture_stopped"

    # Eventos de detección
    ERROR_DETECTED = "error_detected"
    USER_FRUSTRATED = "user_frustrated"

    # Eventos de conversación
    CONVERSATION_MESSAGE = "conversation_message"
    USER_MESSAGE_RECEIVED = "user_message_received"
    AI_RESPONSE_GENERATED = "ai_response_generated"

    # Eventos de conexión
    WEBSOCKET_CONNECTED = "websocket_connected"
    WEBSOCKET_DISCONNECTED = "websocket_disconnected"

    # Eventos de memoria
    MEMORY_SAVED = "memory_saved"
    MEMORY_CLEARED = "memory_cleared"
    MEMORIES_UPDATED = "memories_updated"

    # Eventos proactivos
    PROACTIVE_HELP_TRIGGERED = "proactive_help_triggered"

    # Eventos del Supervisor (Agentic OS) — lifecycle de subtareas.
    # Estos nombres se usan tal cual como "type" en los mensajes WebSocket
    # hacia el frontend (snake_case, el dispatcher del frontend usa el string exacto).
    TASK_QUEUED = "task_queued"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_TIMEOUT = "task_timeout"
    TASK_CONFLICT = "task_conflict"
    TASK_NEEDS_CONFIRMATION = "task_needs_confirmation"

    # Eventos internos del Supervisor (solo bus, no van al frontend)
    SUPERVISOR_REQUEST_RECEIVED = "supervisor_request_received"
    TASK_CONFIRMATION_RECEIVED = "task_confirmation_received"


# Constantes de eventos como strings para uso directo
WAKE_WORD_DETECTED = EventType.WAKE_WORD_DETECTED.value
STATE_CHANGED = EventType.STATE_CHANGED.value
SCREEN_CONTEXT_UPDATED = EventType.SCREEN_CONTEXT_UPDATED.value
ERROR_DETECTED = EventType.ERROR_DETECTED.value
USER_FRUSTRATED = EventType.USER_FRUSTRATED.value
CONVERSATION_MESSAGE = EventType.CONVERSATION_MESSAGE.value
MEMORY_SAVED = EventType.MEMORY_SAVED.value
MEMORY_CLEARED = EventType.MEMORY_CLEARED.value
MEMORIES_UPDATED = EventType.MEMORIES_UPDATED.value
PROACTIVE_HELP_TRIGGERED = EventType.PROACTIVE_HELP_TRIGGERED.value
