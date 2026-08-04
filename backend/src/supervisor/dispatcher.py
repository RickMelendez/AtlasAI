"""
Supervisor dispatcher — the runtime that owns every guarantee.

El modelo planifica; este módulo garantiza. Nada de lo que pasa aquí depende
de que el LLM "se acuerde": eventos de lifecycle con timestamps del servidor,
allSettled (un fallo nunca oculta a sus hermanos), timeouts por subtarea,
exactamente un reintento en errores transitorios, dedup por idempotencia,
presupuesto diario con hard-stop, y parking de confirmaciones en SQLite.

Reglas de transacción: cada transición de estado es su propia transacción
corta — NUNCA se mantiene una sesión abierta mientras corre un worker
(SQLite tiene un solo writer).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Awaitable, Callable, Optional

from src.infrastructure.database import AsyncSessionFactory
from src.infrastructure.database.repositories.task_repository import TaskRepository
from src.infrastructure.config.settings import get_settings
from src.supervisor.schema import (DispatchPlan, Subtask, SubtaskOutcome,
                                   WorkerResult, compute_idempotency_key,
                                   compute_waves)
from src.supervisor.workers import WorkerContext, WorkerSpec

logger = logging.getLogger(__name__)

# (session_id, {"type": ..., "data": ...}) -> Awaitable
EmitFn = Callable[[str, dict], Awaitable[None]]

_WIRE_RESULT_CAP = 2000  # chars de data que viajan por el WS; la DB guarda todo


class Dispatcher:
    def __init__(
        self,
        registry: dict[str, WorkerSpec],
        container=None,
        send_event: Optional[EmitFn] = None,
        session_factory=AsyncSessionFactory,
        settings=None,
    ):
        self.registry = registry
        self.container = container
        self.send_event = send_event or (lambda sid, ev: asyncio.sleep(0))
        self.session_factory = session_factory
        self.settings = settings or get_settings()

    # ── Public API ─────────────────────────────────────────────────────────

    async def run_plan(
        self, plan: DispatchPlan, *, session_id: str, request_id: str
    ) -> list[SubtaskOutcome]:
        """
        Execute the plan wave by wave. Inside a wave everything runs in
        parallel with allSettled semantics.
        """
        waves = compute_waves(plan.subtasks)
        outcomes: dict[str, SubtaskOutcome] = {}

        for wave in waves:
            runnable: list[Subtask] = []
            for st in wave:
                failed_deps = [
                    dep
                    for dep in st.depends_on
                    if outcomes.get(dep) is None
                    or outcomes[dep].status != "completed"
                ]
                if failed_deps:
                    outcomes[st.id] = await self._skip_for_dependency(
                        st, failed_deps, session_id, request_id
                    )
                else:
                    runnable.append(st)

            if not runnable:
                continue

            results = await asyncio.gather(
                *[
                    self._run_subtask(st, session_id=session_id, request_id=request_id)
                    for st in runnable
                ],
                return_exceptions=True,
            )
            for st, res in zip(runnable, results):
                if isinstance(res, BaseException):
                    # _run_subtask no debería lanzar — defensa en profundidad:
                    # una excepción inesperada se vuelve outcome, no cancela hermanos
                    logger.error(f"[dispatcher] unexpected error in {st.id}: {res}")
                    outcomes[st.id] = SubtaskOutcome(
                        task_id="",
                        subtask_id=st.id,
                        agent_id=st.agent_id,
                        task=st.task,
                        project_tag=st.project_tag,
                        status="failed",
                        fail_reason="worker_error",
                    )
                else:
                    outcomes[st.id] = res

        # devolver en el orden del plan
        return [outcomes[st.id] for st in plan.subtasks]

    async def run_single(self, task_row_id: str, session_id: str) -> Optional[SubtaskOutcome]:
        """
        Resume a parked (needs_confirmation) task after approval.

        DB-driven: the row survives restarts. Guarded transition makes
        double-approve a no-op. Kill switch and budget are re-checked at
        execution time; dedup is deliberately skipped — an approved action
        must actually run.
        """
        async with self.session_factory() as s:
            async with s.begin():
                repo = TaskRepository(s)
                row = await repo.get_task(task_row_id)
                if row is None:
                    return None
                moved = await repo.try_transition(
                    task_row_id, "needs_confirmation", "queued"
                )
            if not moved:
                return None  # ya lo manejó otra aprobación/denegación

        st = Subtask(
            id=row.subtask_id,
            agentId=row.agent_id,
            task=row.task,
            projectTag=row.project_tag,
            dependsOn=[],
            timeoutMs=row.timeout_ms,
            costTier=row.cost_tier,
            requiresConfirmation=False,  # ya aprobada
        )
        return await self._execute(
            st,
            task_id=row.id,
            idem_key=row.idempotency_key,
            session_id=session_id,
            request_id=row.request_id,
            skip_dedup=True,
        )

    # ── Internals ──────────────────────────────────────────────────────────

    async def _run_subtask(
        self, st: Subtask, *, session_id: str, request_id: str
    ) -> SubtaskOutcome:
        idem_key = compute_idempotency_key(st.agent_id, st.task)

        # 1. Persistir primero (la DB es la verdad), emitir después
        async with self.session_factory() as s:
            async with s.begin():
                repo = TaskRepository(s)
                row = await repo.create_task(
                    request_id=request_id,
                    subtask_id=st.id,
                    session_id=session_id,
                    idempotency_key=idem_key,
                    agent_id=st.agent_id,
                    task=st.task,
                    project_tag=st.project_tag,
                    depends_on=st.depends_on,
                    timeout_ms=st.timeout_ms,
                    cost_tier=st.cost_tier,
                    requires_confirmation=st.requires_confirmation,
                    status="queued",
                )
                task_id = row.id
                await repo.add_event(task_id, request_id, "task_queued", None)
        await self._emit("task_queued", st, task_id, session_id, request_id)

        # 4. Parking de confirmación — antes de gastar presupuesto o ejecutar
        if st.requires_confirmation:
            await self._transition(
                task_id, request_id, "needs_confirmation", "task_needs_confirmation"
            )
            await self._emit(
                "task_needs_confirmation",
                st,
                task_id,
                session_id,
                request_id,
                extra={"action": st.task},
            )
            return self._outcome(st, task_id, "needs_confirmation")

        return await self._execute(
            st,
            task_id=task_id,
            idem_key=idem_key,
            session_id=session_id,
            request_id=request_id,
        )

    async def _execute(
        self,
        st: Subtask,
        *,
        task_id: str,
        idem_key: str,
        session_id: str,
        request_id: str,
        skip_dedup: bool = False,
    ) -> SubtaskOutcome:
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # 2. Kill switch (settings y DB)
        async with self.session_factory() as s:
            async with s.begin():
                repo = TaskRepository(s)
                killed = (
                    self.settings.supervisor_kill_switch or await repo.is_killed(today)
                )
        if killed:
            return await self._fail(
                st, task_id, session_id, request_id, "kill_switch", "kill switch active"
            )

        # 3. Idempotencia — mismo agente + misma tarea dentro de la ventana
        if not skip_dedup:
            async with self.session_factory() as s:
                async with s.begin():
                    repo = TaskRepository(s)
                    prior = await repo.find_recent_completed_by_idem_key(
                        idem_key, self.settings.supervisor_idempotency_window_secs
                    )
                    prior_result = prior.get_result() if prior else None
                    # excluirse a sí misma (la fila recién creada no está completed)
                    if prior is not None and prior.id != task_id:
                        now = datetime.utcnow()
                        await repo.update_status(
                            task_id,
                            "completed",
                            finished_at=now,
                            result=prior_result,
                        )
                        await repo.add_event(
                            task_id, request_id, "task_completed",
                            {"deduplicated": True},
                        )
                    else:
                        prior = None
            if prior is not None:
                await self._emit(
                    "task_completed",
                    st,
                    task_id,
                    session_id,
                    request_id,
                    extra={
                        "deduplicated": True,
                        "result": self._wire_result(prior_result),
                    },
                )
                return self._outcome(
                    st,
                    task_id,
                    "completed",
                    result=WorkerResult.model_validate(prior_result)
                    if prior_result
                    else None,
                    deduplicated=True,
                )

        # 5. Presupuesto — reservar ANTES de ejecutar; sin devolución en v1
        if st.cost_tier == "expensive":
            async with self.session_factory() as s:
                async with s.begin():
                    repo = TaskRepository(s)
                    reserved = await repo.reserve_expensive_call(
                        today, self.settings.supervisor_daily_budget_calls
                    )
            if not reserved:
                return await self._fail(
                    st,
                    task_id,
                    session_id,
                    request_id,
                    "budget_exceeded",
                    "daily budget for expensive tasks exhausted",
                )

        # 6. Arrancar
        started_at = datetime.utcnow()
        async with self.session_factory() as s:
            async with s.begin():
                repo = TaskRepository(s)
                await repo.update_status(task_id, "running", started_at=started_at)
                await repo.add_event(task_id, request_id, "task_started", None)
        await self._emit("task_started", st, task_id, session_id, request_id)

        # 7. Ejecutar — timeout por intento; timeout es TERMINAL (sin reintento,
        #    reintentar duplicaría el wall clock prometido). Error transitorio
        #    reintenta exactamente una vez.
        spec = self.registry[st.agent_id]
        ctx = self._make_context(st, task_id, session_id, request_id)
        attempts = 0
        result: Optional[WorkerResult] = None

        for attempt in (1, 2):
            attempts = attempt
            try:
                result = await asyncio.wait_for(
                    spec.fn(st.task, ctx), timeout=st.timeout_ms / 1000
                )
            except asyncio.TimeoutError:
                # wait_for canceló el worker (v1 es solo lectura → seguro)
                now = datetime.utcnow()
                async with self.session_factory() as s:
                    async with s.begin():
                        repo = TaskRepository(s)
                        await repo.update_status(
                            task_id,
                            "timeout",
                            finished_at=now,
                            attempts=attempts,
                            fail_reason="worker_error",
                        )
                        await repo.add_event(
                            task_id, request_id, "task_timeout",
                            {"timeout_ms": st.timeout_ms},
                        )
                await self._emit(
                    "task_timeout",
                    st,
                    task_id,
                    session_id,
                    request_id,
                    extra={"timeout_ms": st.timeout_ms},
                )
                return self._outcome(
                    st, task_id, "timeout", attempts=attempts,
                    duration_ms=int((now - started_at).total_seconds() * 1000),
                )
            except asyncio.CancelledError:
                raise  # nunca tragarse una cancelación del propio dispatcher
            except Exception as e:
                # violación de contrato (los workers no deben lanzar)
                result = WorkerResult(
                    source=st.agent_id,
                    error=str(e),
                    transient=isinstance(e, (ConnectionError, OSError)),
                )
            if result.error and result.transient and attempt == 1:
                continue  # exactamente un reintento
            break

        # 8. Terminar
        now = datetime.utcnow()
        duration_ms = int((now - started_at).total_seconds() * 1000)
        envelope = result.model_dump()

        if result.error:
            async with self.session_factory() as s:
                async with s.begin():
                    repo = TaskRepository(s)
                    await repo.update_status(
                        task_id,
                        "failed",
                        finished_at=now,
                        result=envelope,
                        error=result.error,
                        fail_reason="worker_error",
                        attempts=attempts,
                    )
                    await repo.add_event(
                        task_id, request_id, "task_failed",
                        {"reason": "worker_error", "error": result.error},
                    )
            await self._emit(
                "task_failed",
                st,
                task_id,
                session_id,
                request_id,
                extra={"reason": "worker_error", "error": result.error},
            )
            return self._outcome(
                st, task_id, "failed", result=result,
                fail_reason="worker_error", attempts=attempts, duration_ms=duration_ms,
            )

        async with self.session_factory() as s:
            async with s.begin():
                repo = TaskRepository(s)
                await repo.update_status(
                    task_id,
                    "completed",
                    finished_at=now,
                    result=envelope,
                    attempts=attempts,
                )
                await repo.add_event(task_id, request_id, "task_completed", None)
        await self._emit(
            "task_completed",
            st,
            task_id,
            session_id,
            request_id,
            extra={
                "result": self._wire_result(envelope),
                "duration_ms": duration_ms,
                "deduplicated": False,
            },
        )
        return self._outcome(
            st, task_id, "completed", result=result,
            attempts=attempts, duration_ms=duration_ms,
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _make_context(
        self, st: Subtask, task_id: str, session_id: str, request_id: str
    ) -> WorkerContext:
        async def progress(message: str) -> None:
            await self._emit(
                "task_progress",
                st,
                task_id,
                session_id,
                request_id,
                extra={"message": message},
            )

        c = self.container
        return WorkerContext(
            session_id=session_id,
            request_id=request_id,
            task_id=task_id,
            notion=getattr(c, "notion", None),
            playwright=getattr(c, "playwright", None),
            claude_client=getattr(getattr(c, "claude", None), "client", None),
            progress=progress,
        )

    async def _skip_for_dependency(
        self, st: Subtask, failed_deps: list[str], session_id: str, request_id: str
    ) -> SubtaskOutcome:
        """Dependency failed — persist as skipped, never call the worker."""
        idem_key = compute_idempotency_key(st.agent_id, st.task)
        async with self.session_factory() as s:
            async with s.begin():
                repo = TaskRepository(s)
                row = await repo.create_task(
                    request_id=request_id,
                    subtask_id=st.id,
                    session_id=session_id,
                    idempotency_key=idem_key,
                    agent_id=st.agent_id,
                    task=st.task,
                    project_tag=st.project_tag,
                    depends_on=st.depends_on,
                    timeout_ms=st.timeout_ms,
                    cost_tier=st.cost_tier,
                    requires_confirmation=st.requires_confirmation,
                    status="skipped",
                    fail_reason="dependency_failed",
                    finished_at=datetime.utcnow(),
                )
                task_id = row.id
                await repo.add_event(
                    task_id, request_id, "task_failed",
                    {"reason": "dependency_failed", "failed_deps": failed_deps},
                )
        await self._emit(
            "task_failed",
            st,
            task_id,
            session_id,
            request_id,
            extra={"reason": "dependency_failed", "failed_deps": failed_deps},
        )
        return self._outcome(st, task_id, "skipped", fail_reason="dependency_failed")

    async def _fail(
        self,
        st: Subtask,
        task_id: str,
        session_id: str,
        request_id: str,
        reason: str,
        error: str,
    ) -> SubtaskOutcome:
        now = datetime.utcnow()
        async with self.session_factory() as s:
            async with s.begin():
                repo = TaskRepository(s)
                await repo.update_status(
                    task_id, "failed", finished_at=now,
                    error=error, fail_reason=reason,
                )
                await repo.add_event(
                    task_id, request_id, "task_failed",
                    {"reason": reason, "error": error},
                )
        await self._emit(
            "task_failed",
            st,
            task_id,
            session_id,
            request_id,
            extra={"reason": reason, "error": error},
        )
        return self._outcome(st, task_id, "failed", fail_reason=reason)

    async def _transition(
        self, task_id: str, request_id: str, status: str, event_type: str
    ) -> None:
        async with self.session_factory() as s:
            async with s.begin():
                repo = TaskRepository(s)
                await repo.update_status(task_id, status)
                await repo.add_event(task_id, request_id, event_type, None)

    async def _emit(
        self,
        event_type: str,
        st: Subtask,
        task_id: str,
        session_id: str,
        request_id: str,
        extra: Optional[dict] = None,
    ) -> None:
        """
        Push a full task snapshot to the frontend. Fire-and-forget: a WS
        failure never breaks the dispatch (DB already holds the truth).
        """
        snapshot = {
            "task_id": task_id,
            "request_id": request_id,
            "subtask_id": st.id,
            "agent_id": st.agent_id,
            "task": st.task,
            "project_tag": st.project_tag,
            "cost_tier": st.cost_tier,
            "requires_confirmation": st.requires_confirmation,
            "depends_on": st.depends_on,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if extra:
            snapshot.update(extra)
        try:
            await self.send_event(session_id, {"type": event_type, "data": snapshot})
        except Exception as e:
            logger.warning(f"[dispatcher] send_event failed ({event_type}): {e}")

    def _outcome(
        self,
        st: Subtask,
        task_id: str,
        status: str,
        *,
        result: Optional[WorkerResult] = None,
        fail_reason: Optional[str] = None,
        attempts: int = 0,
        duration_ms: Optional[int] = None,
        deduplicated: bool = False,
    ) -> SubtaskOutcome:
        return SubtaskOutcome(
            task_id=task_id,
            subtask_id=st.id,
            agent_id=st.agent_id,
            task=st.task,
            project_tag=st.project_tag,
            status=status,
            result=result,
            fail_reason=fail_reason,
            attempts=attempts,
            duration_ms=duration_ms,
            deduplicated=deduplicated,
        )

    @staticmethod
    def _wire_result(envelope: Optional[dict]) -> Optional[dict]:
        """Cap the data field for the wire — the DB keeps the full envelope."""
        if not envelope:
            return envelope
        wire = dict(envelope)
        data_str = json.dumps(wire.get("data"))
        if data_str and len(data_str) > _WIRE_RESULT_CAP:
            wire["data"] = data_str[:_WIRE_RESULT_CAP] + "…"
            wire["truncated"] = True
        return wire
