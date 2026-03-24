"""
Entidad de dominio que representa el estado del asistente Atlas.

Esta es la entidad central del sistema que mantiene el estado actual
del asistente y las transiciones válidas entre estados.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AssistantMode(Enum):
    """
    Modos posibles del asistente Atlas.

    Cada modo representa un estado funcional y visual distinto del asistente.
    """

    INACTIVE = "inactive"  # Apagado, no escucha
    ACTIVE = "active"  # Activo, listo para conversar
    LISTENING = "listening"  # Escuchando comando de usuario
    THINKING = "thinking"  # Procesando con AI
    SPEAKING = "speaking"  # Respondiendo
    PAUSED = "paused"  # Pausado, escucha wake word pero no interrumpe


@dataclass
class AssistantState:
    """
    Estado del asistente Atlas.

    Mantiene el modo actual, idioma preferido, timestamps y metadatos
    de la sesión del asistente.

    Attributes:
        session_id: ID único de la sesión
        mode: Modo actual del asistente
        language: Idioma preferido ("es" | "en")
        last_interaction: Timestamp de la última interacción
        paused_at: Timestamp de cuando se pausó (si está en PAUSED)
        last_wake_word: Último wake word detectado
        created_at: Timestamp de creación del estado
    """

    session_id: str
    mode: AssistantMode = AssistantMode.INACTIVE
    language: str = "en"
    last_interaction: datetime = field(default_factory=datetime.now)
    paused_at: Optional[datetime] = None
    last_wake_word: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def activate(self) -> None:
        """
        Activa el asistente, cambiando el estado a ACTIVE.

        Este método se llama cuando el usuario activa explícitamente
        el asistente o cuando se detecta un wake word.
        """
        if self.mode in [AssistantMode.INACTIVE, AssistantMode.PAUSED]:
            self.mode = AssistantMode.ACTIVE
            self.last_interaction = datetime.now()
            self.paused_at = None

    def deactivate(self) -> None:
        """
        Desactiva el asistente, cambiando el estado a INACTIVE.

        El asistente deja de procesar comandos y conversaciones,
        pero puede seguir escuchando el wake word si está configurado.
        """
        self.mode = AssistantMode.INACTIVE
        self.last_interaction = datetime.now()
        self.paused_at = None

    def pause(self) -> None:
        """
        Pausa el asistente (Focus Mode).

        En modo PAUSED:
        - No captura pantalla
        - No procesa conversaciones
        - Solo escucha wake word para reactivar
        - Útil cuando el usuario necesita concentrarse sin interrupciones
        """
        if self.mode in [AssistantMode.ACTIVE, AssistantMode.LISTENING]:
            self.mode = AssistantMode.PAUSED
            self.paused_at = datetime.now()

    def resume(self) -> None:
        """
        Resume el asistente desde pausa.

        Vuelve al estado ACTIVE para continuar con las funciones normales.
        """
        if self.mode == AssistantMode.PAUSED:
            self.mode = AssistantMode.ACTIVE
            self.last_interaction = datetime.now()
            self.paused_at = None

    def wake_up(self, detected_keyword: str) -> None:
        """
        Activa el asistente mediante wake word.

        Este método se llama cuando el sistema de wake word detection
        detecta una palabra clave como "Hey Atlas", "Atlas", etc.

        Args:
            detected_keyword: Wake word que fue detectado
        """
        self.mode = AssistantMode.ACTIVE
        self.last_interaction = datetime.now()
        self.last_wake_word = detected_keyword
        self.paused_at = None

    def start_listening(self) -> None:
        """Cambia el estado a LISTENING cuando empieza a grabar audio."""
        if self.mode in (AssistantMode.INACTIVE, AssistantMode.ACTIVE):
            self.mode = AssistantMode.LISTENING
            self.last_interaction = datetime.now()

    def start_thinking(self) -> None:
        """Cambia el estado a THINKING cuando procesa con AI."""
        if self.mode in [AssistantMode.LISTENING, AssistantMode.ACTIVE]:
            self.mode = AssistantMode.THINKING
            self.last_interaction = datetime.now()

    def start_speaking(self) -> None:
        """Cambia el estado a SPEAKING cuando empieza a responder."""
        if self.mode == AssistantMode.THINKING:
            self.mode = AssistantMode.SPEAKING
            self.last_interaction = datetime.now()

    def finish_speaking(self) -> None:
        """Vuelve a ACTIVE después de terminar de hablar."""
        if self.mode == AssistantMode.SPEAKING:
            self.mode = AssistantMode.ACTIVE
            self.last_interaction = datetime.now()

    def reset_to_active(self) -> None:
        """
        Fuerza el estado a ACTIVE desde cualquier modo.

        Usar exclusivamente para recuperación de errores en el pipeline de voz,
        cuando la excepción puede haberse lanzado en cualquier punto de la
        transición LISTENING → THINKING → SPEAKING.
        """
        self.mode = AssistantMode.ACTIVE
        self.last_interaction = datetime.now()

    def is_paused(self) -> bool:
        """Verifica si el asistente está en modo pausa."""
        return self.mode == AssistantMode.PAUSED

    def is_active(self) -> bool:
        """Verifica si el asistente está activo (en cualquier modo activo)."""
        return self.mode in [
            AssistantMode.ACTIVE,
            AssistantMode.LISTENING,
            AssistantMode.THINKING,
            AssistantMode.SPEAKING,
        ]

    def can_process_messages(self) -> bool:
        """
        Verifica si el asistente puede procesar mensajes.

        Returns:
            True si está en un estado que permite procesar conversaciones
        """
        return self.mode in [
            AssistantMode.ACTIVE,
            AssistantMode.LISTENING,
            AssistantMode.THINKING,
        ]

    def to_dict(self) -> dict:
        """
        Convierte el estado a diccionario para serialización.

        Returns:
            Diccionario con todos los campos del estado
        """
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "language": self.language,
            "last_interaction": self.last_interaction.isoformat(),
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "last_wake_word": self.last_wake_word,
            "created_at": self.created_at.isoformat(),
            "is_paused": self.is_paused(),
            "is_active": self.is_active(),
            "can_process_messages": self.can_process_messages(),
        }
