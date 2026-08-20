from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from agent_api.dashboard.service import DashboardService, WorkforceProfile
from workforce_contracts.jira import JiraAccountRef, JiraIssueEvidence


def issue(
    key: str,
    *,
    assignee: str = "account-1",
    name: str = "Mohammad Gnaiem",
    status: str = "In Progress",
    remaining: int | None = 10_800,
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
        activity_timestamp=datetime(2026, 8, 20, tzinfo=UTC),
    )


class JiraReader:
    def __init__(self, issues: tuple[JiraIssueEvidence, ...]) -> None:
        self.issues = issues

    async def search_issues(self, jql: str, *, project_key: str, correlation_id: str):
        assert jql == 'project = "WFD" ORDER BY updated DESC, key ASC'
        assert project_key == "WFD"
        assert correlation_id == "corr-dashboard"
        return self.issues


class Scorer:
    async def score(self, input_data, correlation_id: str):
        return {
            "score": 88,
            "level": "critical",
            "confidence": "high",
            "factors": [],
            "evidence_timestamp": input_data.evidence_timestamp.isoformat(),
            "scoring_model_version": "employee-overload-v1",
            "evidence_references": [],
        }


@pytest.mark.asyncio
async def test_dashboard_groups_tasks_by_real_jira_assignee() -> None:
    service = DashboardService(
        jira=JiraReader(
            (
                issue("WFD-1"),
                issue("WFD-2", remaining=36_000),
                issue("WFD-3", status="Done", remaining=0),
            )
        ),
        scoring=Scorer(),
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
    )

    snapshot = await service.build("WFD", "corr-dashboard")

    assert snapshot.project.total_tasks == 3
    assert snapshot.project.completed_tasks == 1
    assert snapshot.employees[0].remaining_hours == 13
    assert snapshot.employees[0].score == 88
    assert snapshot.tasks[0].jira_url.endswith("/browse/WFD-1")


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
