from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

from pydantic import ValidationError

from agent_api.evidence.models import EvidenceCategory, EvidencePlan, EvidenceScope
from agent_api.task_queries import GroundedAnswerContext

InvokeModel = Callable[[str, dict[str, object]], Awaitable[str]]

PLANNER_PROMPT = """You select evidence categories for a read-only workforce assistant.
Return one JSON object with only: scope, entities, evidence_categories, exhaustive.
scope is project, employee, task, or mixed. Entity kind is project, employee,
task, risk, or operation. Allowed evidence categories are: jira_issues,
workforce_profiles, capacity_and_workload, skills_and_seniority, risk_results,
dependencies_and_blockers, deadlines, history, operations. Select categories,
never tools. Writes are forbidden. Use exhaustive=true for list/all/which/across
the project questions. Return JSON only."""


class BedrockEvidencePlanner:
    def __init__(
        self,
        *,
        invoke: InvokeModel,
        timeout_seconds: float = 8.0,
        max_attempts: int = 2,
    ) -> None:
        self._invoke = invoke
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max(1, max_attempts)

    async def plan(
        self,
        *,
        question: str,
        project_key: str,
        employee_id: str | None,
        previous_context: GroundedAnswerContext | None,
        correlation_id: str,
    ) -> EvidencePlan:
        payload: dict[str, object] = {
            "question": question[:1_000],
            "project_key": project_key,
            "selected_employee_id": employee_id,
            "previous_context": (
                previous_context.model_dump(mode="json")
                if previous_context is not None
                else None
            ),
            "correlation_id": correlation_id,
        }
        for attempt in range(self._max_attempts):
            try:
                raw = await asyncio.wait_for(
                    self._invoke(PLANNER_PROMPT, payload), self._timeout_seconds
                )
                value = raw.strip()
                if value.startswith("```"):
                    value = value.split("\n", 1)[1].rsplit("```", 1)[0]
                plan = EvidencePlan.model_validate(json.loads(value))
                if len(set(plan.evidence_categories)) != len(plan.evidence_categories):
                    raise ValueError("duplicate evidence category")
                return plan
            except (TimeoutError, OSError):
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(min(0.05 * (2**attempt), 0.2))
                    continue
                raise
            except (json.JSONDecodeError, ValidationError, ValueError):
                return conservative_read_plan()
        raise RuntimeError("unreachable evidence-planner state")


def conservative_read_plan() -> EvidencePlan:
    """Compatibility plan for non-Bedrock test doubles and internal callers."""
    return EvidencePlan(
        scope=EvidenceScope.MIXED,
        evidence_categories=tuple(EvidenceCategory),
        exhaustive=True,
    )
