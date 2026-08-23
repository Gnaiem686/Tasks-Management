from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from agent_api.dashboard.service import DashboardService, WorkforceProfile
from workforce_contracts.jira import JiraAccountRef, JiraIssueEvidence, JiraIssueLink


def issue(
    key: str,
    *,
    assignee: str = "account-1",
    name: str = "Mohammad Gnaiem",
    status: str = "In Progress",
    remaining: int | None = 10_800,
    time_spent: int | None = 3_600,
    links: tuple[JiraIssueLink, ...] = (),
) -> JiraIssueEvidence:
    return JiraIssueEvidence(
        environment="test",
        correlation_id="corr-dashboard",
        evidence_timestamp=datetime(2026, 8, 20, tzinfo=UTC),
        key=key,
        summary=f"Task {key}",
        status=status,
        priority="High",
        assignee=JiraAccountRef(account_id=assignee, display_name=name),
        due_date=date(2026, 8, 21),
        original_estimate_seconds=14_400,
        remaining_estimate_seconds=remaining,
        time_spent_seconds=time_spent,
        activity_timestamp=datetime(2026, 8, 20, tzinfo=UTC),
        links=links,
    )


class JiraReader:
    def __init__(self, issues: tuple[JiraIssueEvidence, ...]) -> None:
        self.issues = issues

    async def search_issues(
        self, jql: str, *, project_key: str, correlation_id: str
    ) -> tuple[JiraIssueEvidence, ...]:
        assert jql == 'project = "WFD" ORDER BY updated DESC, key ASC'
        assert project_key == "WFD"
        assert correlation_id == "corr-dashboard"
        return self.issues


class Scorer:
    def __init__(self) -> None:
        self.correlation_ids: list[str] = []
        self.inputs: list[Any] = []

    async def score(self, input_data: Any, correlation_id: str) -> dict[str, Any]:
        self.correlation_ids.append(correlation_id)
        self.inputs.append(input_data)
        return {
            "score": 88,
            "level": "critical",
            "confidence": "high",
            "factors": [],
            "evidence_timestamp": input_data.evidence_timestamp.isoformat(),
            "scoring_model_version": "employee-overload-v1",
            "evidence_references": [],
        }


class HistoryRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...], str]] = []

    async def record(
        self,
        project_key: str,
        rows: tuple[JiraIssueEvidence, ...],
        correlation_id: str,
    ) -> None:
        self.calls.append((project_key, tuple(row.key for row in rows), correlation_id))


@pytest.mark.asyncio
async def test_dashboard_groups_tasks_by_real_jira_assignee() -> None:
    history = HistoryRecorder()
    scorer = Scorer()
    service = DashboardService(
        jira=JiraReader(
            (
                issue("WFD-1"),
                issue("WFD-2", remaining=36_000),
                issue("WFD-3", status="Done", remaining=0),
            )
        ),
        scoring=scorer,
        profiles={
            "account-1": WorkforceProfile(
                employee_id="WFD-EMP-001",
                display_name="Mohammad Gnaiem",
                role="Backend Engineer",
                capacity_hours=24,
                skills=("Java", "Spring Boot"),
            )
        },
        jira_site_url="https://example.atlassian.net",
        today=lambda: date(2026, 8, 20),
        history=history,
    )

    snapshot = await service.build("WFD", "corr-dashboard")

    assert snapshot.project.total_tasks == 3
    assert snapshot.project.completed_tasks == 1
    assert snapshot.employees[0].remaining_hours == 13
    assert snapshot.employees[0].score == 88
    assert snapshot.alerts[0].score == 88
    scoring_input = scorer.inputs[0]
    assert set(scoring_input.evidence_references) == {
        "utilization",
        "overdue_work",
        "blocked_work",
        "priority_load",
        "due_soon_load",
        "active_task_count",
        "concurrent_projects",
        "stale_work",
    }
    assert (
        "profile:WFD-EMP-001:capacity"
        in scoring_input.evidence_references["utilization"]
    )
    assert "jira:WFD-1:duedate" in scoring_input.evidence_references["overdue_work"]
    assert snapshot.tasks[0].jira_url.endswith("/browse/WFD-1")
    assert snapshot.tasks[0].time_spent_hours == 1
    assert snapshot.tasks[0].jira_updated_at == datetime(2026, 8, 20, tzinfo=UTC)
    assert history.calls == [("WFD", ("WFD-1", "WFD-2", "WFD-3"), "corr-dashboard")]
    done = next(task for task in snapshot.tasks if task.key == "WFD-3")
    assert done.remaining_hours == 0
    assert done.raw_remaining_hours == 0


