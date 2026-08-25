from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from agent_api.graph.intents import Intent, classify_intent
from agent_api.historical_evidence import (
    DatabaseHistoricalEvidenceReader,
    OnDemandHistoricalEvidenceReader,
    compare_dossiers,
    parse_historical_date,
)
from agent_api.risk_evidence import RiskEvidenceDossier, TaskSituation


def dossier(*, observed: str, remaining: float, blocked: bool) -> RiskEvidenceDossier:
    return RiskEvidenceDossier(
        employee_id="EMP-003",
        project_key="WRD",
        observed_at=datetime.fromisoformat(observed.replace("Z", "+00:00")),
        available_capacity_hours=40,
        total_remaining_hours=remaining,
        tasks=(
            TaskSituation(
                key="WRD-6",
                summary="Add audit schema",
                status="Blocked" if blocked else "In Progress",
                priority="Highest",
                due_date=date(2026, 8, 19),
                remaining_hours=remaining,
                blocker_category="Needs manager review" if blocked else None,
                dependencies=(),
                last_activity_at=datetime.fromisoformat(
                    observed.replace("Z", "+00:00")
                ),
                evidence_references=("jira:WRD-6:status",),
            ),
        ),
        overdue_task_keys=(),
        due_soon_task_keys=("WRD-6",),
        blocked_task_keys=("WRD-6",) if blocked else (),
        missing_evidence=(),
        evidence_references=("jira:WRD-6:status",),
    )


@pytest.mark.unit
def test_explicit_historical_question_routes_to_history() -> None:
    question = "Why did Employee 3 have high risk on August 18?"
    assert classify_intent(question, default_scope="employee") is Intent.EXPLAIN_HISTORY
    assert parse_historical_date(question, today=date(2026, 8, 20)) == date(2026, 8, 18)


@pytest.mark.unit
def test_improvement_question_routes_to_history_without_explicit_date() -> None:
    assert (
        classify_intent(
            "Has this employee's situation improved?", default_scope="employee"
        )
        is Intent.EXPLAIN_HISTORY
    )


@pytest.mark.unit
def test_comparison_reports_work_and_blocker_changes() -> None:
    earlier = dossier(observed="2026-08-18T10:00:00Z", remaining=72, blocked=True)
    later = dossier(observed="2026-08-20T10:00:00Z", remaining=48, blocked=False)

    result = compare_dossiers(earlier, later)

    assert result.remaining_hours_change == -24
    assert result.resolved_blocker_task_keys == ("WRD-6",)
    assert result.new_blocker_task_keys == ()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_database_reader_rehydrates_immutable_dossier_and_risk() -> None:
    snapshot = SimpleNamespace(
        environment="test",
        subject_id="EMP-003",
        observed_at=dossier(
            observed="2026-08-18T10:00:00Z", remaining=72, blocked=True
        ).observed_at,
        evidence={
            "risk_evidence_dossier": dossier(
                observed="2026-08-18T10:00:00Z", remaining=72, blocked=True
            ).model_dump(mode="json")
        },
    )
    risk = SimpleNamespace(
        score=88,
        level="critical",
        confidence="high",
        created_at=snapshot.observed_at,
        scoring_version="employee-overload-v1",
        factors=[],
        thresholds={"low_max": 29, "medium_max": 54, "high_max": 74},
        evidence_references=["jira:WRD-6:status"],
        missing_evidence=[],
        excluded_evidence=[],
    )

    class Result:
        def all(self) -> list[tuple[object, object]]:
            return [(snapshot, risk)]

    class Session:
        async def execute(self, _query: object) -> Result:
            return Result()

    class Database:
        @asynccontextmanager
        async def transaction(self) -> AsyncIterator[Session]:
            yield Session()

    context = await DatabaseHistoricalEvidenceReader(
        Database(), environment="test", today=lambda: date(2026, 8, 20)
    ).get_at(
        "Why did Employee 3 have high risk on August 18?",
        "EMP-003",
        "WRD",
        "corr-history",
    )

    assert context.risk.score == 88
    assert context.dossier.total_remaining_hours == 72


@pytest.mark.unit
@pytest.mark.asyncio
async def test_improvement_reader_returns_single_snapshot_as_insufficient_history() -> (
    None
):
    current_dossier = dossier(
        observed="2026-08-18T10:00:00Z", remaining=72, blocked=True
    )
    snapshot = SimpleNamespace(
        environment="test",
        subject_id="EMP-003",
        observed_at=current_dossier.observed_at,
        evidence={"risk_evidence_dossier": current_dossier.model_dump(mode="json")},
    )
    risk = SimpleNamespace(
        score=88,
        level="critical",
        confidence="high",
        created_at=snapshot.observed_at,
        scoring_version="employee-overload-v1",
        factors=[],
        thresholds={"low_max": 29, "medium_max": 54, "high_max": 74},
        evidence_references=["jira:WRD-6:status"],
        missing_evidence=[],
        excluded_evidence=[],
    )

    class Result:
        def all(self) -> list[tuple[object, object]]:
            return [(snapshot, risk)]

    class Session:
        async def execute(self, _query: object) -> Result:
            return Result()

    class Database:
        @asynccontextmanager
        async def transaction(self) -> AsyncIterator[Session]:
            yield Session()

    context = await DatabaseHistoricalEvidenceReader(
        Database(), environment="test", today=lambda: date(2026, 8, 18)
    ).get_at(
        "Has this employee's situation improved?",
        "EMP-003",
        "WRD",
        "corr-history",
    )

    assert context.dossier == current_dossier
    assert context.previous_dossier is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_on_demand_reader_closes_database_after_history_lookup() -> None:
    database = SimpleNamespace(closed=False)

    async def get_at(*_args: object) -> object:
        return "historical-context"

    async def close() -> None:
        database.closed = True

    database.close = close
    reader = SimpleNamespace(get_at=get_at)
    wrapper = OnDemandHistoricalEvidenceReader(
        reader_factory=lambda: (database, reader)
    )

    await wrapper.get_at(
        "Why was risk high on August 18?",
        "EMP-003",
        "WRD",
        "corr-history",
    )

    assert database.closed is True
