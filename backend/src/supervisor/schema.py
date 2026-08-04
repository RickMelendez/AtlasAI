"""
Supervisor schema — the runtime contract.

DispatchPlan/Subtask is what the planner LLM must produce; WorkerResult is
what every worker must return; SubtaskOutcome is the runtime's ground truth
fed to the reconciler. Validation is strict on structure (ids, dependencies,
cycles) and lenient on values the runtime can safely clamp (timeouts).
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.infrastructure.config.settings import get_settings

CostTier = Literal["free", "cheap", "expensive"]

TERMINAL_STATUSES = {"completed", "failed", "timeout", "skipped", "denied"}


class PlanValidationError(ValueError):
    """Raised when a DispatchPlan is structurally invalid."""


class Subtask(BaseModel):
    """One unit of dispatchable work. The planner emits camelCase JSON."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    agent_id: str = Field(alias="agentId")
    task: str
    project_tag: str = Field(alias="projectTag", default="personal")
    depends_on: list[str] = Field(alias="dependsOn", default_factory=list)
    timeout_ms: int = Field(alias="timeoutMs", default=60_000)
    cost_tier: CostTier = Field(alias="costTier", default="cheap")
    requires_confirmation: bool = Field(alias="requiresConfirmation", default=False)
    # Aceptado del planner pero IGNORADO — el runtime lo recalcula para que
    # el dedup funcione entre requests distintos, no solo dentro de un plan.
    idempotency_key: Optional[str] = Field(alias="idempotencyKey", default=None)


class DispatchPlan(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    subtasks: list[Subtask] = Field(default_factory=list)
    # clarification set + subtasks vacío => preguntar al usuario, no despachar
    clarification: Optional[str] = None
    reconciliation_hint: Optional[str] = Field(
        alias="reconciliationHint", default=None
    )

    @model_validator(mode="after")
    def _validate_structure(self) -> "DispatchPlan":
        if not self.subtasks and not self.clarification:
            raise PlanValidationError("plan has no subtasks and no clarification")

        ids = [s.id for s in self.subtasks]
        if len(ids) != len(set(ids)):
            raise PlanValidationError(f"duplicate subtask ids: {ids}")

        id_set = set(ids)
        for s in self.subtasks:
            for dep in s.depends_on:
                if dep not in id_set:
                    raise PlanValidationError(
                        f"subtask {s.id} depends on unknown id {dep!r}"
                    )

        # Detección de ciclos (Kahn) — compute_waves lanza si hay ciclo
        if self.subtasks:
            compute_waves(self.subtasks)

        # Clamp de timeouts — corregible, no fatal
        max_ms = get_settings().supervisor_max_timeout_ms
        for s in self.subtasks:
            s.timeout_ms = min(max(s.timeout_ms, 1_000), max_ms)

        return self


class WorkerResult(BaseModel):
    """
    The result envelope every worker returns. Workers NEVER raise —
    failures come back as error + transient inside the envelope.
    """

    source: str
    data: Any = None
    confidence: Literal["direct", "inferred"] = "direct"
    truncated: bool = False
    notes: Optional[str] = None
    error: Optional[str] = None
    transient: bool = False  # error retryable exactly once


class SubtaskOutcome(BaseModel):
    """Runtime ground truth for one subtask — what actually happened."""

    task_id: str
    subtask_id: str
    agent_id: str
    task: str
    project_tag: str = "personal"
    status: Literal[
        "completed", "failed", "timeout", "needs_confirmation", "skipped", "denied"
    ]
    result: Optional[WorkerResult] = None
    fail_reason: Optional[str] = None
    attempts: int = 0
    duration_ms: Optional[int] = None
    deduplicated: bool = False


class ConflictReport(BaseModel):
    subtask_ids: list[str]
    claims: list[dict]  # {agent_id, claim, evidence}
    # Único valor permitido — el Supervisor nunca elige un ganador.
    resolution: Literal["surfaced_to_ricky"] = "surfaced_to_ricky"


class ReconciliationReport(BaseModel):
    statuses: list[dict]  # {subtask_id, status, line}
    conflicts: list[ConflictReport] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)  # subtask ids esperando confirmación
    spoken_summary: str


def compute_idempotency_key(agent_id: str, task: str) -> str:
    """
    sha256 of agent + normalized task text. Whitespace/case variants of the
    same request produce the same key.
    """
    normalized = " ".join(task.lower().split())
    return hashlib.sha256(f"{agent_id}|{normalized}".encode("utf-8")).hexdigest()


def compute_waves(subtasks: list[Subtask]) -> list[list[Subtask]]:
    """
    Kahn layering: wave N contains every subtask whose dependencies are all
    in waves < N. Subtasks inside a wave run in parallel (allSettled).
    """
    by_id = {s.id: s for s in subtasks}
    remaining = {s.id: set(s.depends_on) for s in subtasks}
    done: set[str] = set()
    waves: list[list[Subtask]] = []
    while remaining:
        ready = sorted(sid for sid, deps in remaining.items() if deps <= done)
        if not ready:
            raise PlanValidationError(
                f"dependency cycle among: {sorted(remaining.keys())}"
            )
        waves.append([by_id[sid] for sid in ready])
        done.update(ready)
        for sid in ready:
            remaining.pop(sid)
    return waves
