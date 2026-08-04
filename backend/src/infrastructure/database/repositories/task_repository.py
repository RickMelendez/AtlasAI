"""
Task Repository - Data access layer for supervisor tasks.

Persists dispatched subtasks, their lifecycle events (server timestamps),
and the daily budget counter. The runtime dispatcher is the only writer.

Convención del repo: recibe una AsyncSession, usa flush() — el caller
es dueño de la transacción (igual que MemoryRepository).
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (SupervisorBudgetModel,
                                                TaskEventModel, TaskModel)

logger = logging.getLogger(__name__)


class TaskRepository:
    """
    Repository for supervisor tasks, task events, and the daily budget.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Tasks ─────────────────────────────────────────────────────────────

    async def create_task(self, **fields) -> TaskModel:
        """
        Insert a new task row. `depends_on` (list) and `result` (dict)
        are accepted as convenience kwargs and serialized to JSON.
        """
        depends_on = fields.pop("depends_on", None)
        result = fields.pop("result", None)
        task = TaskModel(id=fields.pop("id", str(uuid.uuid4())), **fields)
        if depends_on:
            task.set_depends_on(depends_on)
        if result:
            task.set_result(result)
        self.session.add(task)
        await self.session.flush()
        return task

    async def get_task(self, task_id: str) -> Optional[TaskModel]:
        stmt = select(TaskModel).where(TaskModel.id == task_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        task_id: str,
        status: str,
        *,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        result: Optional[dict] = None,
        error: Optional[str] = None,
        fail_reason: Optional[str] = None,
        attempts: Optional[int] = None,
    ) -> None:
        task = await self.get_task(task_id)
        if not task:
            logger.warning(f"update_status: task {task_id} not found")
            return
        task.status = status
        if started_at is not None:
            task.started_at = started_at
        if finished_at is not None:
            task.finished_at = finished_at
        if result is not None:
            task.set_result(result)
        if error is not None:
            task.error = error
        if fail_reason is not None:
            task.fail_reason = fail_reason
        if attempts is not None:
            task.attempts = attempts
        await self.session.flush()

    async def try_transition(
        self, task_id: str, from_status: str, to_status: str
    ) -> bool:
        """
        Guarded status transition: only succeeds if the row is still in
        `from_status`. Makes double-approve/double-deny a no-op.
        """
        stmt = (
            update(TaskModel)
            .where(TaskModel.id == task_id, TaskModel.status == from_status)
            .values(status=to_status)
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1

    async def find_recent_completed_by_idem_key(
        self, key: str, window_secs: int
    ) -> Optional[TaskModel]:
        """
        Idempotency lookup: newest completed task with the same key inside
        the dedup window.
        """
        cutoff = datetime.utcnow() - timedelta(seconds=window_secs)
        stmt = (
            select(TaskModel)
            .where(
                TaskModel.idempotency_key == key,
                TaskModel.status == "completed",
                TaskModel.finished_at >= cutoff,
            )
            .order_by(TaskModel.finished_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def find_by_status(self, status: str) -> List[TaskModel]:
        stmt = (
            select(TaskModel)
            .where(TaskModel.status == status)
            .order_by(TaskModel.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # ── Events (audit log — server timestamps) ────────────────────────────

    async def add_event(
        self, task_id: str, request_id: str, event_type: str, payload: Optional[dict]
    ) -> TaskEventModel:
        event = TaskEventModel(
            id=str(uuid.uuid4()),
            task_id=task_id,
            request_id=request_id,
            event_type=event_type,
        )
        event.set_payload(payload)
        self.session.add(event)
        await self.session.flush()
        return event

    # ── Budget ────────────────────────────────────────────────────────────

    async def reserve_expensive_call(self, day: str, cap: int) -> bool:
        """
        Atomically reserve one "expensive" dispatch for the given UTC day.

        Two statements, no read-then-write gap across awaits:
        1. Ensure the day row exists (INSERT ... ON CONFLICT DO NOTHING).
        2. Guarded increment: only succeeds under the cap with the kill
           switch off. rowcount==1 means the reservation is ours.
        """
        insert_stmt = (
            sqlite_insert(SupervisorBudgetModel)
            .values(day=day, expensive_calls=0, kill_switch=False)
            .on_conflict_do_nothing(index_elements=["day"])
        )
        await self.session.execute(insert_stmt)

        update_stmt = (
            update(SupervisorBudgetModel)
            .where(
                SupervisorBudgetModel.day == day,
                SupervisorBudgetModel.expensive_calls < cap,
                SupervisorBudgetModel.kill_switch.is_(False),
            )
            .values(expensive_calls=SupervisorBudgetModel.expensive_calls + 1)
        )
        result = await self.session.execute(update_stmt)
        return result.rowcount == 1

    async def is_killed(self, day: str) -> bool:
        """DB-level kill switch check for the given UTC day."""
        stmt = select(SupervisorBudgetModel.kill_switch).where(
            SupervisorBudgetModel.day == day
        )
        result = await self.session.execute(stmt)
        value = result.scalar_one_or_none()
        return bool(value)
