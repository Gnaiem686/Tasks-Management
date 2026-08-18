from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from typing import Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict
from workforce_contracts.jira import JiraIssueEvidence


class JiraRiskReader(Protocol):
    async def search_issues(
        self, jql: str, *, project_key: str, correlation_id: str
    ) -> tuple[JiraIssueEvidence, ...]: ...


class TaskSituation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str
    summary: str
    status: str
    priority: str | None
    due_date: date | None
    remaining_hours: float | None
    blocker_category: str | None
    dependencies: tuple[str, ...]
    last_activity_at: AwareDatetime
    evidence_references: tuple[str, ...]


class RiskEvidenceDossier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_id: str
    project_key: str
    observed_at: AwareDatetime
    available_capacity_hours: float
    total_remaining_hours: float | None
    tasks: tuple[TaskSituation, ...]
    overdue_task_keys: tuple[str, ...]
    due_soon_task_keys: tuple[str, ...]
    blocked_task_keys: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    evidence_references: tuple[str, ...]


class JiraRiskEvidenceProvider:
    def __init__(
        self,
        *,
        jira: JiraRiskReader,
        capacities: Mapping[str, float],
        today: Callable[[], date],
    ) -> None:
        self._jira = jira
        self._capacities = dict(capacities)
        self._today = today

    async def get_current_dossier(
        self, employee_id: str, project_key: str, correlation_id: str
    ) -> RiskEvidenceDossier:
        capacity = self._capacities.get(employee_id)
        if capacity is None:
            raise ValueError("employee capacity is not configured")
        jql = (
            f'project = "{project_key}" '
            f'AND labels = "workforce-employee:{employee_id}" '
            'AND labels != "workforce-record:employee-profile" '
            "AND statusCategory != Done ORDER BY duedate ASC, key ASC"
        )
        rows = await self._jira.search_issues(
            jql, project_key=project_key, correlation_id=correlation_id
        )
        relevant: list[JiraIssueEvidence] = []
        for row in rows:
            if not row.key.startswith(f"{project_key}-"):
                raise ValueError("Jira evidence is outside the requested project")
            if row.workforce_employee_id != employee_id:
                continue
            if row.status.casefold() in {"done", "closed", "resolved"}:
                continue
            relevant.append(row)

        tasks = tuple(self._task(row) for row in relevant)
        today = self._today()
        missing = tuple(
            sorted(
                {
                    f"{task.key}.remaining_estimate"
                    for task in tasks
                    if task.remaining_hours is None
                }
            )
        )
        remaining = (
            None
            if any(task.remaining_hours is None for task in tasks)
            else round(sum(task.remaining_hours or 0 for task in tasks), 2)
        )
        references = tuple(
            dict.fromkeys(
                reference for task in tasks for reference in task.evidence_references
            )
        )
        observed_at = max(
            (row.evidence_timestamp for row in relevant),
            default=datetime.now().astimezone(),
        )
        return RiskEvidenceDossier(
            employee_id=employee_id,
            project_key=project_key,
            observed_at=observed_at,
            available_capacity_hours=capacity,
            total_remaining_hours=remaining,
            tasks=tasks,
            overdue_task_keys=tuple(
                task.key
                for task in tasks
                if task.due_date is not None and task.due_date < today
            ),
            due_soon_task_keys=tuple(
                task.key
                for task in tasks
                if task.due_date is not None
                and today <= task.due_date <= today + timedelta(days=7)
            ),
            blocked_task_keys=tuple(
                task.key
                for task in tasks
                if task.blocker_category
                or any(
                    "block" in relationship.casefold()
                    for relationship in task.dependencies
                )
            ),
            missing_evidence=missing,
            evidence_references=references,
        )

    @staticmethod
    def _task(row: JiraIssueEvidence) -> TaskSituation:
        blocker = next(
            (
                field.value
                for field in row.custom_fields
                if field.logical_name == "blocker_category"
                and isinstance(field.value, str)
                and field.value not in {"", "None"}
            ),
            None,
        )
        references = tuple(
            f"jira:{reference.issue_key}:{reference.field_id}"
            for reference in row.evidence_references
        )
        dependencies = tuple(
            f"{link.relationship}: {link.issue_key}" for link in row.links
        )
        return TaskSituation(
            key=row.key,
            summary=row.summary,
            status=row.status,
            priority=row.priority,
            due_date=row.due_date,
            remaining_hours=(
                None
                if row.remaining_estimate_seconds is None
                else row.remaining_estimate_seconds / 3600
            ),
            blocker_category=blocker,
            dependencies=dependencies,
            last_activity_at=row.activity_timestamp,
            evidence_references=references,
        )
