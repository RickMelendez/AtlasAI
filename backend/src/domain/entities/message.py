"""
Entidad de dominio que representa un mensaje en una conversación de Atlas AI.

Un mensaje puede ser del usuario o del asistente, y puede incluir
contexto de pantalla capturado en el momento del mensaje.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4


class MessageRole(Enum):
    """Rol del emisor del mensaje."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """
    Representa un mensaje individual dentro de una conversación.

    Attributes:
        conversation_id: ID de la conversación a la que pertenece
        role: Quién envió el mensaje (usuario, asistente, sistema)
        content: Contenido textual del mensaje
        id: Identificador único del mensaje
        created_at: Timestamp de creación
        screen_context_id: ID del contexto de pantalla asociado (opcional)
        tokens_used: Tokens consumidos al generar este mensaje (si es del asistente)
        is_proactive: Si el mensaje fue una sugerencia proactiva del asistente
        metadata: Datos adicionales en formato dict (model usado, latencia, etc.)
    """

    conversation_id: str
    role: MessageRole
    content: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    screen_context_id: Optional[str] = None
    tokens_used: Optional[int] = None
    is_proactive: bool = False
    metadata: dict = field(default_factory=dict)

    def is_from_user(self) -> bool:
        """Retorna True si el mensaje es del usuario."""
        return self.role == MessageRole.USER

    def is_from_assistant(self) -> bool:
        """Retorna True si el mensaje es del asistente."""
        return self.role == MessageRole.ASSISTANT

    def to_claude_format(self) -> dict:
        """
        Convierte el mensaje al formato requerido por la API de Claude.

        Returns:
            Diccionario compatible con el formato de mensajes de Anthropic
        """
        # Solo user y assistant son válidos en la API de Claude
        role = "user" if self.role == MessageRole.USER else "assistant"
        return {
            "role": role,
            "content": self.content,
        }

    def to_dict(self) -> dict:
        """Serializa la entidad a diccionario."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role.value,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "screen_context_id": self.screen_context_id,
            "tokens_used": self.tokens_used,
            "is_proactive": self.is_proactive,
            "metadata": self.metadata,
        }
