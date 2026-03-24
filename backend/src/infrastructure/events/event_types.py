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


# Constantes de eventos como strings para uso directo
WAKE_WORD_DETECTED = EventType.WAKE_WORD_DETECTED.value
STATE_CHANGED = EventType.STATE_CHANGED.value
SCREEN_CONTEXT_UPDATED = EventType.SCREEN_CONTEXT_UPDATED.value
ERROR_DETECTED = EventType.ERROR_DETECTED.value
USER_FRUSTRATED = EventType.USER_FRUSTRATED.value
CONVERSATION_MESSAGE = EventType.CONVERSATION_MESSAGE.value
