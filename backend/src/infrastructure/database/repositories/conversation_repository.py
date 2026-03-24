"""
Implementación concreta del ConversationRepository usando SQLAlchemy + SQLite.

Este adapter implementa el port definido en la capa de aplicación,
manteniendo la Clean Architecture.
"""

import logging
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.interfaces.conversation_repository import \
    ConversationRepository
from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message, MessageRole
from src.domain.entities.screen_context import ScreenContext
from src.infrastructure.database.models import (ConversationModel,
                                                MessageModel,
                                                ScreenContextModel)

logger = logging.getLogger(__name__)


class SQLiteConversationRepository(ConversationRepository):
    """
    Repositorio de conversaciones basado en SQLite via SQLAlchemy async.

    Args:
        session: Sesión asíncrona de SQLAlchemy
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ─── Mapeo ORM ↔ Dominio ──────────────────────────────────────────────────

    @staticmethod
    def _to_conversation(model: ConversationModel) -> Conversation:
        return Conversation(
            id=model.id,
            session_id=model.session_id,
            language=model.language,
            created_at=model.created_at,
            updated_at=model.updated_at,
            is_active=model.is_active,
            title=model.title,
        )

    @staticmethod
    def _to_message(model: MessageModel) -> Message:
        return Message(
            id=model.id,
            conversation_id=model.conversation_id,
            role=MessageRole(model.role),
            content=model.content,
            created_at=model.created_at,
            screen_context_id=model.screen_context_id,
            tokens_used=model.tokens_used,
            is_proactive=model.is_proactive,
            metadata=model.get_extra_data(),
        )

    @staticmethod
    def _to_screen_context(model: ScreenContextModel) -> ScreenContext:
        return ScreenContext(
            id=model.id,
            session_id=model.session_id,
            ocr_text=model.ocr_text,
            app_name=model.app_name,
            created_at=model.created_at,
            detected_errors=model.get_detected_errors(),
            language=model.language,
            url=model.url,
            shell_type=model.shell_type,
            line_numbers=model.get_line_numbers(),
            raw_analysis=model.raw_analysis,
        )

    # ─── Conversaciones ───────────────────────────────────────────────────────

    async def create_conversation(self, conversation: Conversation) -> Conversation:
        """Persiste una nueva conversación."""
        model = ConversationModel(
            id=conversation.id,
            session_id=conversation.session_id,
            language=conversation.language,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            is_active=conversation.is_active,
            title=conversation.title,
        )
        self._session.add(model)
        await self._session.flush()
        logger.debug(f"Created conversation: {conversation.id}")
        return conversation

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Obtiene una conversación por ID."""
        result = await self._session.execute(
            select(ConversationModel).where(ConversationModel.id == conversation_id)
        )
        model = result.scalar_one_or_none()
        return self._to_conversation(model) if model else None

    async def get_active_conversation_by_session(
        self, session_id: str
    ) -> Optional[Conversation]:
        """Obtiene la conversación activa de una sesión WebSocket."""
        result = await self._session.execute(
            select(ConversationModel)
            .where(
                ConversationModel.session_id == session_id,
                ConversationModel.is_active == True,  # noqa: E712
            )
            .order_by(ConversationModel.updated_at.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return self._to_conversation(model) if model else None

    async def list_conversations(
        self, limit: int = 20, offset: int = 0
    ) -> List[Conversation]:
        """Lista conversaciones ordenadas por última actualización."""
        result = await self._session.execute(
            select(ConversationModel)
            .order_by(ConversationModel.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_conversation(m) for m in result.scalars().all()]

    async def update_conversation(self, conversation: Conversation) -> Conversation:
        """Actualiza una conversación existente."""
        await self._session.execute(
            update(ConversationModel)
            .where(ConversationModel.id == conversation.id)
            .values(
                language=conversation.language,
                updated_at=conversation.updated_at,
                is_active=conversation.is_active,
                title=conversation.title,
            )
        )
        await self._session.flush()
        return conversation

    async def deactivate_conversation(self, conversation_id: str) -> None:
        """Marca una conversación como inactiva."""
        from datetime import datetime

        await self._session.execute(
            update(ConversationModel)
            .where(ConversationModel.id == conversation_id)
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        await self._session.flush()
        logger.debug(f"Deactivated conversation: {conversation_id}")

    # ─── Mensajes ─────────────────────────────────────────────────────────────

    async def add_message(self, message: Message) -> Message:
        """Persiste un mensaje en la base de datos."""
        model = MessageModel(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role.value,
            content=message.content,
            created_at=message.created_at,
            screen_context_id=message.screen_context_id,
            tokens_used=message.tokens_used,
            is_proactive=message.is_proactive,
        )
        model.set_extra_data(message.metadata)
        self._session.add(model)
        await self._session.flush()
        logger.debug(f"Saved message: {message.id} (role={message.role.value})")
        return message

    async def get_messages(
        self, conversation_id: str, limit: int = 50
    ) -> List[Message]:
        """Obtiene mensajes de una conversación, ordenados cronológicamente."""
        result = await self._session.execute(
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.asc())
            .limit(limit)
        )
        return [self._to_message(m) for m in result.scalars().all()]

    async def get_last_n_messages(
        self, conversation_id: str, n: int = 10
    ) -> List[Message]:
        """
        Obtiene los últimos N mensajes de una conversación.

        Útil para construir el historial de contexto para Claude,
        evitando superar límites de tokens.
        """
        # Subquery: toma los últimos N, luego ordena para devolver ASC
        subq = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.desc())
            .limit(n)
            .subquery()
        )
        result = await self._session.execute(
            select(MessageModel)
            .join(subq, MessageModel.id == subq.c.id)
            .order_by(MessageModel.created_at.asc())
        )
        return [self._to_message(m) for m in result.scalars().all()]

    # ─── Screen Contexts ──────────────────────────────────────────────────────

    async def save_screen_context(self, context: ScreenContext) -> ScreenContext:
        """Persiste un contexto de pantalla."""
        model = ScreenContextModel(
            id=context.id,
            session_id=context.session_id,
            ocr_text=context.ocr_text,
            app_name=context.app_name,
            created_at=context.created_at,
            language=context.language,
            url=context.url,
            shell_type=context.shell_type,
            raw_analysis=context.raw_analysis,
        )
        model.set_detected_errors(context.detected_errors)
        model.set_line_numbers(context.line_numbers)
        self._session.add(model)
        await self._session.flush()
        logger.debug(f"Saved screen context: {context.id} (app={context.app_name})")
        return context

    async def get_latest_screen_context(
        self, session_id: str
    ) -> Optional[ScreenContext]:
        """Obtiene el contexto de pantalla más reciente de una sesión."""
        result = await self._session.execute(
            select(ScreenContextModel)
            .where(ScreenContextModel.session_id == session_id)
            .order_by(ScreenContextModel.created_at.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return self._to_screen_context(model) if model else None
