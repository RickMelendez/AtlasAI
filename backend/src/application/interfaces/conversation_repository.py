"""
Interface abstracta del repositorio de conversaciones (Port en Clean Architecture).

Define el contrato que debe implementar el repositorio concreto en la capa
de infraestructura, manteniendo el dominio libre de dependencias de BD.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.domain.entities.screen_context import ScreenContext


class ConversationRepository(ABC):
    """
    Port abstracto para persistencia de conversaciones y mensajes.
    """

    # ─── Conversaciones ───────────────────────────────────────────────────────

    @abstractmethod
    async def create_conversation(self, conversation: Conversation) -> Conversation:
        """Persiste una nueva conversación y la retorna."""
        pass

    @abstractmethod
    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Obtiene una conversación por su ID."""
        pass

    @abstractmethod
    async def get_active_conversation_by_session(
        self, session_id: str
    ) -> Optional[Conversation]:
        """Obtiene la conversación activa para una sesión WebSocket."""
        pass

    @abstractmethod
    async def list_conversations(
        self, limit: int = 20, offset: int = 0
    ) -> List[Conversation]:
        """Lista conversaciones ordenadas por fecha de actualización."""
        pass

    @abstractmethod
    async def update_conversation(self, conversation: Conversation) -> Conversation:
        """Actualiza una conversación existente."""
        pass

    @abstractmethod
    async def deactivate_conversation(self, conversation_id: str) -> None:
        """Marca una conversación como inactiva."""
        pass

    # ─── Mensajes ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def add_message(self, message: Message) -> Message:
        """Agrega un mensaje a una conversación."""
        pass

    @abstractmethod
    async def get_messages(
        self, conversation_id: str, limit: int = 50
    ) -> List[Message]:
        """Obtiene los mensajes más recientes de una conversación."""
        pass

    @abstractmethod
    async def get_last_n_messages(
        self, conversation_id: str, n: int = 10
    ) -> List[Message]:
        """Obtiene los últimos N mensajes para construir historial de Claude."""
        pass

    # ─── Screen Contexts ──────────────────────────────────────────────────────

    @abstractmethod
    async def save_screen_context(self, context: ScreenContext) -> ScreenContext:
        """Persiste un contexto de pantalla capturado."""
        pass

    @abstractmethod
    async def get_latest_screen_context(
        self, session_id: str
    ) -> Optional[ScreenContext]:
        """Obtiene el contexto de pantalla más reciente de una sesión."""
        pass
