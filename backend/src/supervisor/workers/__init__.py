"""
Supervisor workers — one job each, done well.

Worker contract (ver plantilla en docs/agentic-os-supervisor.md §5):
- async fn(task: str, ctx: WorkerContext) -> WorkerResult
- NUNCA lanza excepciones: los errores vuelven en el envelope.
- Solo lecturas idempotentes en v1 — nada destructivo.
- El runtime (dispatcher) maneja timeout y reintento; el worker no reintenta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from src.supervisor.schema import WorkerResult


@dataclass
class WorkerContext:
    """Everything a worker may need, injected by the dispatcher per run."""

    session_id: str
    request_id: str
    task_id: str
    notion: Any = None
    playwright: Any = None
    claude_client: Any = None
    # Inyectado por el dispatcher — emite task_progress hacia el frontend
    progress: Callable[[str], Awaitable[None]] = field(default=None)


@dataclass(frozen=True)
class WorkerSpec:
    """Registry entry: the function plus the metadata the planner sees."""

    fn: Callable[[str, WorkerContext], Awaitable[WorkerResult]]
    capability: str
    cost_tier: str
    read_only: bool
    default_timeout_ms: int


def build_registry(container) -> dict[str, WorkerSpec]:
    """
    v1 roster. Both workers are read-only and reuse container adapters —
    the doc's calendar recommendation has no adapter yet, these two prove
    the same loop (parallel fan-out, cost tiers, both timeout classes).
    """
    from src.supervisor.workers import notion_worker, research_worker

    return {
        "notion": WorkerSpec(
            fn=notion_worker.run,
            capability="Search and read pages in Ricky's Notion workspace",
            cost_tier="cheap",
            read_only=True,
            default_timeout_ms=60_000,
        ),
        "research": WorkerSpec(
            fn=research_worker.run,
            capability="Browse the web and summarize findings",
            cost_tier="expensive",
            read_only=True,
            default_timeout_ms=180_000,
        ),
    }


def registry_for_prompt(registry: dict[str, WorkerSpec]) -> list[dict]:
    """Roster as injected into the planner prompt."""
    return [
        {
            "id": agent_id,
            "capability": spec.capability,
            "costTier": spec.cost_tier,
            "readOnly": spec.read_only,
        }
        for agent_id, spec in registry.items()
    ]
