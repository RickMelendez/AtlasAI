"""
Entidad de dominio que representa una conversación en Atlas AI.

Una conversación es una sesión de intercambio entre el usuario y el asistente.
Puede contener múltiples mensajes y está asociada a un session_id de WebSocket.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4


@dataclass
class Conversation:
    """
    Representa una sesión de conversación con el asistente.

    Attributes:
        id: Identificador único de la conversación
        session_id: Session ID del WebSocket que inició la conversación
        language: Idioma principal de la conversación ("es" o "en")
        created_at: Timestamp de creación
        updated_at: Timestamp de última actualización
        is_active: Si la conversación está actualmente activa
        title: Título opcional generado automáticamente
    """

    session_id: str
    language: str = "es"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    title: Optional[str] = None

    def deactivate(self) -> None:
        """Marca la conversación como inactiva."""
        self.is_active = False
        self.updated_at = datetime.utcnow()

    def update_language(self, language: str) -> None:
        """Actualiza el idioma de la conversación."""
        self.language = language
        self.updated_at = datetime.utcnow()

    def touch(self) -> None:
        """Actualiza el timestamp de la conversación."""
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict:
        """Serializa la entidad a diccionario."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "language": self.language,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_active": self.is_active,
            "title": self.title,
        }
