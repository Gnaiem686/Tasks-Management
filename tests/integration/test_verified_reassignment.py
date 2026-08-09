from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from jira_mcp_client.mutation import JiraAssigneeMutationClient
from sqlalchemy import select
from workforce_persistence.database import Database
from workforce_persistence.execution_repository import DatabaseExecutionStore
from workforce_persistence.models import ProposalExecution, ReassignmentProposal
from workforce_persistence.proposal_repository import ProposalRepository
from workforce_risk.models import ConfidenceLevel
from workforce_risk.proposals.execution import (
    ExecutionClaim,
    ExecutionResult,
    ReassignmentExecutionService,
)
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


class Transport:
    def __init__(self) -> None:
        self.assignee = "old"
        self.edit_count = 0

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, correlation_id: str
    ) -> dict[str, Any]:
        if name == "editJiraIssue":
            self.edit_count += 1
            self.assignee = arguments["fields"]["assignee"]["accountId"]
            return {"status": "success"}
        return {
            "schema_version": "1.0",
            "environment": "dev",
            "correlation_id": correlation_id,
            "status": "success",
            "data": {"fields": {"assignee": {"accountId": self.assignee}}},
        }


class Store:
    def __init__(self) -> None:
        self.finished: ExecutionResult | None = None

    async def prepare(
        self, proposal_id: str, correlation_id: str
    ) -> ExecutionClaim | ExecutionResult:
        if self.finished is not None:
            return self.finished
        return ExecutionClaim(
            execution_id="execution-1",
            proposal_id=proposal_id,
            environment="dev",
            project_key="WRD",
            issue_key="WRD-1",
            expected_assignee_id="old",
            proposed_assignee_id="new",
            idempotency_key="execute-1",
            correlation_id=correlation_id,
        )

    async def finalize(
        self, claim: ExecutionClaim, result: ExecutionResult
    ) -> ExecutionResult:
        self.finished = result
        return result

    async def mark_write_attempted(self, claim: ExecutionClaim) -> None:
        pass


@pytest.mark.asyncio
async def test_execution_is_verified_and_duplicate_does_not_write_again() -> None:
    transport, store = Transport(), Store()
    service = ReassignmentExecutionService(
        store=store,
        mutator=JiraAssigneeMutationClient(
            transport=transport, environment="dev", allowed_project_keys={"WRD"}
        ),
    )
    first = await service.execute("proposal-1", correlation_id="corr-1")
    second = await service.execute("proposal-1", correlation_id="corr-1")
    assert first.state is ProposalState.EXECUTED_VERIFIED
    assert second == first
    assert transport.edit_count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_saga_commits_before_write_and_persists_verified_result() -> (
    None
):
    marker = str(uuid.uuid4())
    now = datetime.now(UTC)
    actor = ProposalActor(
        actor_id="manager-test",
        role="manager",
        environment="dev",
        project_scopes=("WRD",),
        correlation_id=f"corr-{marker}",
    )
    database, transport = Database(DATABASE_URL), Transport()
    try:
        command = ProposalCreateCommand(
            simulation=StoredSimulation(
                simulation_id=f"simulation-{marker}",
                environment="dev",
                project_key="WRD",
                task_id="WRD-1",
                current_assignee_id="old",
                proposed_assignee_id="new",
                candidate_ids=("new",),
                confidence=ConfidenceLevel.HIGH,
                evidence_fingerprint="a" * 64,
                scoring_model_versions=("employee-v1", "task-v1", "project-v1"),
                simulated_at=now,
                safe_payload={"synthetic": True},
            ),
            idempotency_key=f"create-{marker}",
            requested_at=now,
            expires_at=now + timedelta(hours=1),
        )
        async with database.transaction() as session:
            proposal = await ProposalRepository(session).create(command, actor)
        async with database.transaction() as session:
            proposal = await ProposalRepository(session).decide(
                ProposalDecisionCommand(
                    proposal_id=proposal.proposal_id,
                    expected_version=1,
                    decision="approve",
                    idempotency_key=f"approve-{marker}",
                    current_evidence_fingerprint="a" * 64,
                    decided_at=now,
                ),
                actor,
            )
        service = ReassignmentExecutionService(
            store=DatabaseExecutionStore(database, environment="dev"),
            mutator=JiraAssigneeMutationClient(
                transport=transport, environment="dev", allowed_project_keys={"WRD"}
            ),
        )
        result = await service.execute(
            proposal.proposal_id, correlation_id=actor.correlation_id
        )
        duplicate = await service.execute(
            proposal.proposal_id, correlation_id=actor.correlation_id
        )
        assert result.state is ProposalState.EXECUTED_VERIFIED
        assert duplicate.state is ProposalState.EXECUTED_VERIFIED
        assert transport.edit_count == 1
        async with database.transaction() as session:
            stored_proposal = await session.get(
                ReassignmentProposal, uuid.UUID(proposal.proposal_id)
            )
            stored_execution = await session.scalar(
                select(ProposalExecution).where(
                    ProposalExecution.proposal_id == uuid.UUID(proposal.proposal_id)
                )
            )
            assert stored_proposal is not None
            assert stored_execution is not None
            assert stored_proposal.state == ProposalState.EXECUTED_VERIFIED.value
            assert stored_execution.write_attempted is True
    finally:
        await database.close()
