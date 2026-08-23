from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from agent_api.progress_history import (
    DatabaseProgressHistoryReader,
    DatabaseProgressHistoryRecorder,
)
from workforce_contracts.jira import JiraAccountRef, JiraIssueEvidence, JiraIssueLink
from workforce_persistence.progress_repository import TaskProgressObservation


class Repository:
    def __init__(self) -> None:
        self.observations: tuple[TaskProgressObservation, ...] = ()
        self.environment = ""

    async def record_observations(
        self,
        *,
        environment: str,
        observations: tuple[TaskProgressObservation, ...],
        timezone_name: str,
    ) -> object:
        del timezone_name
        self.environment = environment
        self.observations = observations
        return object()

    async def load_history_records(
        self, *, environment: str, project_key: str, limit: int
    ) -> tuple[dict[str, object], ...]:
        assert environment == "dev"
        assert project_key == "WFD"
        assert limit == 200
        return (
            {
                "record_type": "progress_event",
                "issue_key": "WFD-5",
                "event_type": "remaining_estimate_changed",
                "old_value": 8.0,
                "new_value": 6.0,
            },
        )


@pytest.mark.asyncio
async def test_recorder_normalizes_live_jira_rows_without_inventing_progress() -> None:
    repository = Repository()
    recorder = DatabaseProgressHistoryRecorder(
        environment="dev",
        repository_factory=lambda: repository,
    )
    row = JiraIssueEvidence(
        environment="dev",
        correlation_id="corr-history",
        evidence_timestamp=datetime(2026, 8, 24, 9, 30, tzinfo=UTC),
        key="WFD-5",
        summary="Security review",
        status="Testing",
        priority="High",
        assignee=JiraAccountRef(account_id="account-1", display_name="Employee"),
        due_date=date(2026, 8, 25),
        original_estimate_seconds=28_800,
        remaining_estimate_seconds=21_600,
        time_spent_seconds=7_200,
        activity_timestamp=datetime(2026, 8, 24, 9, 20, tzinfo=UTC),
        links=(JiraIssueLink(relationship="is blocked by", issue_key="WFD-3"),),
    )

    await recorder.record("WFD", (row,), "corr-history")

    assert repository.environment == "dev"
    observation = repository.observations[0]
    assert observation.remaining_estimate_hours == 6
    assert observation.time_spent_hours == 2
    assert observation.blocked is True
    assert observation.blocker_issue_keys == ("WFD-3",)
    assert observation.captured_at == row.evidence_timestamp
    assert observation.jira_updated_at == row.activity_timestamp


@pytest.mark.asyncio
async def test_reader_returns_bounded_persisted_history() -> None:
    repository = Repository()
    reader = DatabaseProgressHistoryReader(
        environment="dev",
        repository_factory=lambda: repository,
    )

    result = await reader.load("WFD", "corr-history")

    assert result[0]["issue_key"] == "WFD-5"
    assert result[0]["event_type"] == "remaining_estimate_changed"
