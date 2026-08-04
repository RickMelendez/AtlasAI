"""
Modelos ORM de SQLAlchemy para Atlas AI.

Define las tablas de la base de datos SQLite que persisten
conversaciones, mensajes y contextos de pantalla.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (Boolean, DateTime, ForeignKey, Index, Integer, String,
                        Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base


class ConversationModel(Base):
    """
    Tabla ORM para conversaciones.

    Cada fila representa una sesión de conversación con el asistente.
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(10), default="es")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relación 1:N con mensajes
    messages: Mapped[List["MessageModel"]] = relationship(
        "MessageModel",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageModel.created_at",
    )

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} session={self.session_id} active={self.is_active}>"


class MessageModel(Base):
    """
    Tabla ORM para mensajes individuales.

    Cada fila es un mensaje dentro de una conversación (user o assistant).
    """

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "user" | "assistant" | "system"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    screen_context_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("screen_contexts.id", ondelete="SET NULL"),
        nullable=True,
    )
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_proactive: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_data: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON blob for metadata

    # Relaciones
    conversation: Mapped["ConversationModel"] = relationship(
        "ConversationModel", back_populates="messages"
    )
    screen_context: Mapped[Optional["ScreenContextModel"]] = relationship(
        "ScreenContextModel", back_populates="messages"
    )

    def get_extra_data(self) -> dict:
        """Deserializa extra_data desde JSON."""
        if self.extra_data:
            return json.loads(self.extra_data)
        return {}

    def set_extra_data(self, value: dict) -> None:
        """Serializa extra_data a JSON."""
        self.extra_data = json.dumps(value) if value else None

    def __repr__(self) -> str:
        return f"<Message id={self.id} role={self.role} conv={self.conversation_id}>"


class ScreenContextModel(Base):
    """
    Tabla ORM para contextos de pantalla capturados.

    Cada fila es una captura de pantalla procesada con OCR.
    """

    __tablename__ = "screen_contexts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ocr_text: Mapped[str] = mapped_column(Text, nullable=False)
    app_name: Mapped[str] = mapped_column(String(100), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    detected_errors_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    shell_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    line_numbers_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relación inversa con mensajes
    messages: Mapped[List["MessageModel"]] = relationship(
        "MessageModel", back_populates="screen_context"
    )

    def get_detected_errors(self) -> List[str]:
        if self.detected_errors_json:
            return json.loads(self.detected_errors_json)
        return []

    def set_detected_errors(self, value: List[str]) -> None:
        self.detected_errors_json = json.dumps(value) if value else None

    def get_line_numbers(self) -> List[int]:
        if self.line_numbers_json:
            return json.loads(self.line_numbers_json)
        return []

    def set_line_numbers(self, value: List[int]) -> None:
        self.line_numbers_json = json.dumps(value) if value else None

    def __repr__(self) -> str:
        return f"<ScreenContext id={self.id} app={self.app_name} session={self.session_id}>"


class MemoryModel(Base):
    """
    Tabla ORM para memoria a largo plazo.

    Almacena hechos y preferencias del usuario que deben persistir
    entre sesiones para proporcionar un contexto personalizado.
    """

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # The fact to remember
    source: Mapped[str] = mapped_column(String(20), default="user")  # "user" | "auto"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Memory id={self.id} source={self.source}>"


class TaskModel(Base):
    """
    Tabla ORM para subtareas del Supervisor (Agentic OS).

    Cada fila es una subtarea despachada por el runtime. El estado en esta
    tabla es la verdad absoluta — los eventos WebSocket son solo notificaciones.
    """

    __tablename__ = "supervisor_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    subtask_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # id asignado por el planner ("t1"), estable entre reintentos
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # sha256 hex — calculado por el runtime, NO por el modelo
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    project_tag: Mapped[str] = mapped_column(String(50), default="personal")
    depends_on_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timeout_ms: Mapped[int] = mapped_column(Integer, default=60_000)
    cost_tier: Mapped[str] = mapped_column(
        String(12), default="cheap"
    )  # "free" | "cheap" | "expensive"
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    # queued|running|needs_confirmation|completed|failed|timeout|skipped|denied
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fail_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # worker_error|budget_exceeded|dependency_failed|kill_switch|denied_by_user
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def get_depends_on(self) -> List[str]:
        if self.depends_on_json:
            return json.loads(self.depends_on_json)
        return []

    def set_depends_on(self, value: List[str]) -> None:
        self.depends_on_json = json.dumps(value) if value else None

    def get_result(self) -> dict:
        if self.result_json:
            return json.loads(self.result_json)
        return {}

    def set_result(self, value: Optional[dict]) -> None:
        self.result_json = json.dumps(value) if value else None

    def __repr__(self) -> str:
        return f"<Task id={self.id} agent={self.agent_id} status={self.status}>"


class TaskEventModel(Base):
    """
    Tabla ORM para eventos de lifecycle de subtareas.

    Audit log con timestamps del servidor — el modelo no puede falsificarlos
    porque nunca los toca (garantía del runtime, ver docs/agentic-os-supervisor.md).
    """

    __tablename__ = "supervisor_task_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("supervisor_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def get_payload(self) -> dict:
        if self.payload_json:
            return json.loads(self.payload_json)
        return {}

    def set_payload(self, value: Optional[dict]) -> None:
        self.payload_json = json.dumps(value) if value else None

    def __repr__(self) -> str:
        return f"<TaskEvent task={self.task_id} type={self.event_type}>"


class SupervisorBudgetModel(Base):
    """
    Tabla ORM para el presupuesto diario del Supervisor.

    Una fila por día UTC. kill_switch=True detiene todos los dispatches
    (segunda capa además del flag en settings).
    """

    __tablename__ = "supervisor_budget"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # "YYYY-MM-DD" UTC
    expensive_calls: Mapped[int] = mapped_column(Integer, default=0)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<SupervisorBudget day={self.day} calls={self.expensive_calls}>"


# ─── Índices adicionales ──────────────────────────────────────────────────────

Index(
    "ix_conversations_session_active",
    ConversationModel.session_id,
    ConversationModel.is_active,
)
Index(
    "ix_messages_conversation_created",
    MessageModel.conversation_id,
    MessageModel.created_at,
)
Index(
    "ix_screen_session_created",
    ScreenContextModel.session_id,
    ScreenContextModel.created_at,
)
Index(
    "ix_supervisor_tasks_idem_created",
    TaskModel.idempotency_key,
    TaskModel.created_at,
)
Index(
    "ix_supervisor_events_task_created",
    TaskEventModel.task_id,
    TaskEventModel.created_at,
)
