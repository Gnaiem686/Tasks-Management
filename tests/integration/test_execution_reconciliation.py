from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from workforce_persistence.database import Database
from workforce_persistence.execution_repository import DatabaseReconciliationStore
from workforce_persistence.models import ProposalExecution, ReassignmentProposal
from workforce_risk.proposals.reconciliation import (
    ReconciliationClaim,
    ReconciliationService,
)
from workforce_risk.proposals.state import ProposalState

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://workforce:workforce-local-only@127.0.0.1:5432/workforce",
)


class Reader:
    def __init__(self, observed: str | BaseException) -> None:
        self.observed = observed
        self.calls = 0

    async def read_assignee(self, issue_key: str, *, correlation_id: str) -> str | None:
        self.calls += 1
        if isinstance(self.observed, BaseException):
            raise self.observed
        return self.observed


class Store:
    def __init__(self, claims: list[ReconciliationClaim]) -> None:
        self.claims = claims
        self.resolved: list[tuple[str, ProposalState, dict[str, Any]]] = []

    async def lease_abandoned(
        self, *, worker_id: str, limit: int
    ) -> list[ReconciliationClaim]:
        claims, self.claims = self.claims[:limit], self.claims[limit:]
        return claims

    async def resolve(
        self,
        claim: ReconciliationClaim,
        *,
        state: ProposalState,
        evidence: dict[str, Any],
    ) -> None:
        self.resolved.append((claim.execution_id, state, evidence))

    async def lease_proposal(
        self, proposal_id: str, *, worker_id: str
    ) -> ReconciliationClaim | None:
        for index, item in enumerate(self.claims):
            if item.proposal_id == proposal_id:
                return self.claims.pop(index)
        return None


def claim(*, attempted: bool = True) -> ReconciliationClaim:
    return ReconciliationClaim(
        execution_id="execution-1",
        proposal_id="proposal-1",
        issue_key="WRD-1",
        expected_assignee_id="old",
        proposed_assignee_id="new",
        correlation_id="corr-1",
        write_attempted=attempted,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("observed", "attempted", "expected"),
    [
        ("new", True, ProposalState.EXECUTED_VERIFIED),
        ("old", False, ProposalState.EXECUTION_FAILED),
        ("old", True, ProposalState.UNCERTAIN),
        ("third", True, ProposalState.UNCERTAIN),
    ],
)
async def test_reconciliation_uses_fresh_read_without_writing(
    observed: str, attempted: bool, expected: ProposalState
) -> None:
    store, reader = Store([claim(attempted=attempted)]), Reader(observed)
    results = await ReconciliationService(store=store, reader=reader).run_once(
        worker_id="worker-1", limit=10
    )
    assert results[0].state is expected
    assert reader.calls == 1


@pytest.mark.asyncio
async def test_unavailable_jira_remains_uncertain_and_repeated_run_is_idempotent() -> (
    None
):
    store, reader = Store([claim()]), Reader(TimeoutError())
    service = ReconciliationService(store=store, reader=reader)
    first = await service.run_once(worker_id="worker-1", limit=10)
    second = await service.run_once(worker_id="worker-1", limit=10)
    assert first[0].state is ProposalState.UNCERTAIN
    assert second == []
    assert reader.calls == 1


@pytest.mark.asyncio
async def test_manager_triggered_reconciliation_uses_fresh_evidence() -> None:
    store, reader = Store([claim()]), Reader("new")
    result = await ReconciliationService(store=store, reader=reader).run_proposal(
        "proposal-1", worker_id="manager-trigger"
    )
    assert result is not None
    assert result.state is ProposalState.EXECUTED_VERIFIED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crash_after_write_is_reconciled_from_database_without_second_write() -> (
    None
):
    database = Database(DATABASE_URL)
    proposal_id, execution_id = uuid.uuid4(), uuid.uuid4()
    created_at = datetime.now(UTC) - timedelta(minutes=10)
    try:
        async with database.transaction() as session:
            session.add(
                ReassignmentProposal(
                    id=proposal_id,
                    environment="dev",
                    created_at=created_at,
                    simulation_id=f"simulation-{proposal_id}",
                    project_key="WRD",
                    task_key="WRD-1",
                    expected_assignee="old",
                    proposed_assignee="new",
                    state="executing",
                    idempotency_key=f"proposal-{proposal_id}",
                    evidence_fingerprint="a" * 64,
                    confidence="high",
                    scoring_versions=["v1"],
                    simulation_payload={"synthetic": True},
                    requested_by="manager-test",
                    expires_at=created_at + timedelta(hours=1),
                    version=2,
                )
            )
            await session.flush()
            session.add(
                ProposalExecution(
                    id=execution_id,
                    environment="dev",
                    created_at=created_at,
                    proposal_id=proposal_id,
                    state="executing",
                    external_correlation_id=f"corr-{proposal_id}",
                    result={"write_attempted": True},
                    write_attempted=True,
                )
            )
        reader = Reader("new")
        results = await ReconciliationService(
            store=DatabaseReconciliationStore(database, environment="dev"),
            reader=reader,
        ).run_once(worker_id="worker-db", limit=10)
        assert any(item.execution_id == str(execution_id) for item in results)
        async with database.transaction() as session:
            execution = await session.scalar(
                select(ProposalExecution).where(ProposalExecution.id == execution_id)
            )
            assert execution is not None
            assert execution.state == ProposalState.EXECUTED_VERIFIED.value
        assert reader.calls == 1
    finally:
        await database.close()