@pytest.mark.asyncio
async def test_dashboard_marks_missing_estimate_without_guessing() -> None:
    service = DashboardService(
        jira=JiraReader((issue("WFD-14", remaining=None),)),
        scoring=Scorer(),
        profiles={},
        jira_site_url="https://example.atlassian.net",
        today=lambda: date(2026, 8, 20),
    )

    snapshot = await service.build("WFD", "corr-dashboard")

    assert snapshot.tasks[0].remaining_hours is None
    assert "WFD-14.remaining_estimate" in snapshot.missing_evidence
    assert snapshot.employees[0].score is None
    assert snapshot.employees[0].level == "insufficient-data"


@pytest.mark.asyncio
async def test_done_task_uses_zero_effective_remaining_and_reports_stale_value() -> (
    None
):
    service = DashboardService(
        jira=JiraReader((issue("WFD-7", status="Done", remaining=21_600),)),
        scoring=Scorer(),
        profiles={},
        jira_site_url="https://example.atlassian.net",
        today=lambda: date(2026, 8, 20),
    )

    snapshot = await service.build("WFD", "corr-dashboard")

    task = snapshot.tasks[0]
    assert task.remaining_hours == 0
    assert task.raw_remaining_hours == 6
    assert task.data_quality_findings == (
        "Completed task has a non-zero Jira remaining estimate.",
    )


@pytest.mark.asyncio
async def test_dashboard_distinguishes_blocked_tasks_from_downstream_impact() -> None:
    service = DashboardService(
        jira=JiraReader(
            (
                issue(
                    "WFD-4",
                    links=(
                        JiraIssueLink(relationship="is blocked by", issue_key="WFD-2"),
                    ),
                ),
                issue(
                    "WFD-2",
                    links=(JiraIssueLink(relationship="blocks", issue_key="WFD-4"),),
                ),
            )
        ),
        scoring=Scorer(),
        profiles={},
        jira_site_url="https://example.atlassian.net",
        today=lambda: date(2026, 8, 20),
    )

    snapshot = await service.build("WFD", "corr-dashboard")

    assert snapshot.employees[0].top_risk == (
        "WFD-4 is blocked by WFD-2; WFD-2 blocks downstream task WFD-4."
    )
    assert snapshot.project.blocked_tasks == 1


@pytest.mark.asyncio
async def test_dashboard_uses_unique_child_correlation_for_each_employee_score() -> (
    None
):
    scorer = Scorer()
    service = DashboardService(
        jira=JiraReader(
            (
                issue("WFD-1", assignee="account-1", name="Employee 1"),
                issue("WFD-2", assignee="account-2", name="Employee 2"),
            )
        ),
        scoring=scorer,
        profiles={
            "account-1": WorkforceProfile(
                employee_id="EMP-001", display_name="Employee 1", capacity_hours=24
            ),
            "account-2": WorkforceProfile(
                employee_id="EMP-002", display_name="Employee 2", capacity_hours=24
            ),
        },
        jira_site_url="https://example.atlassian.net",
        today=lambda: date(2026, 8, 20),
    )

    await service.build("WFD", "corr-dashboard")

    assert len(scorer.correlation_ids) == 2
    assert len(set(scorer.correlation_ids)) == 2
    assert all(value.startswith("corr-dashboard:") for value in scorer.correlation_ids)
