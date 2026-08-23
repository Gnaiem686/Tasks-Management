from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field
from workforce_contracts.jira import JiraIssueEvidence
from workforce_risk.models import EmployeeOverloadInput

from agent_api.dashboard.models import (
    AlertSummary,
    DashboardSnapshot,
    EmployeeSummary,
    ProjectSummary,
    TaskSummary,
    WorkloadDistribution,
)
from agent_api.project_access import require_configured_project


class JiraDashboardReader(Protocol):
    async def search_issues(
        self, jql: str, *, project_key: str, correlation_id: str
    ) -> tuple[JiraIssueEvidence, ...]: ...


class DashboardScorer(Protocol):
    async def score(
        self, input_data: EmployeeOverloadInput, correlation_id: str
    ) -> dict[str, Any]: ...


class ProgressHistoryRecorder(Protocol):
    async def record(
        self,
        project_key: str,
        rows: tuple[JiraIssueEvidence, ...],
        correlation_id: str,
    ) -> None: ...


class WorkforceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str | None = None
    capacity_hours: float = Field(gt=0)
    skills: tuple[str, ...] = ()


class DashboardService:
    def __init__(
        self,
        *,
        jira: JiraDashboardReader,
        scoring: DashboardScorer,
        profiles: Mapping[str, WorkforceProfile],
        jira_site_url: str,
        today: Callable[[], date],
        environment: Literal["dev", "prod", "test"] = "test",
        history: ProgressHistoryRecorder | None = None,
    ) -> None:
        self._jira = jira
        self._scoring = scoring
        self._profiles = dict(profiles)
        self._jira_site_url = jira_site_url.rstrip("/")
        self._today = today
        self._environment = environment
        self._history = history

    async def build(self, project_key: str, correlation_id: str) -> DashboardSnapshot:
        project = require_configured_project(project_key)
        rows = await self._jira.search_issues(
            f'project = "{project.key}" ORDER BY updated DESC, key ASC',
            project_key=project.key,
            correlation_id=correlation_id,
        )
        if any(not row.key.startswith(f"{project.key}-") for row in rows):
            raise ValueError("Jira returned evidence outside the requested project")
        history_degraded = False
        if self._history is not None:
            try:
                await self._history.record(project.key, rows, correlation_id)
            except Exception:
                history_degraded = True
                logging.getLogger(__name__).exception(
                    "progress_history_record_failed correlation_id=%s project=%s",
                    correlation_id,
                    project.key,
                )
        tasks = tuple(self._task(row) for row in rows)
        active_rows = tuple(row for row in rows if not self._is_done(row.status))
        grouped: dict[str, list[JiraIssueEvidence]] = defaultdict(list)
        for row in active_rows:
            if row.assignee is not None:
                grouped[row.assignee.account_id].append(row)
        employees = tuple(
            [
                await self._employee(account_id, employee_rows, correlation_id)
                for account_id, employee_rows in grouped.items()
            ]
        )
        employees = tuple(
            sorted(
                employees, key=lambda item: (-1 * (item.score or -1), item.display_name)
            )
        )
        today = self._today()
        overdue = sum(
            row.due_date is not None and row.due_date < today for row in active_rows
        )
        due_soon = sum(
            row.due_date is not None
            and today <= row.due_date <= today + timedelta(days=7)
            for row in active_rows
        )
        blocked = sum(self._is_blocked(row) for row in active_rows)
        missing = tuple(
            f"{row.key}.remaining_estimate"
            for row in active_rows
            if row.remaining_estimate_seconds is None
        )
        completed = len(rows) - len(active_rows)
        alerts = tuple(
            AlertSummary(
                subject_id=employee.employee_id,
                severity=cast(Literal["medium", "high", "critical"], employee.level),
                score=cast(int, employee.score),
                reason=employee.top_risk,
            )
            for employee in employees
            if employee.level in {"medium", "high", "critical"}
        )
        evidence_timestamp = max(
            (row.evidence_timestamp for row in rows), default=datetime.now(UTC)
        )
        return DashboardSnapshot(
            correlation_id=correlation_id,
            evidence_timestamp=evidence_timestamp,
            project=ProjectSummary(
                key=project.key,
                name=project.name,
                total_tasks=len(rows),
                completed_tasks=completed,
                active_tasks=len(active_rows),
                overdue_tasks=overdue,
                due_soon_tasks=due_soon,
                blocked_tasks=blocked,
                missing_estimate_tasks=len(missing),
                completion_percent=round(100 * completed / len(rows)) if rows else 0,
            ),
            employees=employees,
            tasks=tasks,
            alerts=alerts,
            workload=WorkloadDistribution(
                overloaded=sum(
                    item.level in {"high", "critical"} for item in employees
                ),
                balanced=sum(item.level in {"low", "medium"} for item in employees),
                insufficient_data=sum(
                    item.level == "insufficient-data" for item in employees
                ),
            ),
            missing_evidence=missing,
            degraded=history_degraded,
            missing_sources=("progress_history",) if history_degraded else (),
        )

    async def _employee(
        self,
        account_id: str,
        rows: list[JiraIssueEvidence],
        correlation_id: str,
    ) -> EmployeeSummary:
        profile = self._profiles.get(account_id)
        display_name = rows[0].assignee.display_name if rows[0].assignee else account_id
        remaining_complete = all(
            row.remaining_estimate_seconds is not None for row in rows
        )
        remaining = (
            sum((row.remaining_estimate_seconds or 0) / 3600 for row in rows)
            if remaining_complete
            else None
        )
        score: int | None = None
        level = "insufficient-data"
        if profile is not None and remaining is not None:
            today = self._today()
            issue_refs = tuple(f"jira:{row.key}" for row in rows)
            project_key = rows[0].key.split("-", 1)[0]
            evidence_references = {
                "utilization": (
                    *(f"{ref}:remaining_estimate" for ref in issue_refs),
                    f"profile:{profile.employee_id}:capacity",
                ),
                "overdue_work": tuple(f"{ref}:duedate" for ref in issue_refs),
                "blocked_work": tuple(f"{ref}:blocker_and_links" for ref in issue_refs),
                "priority_load": tuple(f"{ref}:priority" for ref in issue_refs),
                "due_soon_load": tuple(f"{ref}:duedate" for ref in issue_refs),
                "active_task_count": tuple(f"{ref}:status" for ref in issue_refs),
                "concurrent_projects": (f"jira:{project_key}:project",),
                "stale_work": tuple(f"{ref}:updated" for ref in issue_refs),
            }
            input_data = EmployeeOverloadInput(
                employee_id=profile.employee_id,
                environment=self._environment,
                remaining_estimated_hours=remaining,
                available_capacity_hours=profile.capacity_hours,
                overdue_tasks=sum(
                    row.due_date is not None and row.due_date < today for row in rows
                ),
                blocked_or_blocking_tasks=sum(
                    self._blocker(row) is not None or bool(row.links) for row in rows
                ),
                urgent_high_priority_tasks=sum(
                    (row.priority or "").casefold() in {"high", "highest"}
                    for row in rows
                ),
                due_soon_tasks=sum(
                    row.due_date is not None
                    and today <= row.due_date <= today + timedelta(days=7)
                    for row in rows
                ),
                active_tasks=len(rows),
                concurrent_projects=1,
                stale_tasks=sum(
                    (datetime.now(UTC) - row.activity_timestamp).days >= 7
                    for row in rows
                ),
                evidence_timestamp=max(row.evidence_timestamp for row in rows),
                evidence_references=evidence_references,
            )
            child_correlation = (
                f"{correlation_id[:100]}:score:"
                f"{sha256(profile.employee_id.encode()).hexdigest()[:12]}"
            )
            result = await self._scoring.score(input_data, child_correlation)
            score = result.get("score")
            level = str(result.get("level") or "insufficient-data")
        top_risk = self._top_risk(rows, remaining, profile)
        return EmployeeSummary(
            employee_id=profile.employee_id if profile else f"jira:{account_id}",
            display_name=display_name,
            role=profile.role if profile else None,
            skills=profile.skills if profile else (),
            capacity_hours=profile.capacity_hours if profile else None,
            remaining_hours=round(remaining, 1) if remaining is not None else None,
            active_tasks=len(rows),
            score=score,
            level=cast(Any, level),
            top_risk=top_risk,
        )

    def _task(self, row: JiraIssueEvidence) -> TaskSummary:
        raw_remaining = (
            row.remaining_estimate_seconds / 3600
            if row.remaining_estimate_seconds is not None
            else None
        )
        done = self._is_done(row.status)
        data_quality_findings = (
            ("Completed task has a non-zero Jira remaining estimate.",)
            if done and raw_remaining not in {None, 0}
            else ()
        )
        return TaskSummary(
            key=row.key,
            summary=row.summary,
            status=row.status,
            priority=row.priority,
            assignee_id=row.assignee.account_id if row.assignee else None,
            assignee_name=row.assignee.display_name if row.assignee else None,
            due_date=row.due_date,
            original_hours=(
                row.original_estimate_seconds / 3600
                if row.original_estimate_seconds is not None
                else None
            ),
            remaining_hours=0 if done else raw_remaining,
            raw_remaining_hours=raw_remaining,
            time_spent_hours=(
                row.time_spent_seconds / 3600
                if row.time_spent_seconds is not None
                else None
            ),
            jira_updated_at=row.activity_timestamp,
            data_quality_findings=data_quality_findings,
            required_skills=row.required_skills,
            blocker=self._blocker(row),
            dependencies=tuple(
                f"{link.relationship}: {link.issue_key}" for link in row.links
            ),
            jira_url=f"{self._jira_site_url}/browse/{row.key}",
        )

    @staticmethod
    def _is_done(status: str) -> bool:
        return status.casefold() in {"done", "closed", "resolved"}

    @staticmethod
    def _blocker(row: JiraIssueEvidence) -> str | None:
        return next(
            (
                str(field.value)
                for field in row.custom_fields
                if field.logical_name == "blocker_category" and field.value
            ),
            None,
        )

    @classmethod
    def _is_blocked(cls, row: JiraIssueEvidence) -> bool:
        return cls._blocker(row) is not None or any(
            link.relationship.casefold().strip() == "is blocked by"
            for link in row.links
        )

    def _top_risk(
        self,
        rows: list[JiraIssueEvidence],
        remaining: float | None,
        profile: WorkforceProfile | None,
    ) -> str:
        today = self._today()
        overdue = sum(row.due_date is not None and row.due_date < today for row in rows)
        dependency_facts: list[str] = []
        for row in rows:
            blocker = self._blocker(row)
            if blocker is not None:
                dependency_facts.append(f"{row.key} has blocker {blocker}")
            for link in row.links:
                relationship = link.relationship.casefold().strip()
                if relationship == "is blocked by":
                    dependency_facts.append(f"{row.key} is blocked by {link.issue_key}")
                elif relationship == "blocks":
                    dependency_facts.append(
                        f"{row.key} blocks downstream task {link.issue_key}"
                    )
        if remaining is None:
            return "One or more active tasks is missing a remaining estimate."
        if profile and remaining > profile.capacity_hours:
            return (
                f"{remaining:g}h remaining exceeds "
                f"{profile.capacity_hours:g}h capacity."
            )
        if overdue:
            return f"{overdue} active task(s) are overdue."
        if dependency_facts:
            return "; ".join(dependency_facts) + "."
        return "Current structured workload evidence is within configured capacity."
