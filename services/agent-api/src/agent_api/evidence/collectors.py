from __future__ import annotations

from typing import Protocol

from agent_api.dashboard.models import DashboardSnapshot
from agent_api.evidence.derivation import rank_reassignment_candidates
from agent_api.evidence.focus import build_answer_evidence
from agent_api.evidence.models import (
    EvidenceCategory,
    EvidencePlan,
    MissingData,
    UniversalEvidenceBundle,
    calculate_capacity,
)
from agent_api.task_queries import GroundedAnswerContext


class ProjectEvidenceReader(Protocol):
    async def build(
        self, project_key: str, correlation_id: str
    ) -> DashboardSnapshot: ...


class ProgressHistoryReader(Protocol):
    async def load(
        self, project_key: str, correlation_id: str
    ) -> tuple[dict[str, object], ...]: ...


class UniversalEvidenceCollector:
    """Maps evidence categories to existing read-only project evidence."""

    def __init__(
        self,
        project_reader: ProjectEvidenceReader,
        *,
        history_reader: ProgressHistoryReader | None = None,
    ) -> None:
        self._project_reader = project_reader
        self._history_reader = history_reader

    async def collect(
        self,
        plan: EvidencePlan,
        *,
        project_key: str,
        correlation_id: str,
        source_employee_id: str | None = None,
        question: str = "",
        previous_context: GroundedAnswerContext | None = None,
    ) -> UniversalEvidenceBundle:
        snapshot = await self._project_reader.build(project_key, correlation_id)
        capacities = tuple(
            item
            for employee in snapshot.employees
            if (
                item := calculate_capacity(
                    employee.capacity_hours,
                    employee.remaining_hours,
                    employee_id=employee.employee_id,
                )
            )
            is not None
        )
        missing: list[MissingData] = []
        requested = set(plan.evidence_categories)
        history: tuple[dict[str, object], ...] = ()
        if EvidenceCategory.HISTORY in requested:
            if self._history_reader is None:
                missing.append(
                    MissingData(
                        category=EvidenceCategory.HISTORY,
                        reason=(
                            "historical snapshots are unavailable from this collector"
                        ),
                        entity=f"project:{project_key}",
                    )
                )
            else:
                try:
                    history = await self._history_reader.load(
                        project_key, correlation_id
                    )
                except Exception:
                    missing.append(
                        MissingData(
                            category=EvidenceCategory.HISTORY,
                            reason="stored progress history is temporarily unavailable",
                            entity=f"project:{project_key}",
                        )
                    )
        if EvidenceCategory.OPERATIONS in requested:
            missing.append(
                MissingData(
                    category=EvidenceCategory.OPERATIONS,
                    reason="operations evidence was not requested from DevOps MCP",
                    entity=f"project:{project_key}",
                )
            )
        for employee in snapshot.employees:
            if employee.capacity_hours is None or employee.capacity_hours <= 0:
                missing.append(
                    MissingData(
                        category=EvidenceCategory.CAPACITY_AND_WORKLOAD,
                        reason="configured capacity is missing or non-positive",
                        entity=f"employee:{employee.employee_id}",
                        required_for_claim=True,
                    )
                )
            if (
                EvidenceCategory.SKILLS_AND_SENIORITY in requested
                and not employee.skills
            ):
                missing.append(
                    MissingData(
                        category=EvidenceCategory.SKILLS_AND_SENIORITY,
                        reason="documented skills are unavailable",
                        entity=f"employee:{employee.employee_id}",
                    )
                )
        task_risk = {
            task.key: (
                "high"
                if task.blocker or task.dependencies or task.due_date is None
                else "low"
            )
            for task in snapshot.tasks
        }
        if source_employee_id is None:
            normalized_question = question.casefold()
            source_employee_id = next(
                (
                    employee.employee_id
                    for employee in snapshot.employees
                    if employee.display_name.casefold() in normalized_question
                ),
                None,
            )
        ranking = (
            rank_reassignment_candidates(
                snapshot, source_employee_id=source_employee_id
            )
            if source_employee_id is not None
            else None
        )
        if ranking is not None:
            missing.extend(ranking.missing_data)
        return UniversalEvidenceBundle(
            correlation_id=correlation_id,
            project_key=project_key,
            plan=plan,
            answer_evidence=build_answer_evidence(
                question=question,
                snapshot=snapshot,
                plan=plan,
                previous_context=previous_context,
            ),
            project_snapshot=snapshot,
            capacity_and_workload=capacities,
            employee_workload_classifications={
                employee.employee_id: employee.level for employee in snapshot.employees
            },
            task_delivery_risk=task_risk,
            skills={
                employee.employee_id: employee.skills for employee in snapshot.employees
            },
            seniority={
                employee.employee_id: next(
                    (
                        level
                        for level in ("lead", "senior", "mid", "junior")
                        if level in (employee.role or "").casefold()
                    ),
                    None,
                )
                for employee in snapshot.employees
            },
            ranked_candidates=(ranking.candidates if ranking is not None else ()),
            candidate_ranking=ranking,
            history=history,
            missing_data=tuple(missing),
            source_metadata=(
                {
                    "source": "project_snapshot",
                    "schema_version": snapshot.schema_version,
                    "evidence_timestamp": snapshot.evidence_timestamp.isoformat(),
                    "correlation_id": snapshot.correlation_id,
                },
            ),
        )
