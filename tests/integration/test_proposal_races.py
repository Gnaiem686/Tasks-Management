from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from workforce_persistence.database import Database
from workforce_persistence.proposal_repository import ProposalRepository
from workforce_persistence.simulation_repository import SimulationRepository
from workforce_risk.models import ConfidenceLevel
from workforce_risk.proposals.models import (
    ProposalActor,
    ProposalCreateCommand,
    ProposalDecisionCommand,
    StoredSimulation,
)
from workforce_risk.proposals.state import ProposalState

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://workforce:workforce-local-only@127.0.0.1:5432/workforce",
)
NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


def actor(role: str = "manager") -> ProposalActor:
    return ProposalActor(
        actor_id="manager-safe",
        role=role,
        environment="test",
        project_scopes=("WRD",),
        correlation_id="corr-proposal",
    )


def create_command(
    marker: str, *, expires_at: datetime | None = None
) -> ProposalCreateCommand:
    return ProposalCreateCommand(
        simulation=StoredSimulation(
            simulation_id=f"simulation-{marker}",
            environment="test",
            project_key="WRD",
            task_id="WRD-1",
            current_assignee_id="EMP-002",
            proposed_assignee_id="EMP-003",
            candidate_ids=("EMP-003",),
            confidence=ConfidenceLevel.HIGH,
            evidence_fingerprint="a" * 64,
            scoring_model_versions=("employee-v1", "task-v1", "project-v1"),
            simulated_at=NOW,
            safe_payload={"score_before": 88, "score_after": 30},
        ),
        idempotency_key=f"create-{marker}",
        expires_at=expires_at or NOW + timedelta(hours=1),
        requested_at=NOW,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_approval_are_idempotent_and_duplicate_race_is_closed() -> (
    None
):
    database = Database(DATABASE_URL)
    marker = str(uuid.uuid4())
    try:
        async with database.transaction() as session:
            repository = ProposalRepository(session)
            command = create_command(marker)
            await SimulationRepository(session).persist(command.simulation)
            first = await repository.create_from_stored_simulation(
                simulation_id=command.simulation.simulation_id,
                idempotency_key=command.idempotency_key,
                expires_at=command.expires_at,
                requested_at=command.requested_at,
                actor=actor(),
            )
            repeated = await repository.create_from_stored_simulation(
                simulation_id=command.simulation.simulation_id,
                idempotency_key=command.idempotency_key,
                expires_at=command.expires_at,
                requested_at=command.requested_at,
                actor=actor(),
            )
            assert first.proposal_id == repeated.proposal_id
        decision = ProposalDecisionCommand(
            proposal_id=first.proposal_id,
            expected_version=1,
            decision="approve",
            idempotency_key=f"approve-{marker}",
            current_evidence_fingerprint="a" * 64,
            decided_at=NOW,
        )
        async with database.transaction() as session:
            approved = await ProposalRepository(session).decide(decision, actor())
            assert approved.state is ProposalState.EXECUTING
        async with database.transaction() as session:
            repeated = await ProposalRepository(session).decide(decision, actor())
            assert repeated.state is ProposalState.EXECUTING
            with pytest.raises(ValueError, match="not pending|version"):
                await ProposalRepository(session).decide(
                    decision.model_copy(update={"idempotency_key": f"other-{marker}"}),
                    actor(),
                )
    finally:
        await database.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_proposal_cannot_be_created_from_unstored_simulation() -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            with pytest.raises(ValueError, match="stored simulation"):
                await ProposalRepository(session).create_from_stored_simulation(
                    simulation_id="not-stored",
                    idempotency_key="missing-simulation",
                    expires_at=NOW + timedelta(hours=1),
                    requested_at=NOW,
                    actor=actor(),
                )
    finally:
        await database.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fingerprint", "expired", "expected"),
    [
        ("b" * 64, False, ProposalState.STALE),
        ("a" * 64, True, ProposalState.EXPIRED),
    ],
)
async def test_stale_or_expired_proposal_never_enters_execution(
    fingerprint: str, expired: bool, expected: ProposalState
) -> None:
    database = Database(DATABASE_URL)
    marker = str(uuid.uuid4())
    try:
        command = create_command(marker)
        async with database.transaction() as session:
            proposal = await ProposalRepository(session).create(command, actor())
        decision = ProposalDecisionCommand(
            proposal_id=proposal.proposal_id,
            expected_version=1,
            decision="approve",
            idempotency_key=f"decide-{marker}",
            current_evidence_fingerprint=fingerprint,
            decided_at=NOW + timedelta(hours=2) if expired else NOW,
        )
        async with database.transaction() as session:
            result = await ProposalRepository(session).decide(decision, actor())
            assert result.state is expected
    finally:
        await database.close()
