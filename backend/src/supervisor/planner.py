"""
Supervisor planner — one Claude call turns a request into a DispatchPlan.

Strict JSON validation with exactly one repair retry. Under ANTHROPIC_MOCK=1
short-circuits to a canned plan (the mock client can't produce plan JSON).
"""

from __future__ import annotations

import json
import logging
import os

from pydantic import ValidationError

from src.supervisor import prompts
from src.supervisor.schema import DispatchPlan, PlanValidationError
from src.supervisor.workers import WorkerSpec, registry_for_prompt
from src.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)


class PlanError(Exception):
    """The planner could not produce a valid DispatchPlan."""


def _block_text(response) -> str:
    """Content block text — dict under ANTHROPIC_MOCK, attr on the real API."""
    if not response.content:
        return ""
    block = response.content[0]
    return block["text"] if isinstance(block, dict) else block.text


def _extract_json(text: str) -> str:
    """Strip markdown fences and slice from the first '{' to the last '}'."""
    if "```" in text:
        # quedarse con el bloque interior si vino cercado
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("no JSON object found", text, 0)
    return text[start : end + 1]


class Planner:
    def __init__(
        self,
        client,
        registry: dict[str, WorkerSpec],
        model: str = "claude-sonnet-4-6",
    ):
        self.client = client
        self.registry = registry
        self.model = model

    async def plan(self, request: str) -> DispatchPlan:
        if os.environ.get("ANTHROPIC_MOCK") == "1":
            return DispatchPlan.model_validate(prompts.mock_plan(request))

        system = prompts.render_planner_prompt(
            prompts.ACTIVE_PROJECTS, registry_for_prompt(self.registry)
        )
        raw = await self._call(system, request)
        try:
            return self._validate(raw)
        except (ValidationError, json.JSONDecodeError, PlanError, PlanValidationError) as e:
            logger.warning(f"[planner] plan failed validation, repairing: {e}")
            raw2 = await self._call(
                system, prompts.REPAIR_PROMPT.format(error=e, previous=raw)
            )
            try:
                return self._validate(raw2)
            except (
                ValidationError,
                json.JSONDecodeError,
                PlanError,
                PlanValidationError,
            ) as e2:
                raise PlanError(f"plan invalid after repair: {e2}") from e2

    async def _call(self, system: str, user: str) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=0.2,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _block_text(response)

    def _validate(self, raw: str) -> DispatchPlan:
        plan = DispatchPlan.model_validate_json(_extract_json(raw))
        for st in plan.subtasks:
            if st.agent_id not in self.registry:
                raise PlanError(f"unknown agent {st.agent_id!r}")
            # proyecto desconocido se corrige, no falla
            if st.project_tag not in prompts.ACTIVE_PROJECTS:
                st.project_tag = "personal"
            max_ms = get_settings().supervisor_max_timeout_ms
            st.timeout_ms = min(max(st.timeout_ms, 1_000), max_ms)
        return plan
