from datetime import UTC, date, datetime

import pytest
from agent_api.risk_evidence import JiraRiskEvidenceProvider
from workforce_contracts.jira import JiraIssueEvidence


def issue(
    key: str,
    *,
    employee_id: str | None = "EMP-003",
    status: str = "In Progress",
    priority: str = "High",
    due: date | None = date(2026, 8, 17),
    remaining_seconds: int | None = 43_200,
    blocker: str | None = None,
) -> JiraIssueEvidence:
    custom_fields = []
    if blocker is not None:
        custom_fields.append(
            {
                "logical_name": "blocker_category",
                "raw_field_id": "customfield_10042",
                "value": blocker,
            }
        )
    return JiraIssueEvidence.model_validate(
        {
            "environment": "test",
            "correlation_id": "corr-risk",
            "evidence_timestamp": "2026-08-18T10:00:00Z",
            "key": key,
            "summary": f"Task {key}",
            "status": status,
            "priority": priority,
            "assignee": None,
            "due_date": due,
            "original_estimate_seconds": 72_000,
            "remaining_estimate_seconds": remaining_seconds,
            "workforce_employee_id": employee_id,
            "activity_timestamp": "2026-08-17T09:00:00Z",
            "links": [{"relationship": "is blocked by", "issue_key": "WRD-9"}],
            "custom_fields": custom_fields,
            "evidence_references": [
                {
                    "issue_key": key,
                    "field_id": field,
                    "observed_at": "2026-08-18T10:00:00Z",
                }
                for field in (
                    "summary",
                    "status",
                    "priority",
                    "duedate",
                    "timeestimate",
                )
            ],
        }
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_current_dossier_describes_all_active_employee_tasks() -> None:
    class Jira:
        async def search_issues(
            self, jql: str, *, project_key: str, correlation_id: str
        ) -> tuple[JiraIssueEvidence, ...]:
            assert project_key == "WRD"
            assert correlation_id == "corr-risk"
            assert 'project = "WRD"' in jql
            return (
                issue("WRD-4"),
                issue(
                    "WRD-6",
                    due=date(2026, 8, 19),
                    remaining_seconds=216_000,
                    blocker="Needs manager review",
                ),
                issue("WRD-12", employee_id=None),
                issue("WRD-7", status="Done"),
            )

    dossier = await JiraRiskEvidenceProvider(
        jira=Jira(),
        capacities={"EMP-003": 40.0},
        today=lambda: date(2026, 8, 18),
    ).get_current_dossier("EMP-003", "WRD", "corr-risk")

    assert [task.key for task in dossier.tasks] == ["WRD-4", "WRD-6"]
    assert dossier.total_remaining_hours == 72.0
    assert dossier.available_capacity_hours == 40.0
    assert dossier.overdue_task_keys == ("WRD-4",)
    assert dossier.due_soon_task_keys == ("WRD-6",)
    assert dossier.blocked_task_keys == ("WRD-4", "WRD-6")
    assert dossier.tasks[1].blocker_category == "Needs manager review"
    assert "jira:WRD-6:duedate" in dossier.evidence_references
    assert dossier.observed_at == datetime(2026, 8, 18, 10, tzinfo=UTC)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_current_dossier_rejects_cross_project_rows() -> None:
    class Jira:
        async def search_issues(
            self, jql: str, *, project_key: str, correlation_id: str
        ) -> tuple[JiraIssueEvidence, ...]:
            return (issue("OTHER-1"),)

    with pytest.raises(ValueError, match="outside the requested project"):
        await JiraRiskEvidenceProvider(
            jira=Jira(),
            capacities={"EMP-003": 40.0},
            today=lambda: date(2026, 8, 18),
        ).get_current_dossier("EMP-003", "WRD", "corr-risk")
