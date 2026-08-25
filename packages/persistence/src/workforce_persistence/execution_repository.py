from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from workforce_risk.proposals.execution import (
    ExecutionClaim,
    ExecutionResult,
)
from workforce_risk.proposals.reconciliation import ReconciliationClaim
from workforce_risk.proposals.state import ProposalState, validate_transition

from workforce_persistence.database import Database
from workforce_persistence.models import ProposalExecution, ReassignmentProposal
from workforce_persistence.outbox_repository import OutboxRepository
from workforce_persistence.repositories import AuditRepository


class DatabaseExecutionStore:
    """Short transactions around external I/O; it never holds a DB transaction open."""

    def __init__(self, database: Database, *, environment: str) -> None:
        self._database = database
        self._environment = environment

    @staticmethod
    def _result(record: ProposalExecution) -> ExecutionResult:
        payload = record.result or {}
        return ExecutionResult(
            execution_id=str(record.id),
            proposal_id=str(record.proposal_id),
            state=ProposalState(record.state),
            correlation_id=record.external_correlation_id or "unknown",
            observed_assignee_id=payload.get("observed_assignee_id"),
            safe_error_code=payload.get("safe_error_code"),
        )

    async def prepare(
        self, proposal_id: str, correlation_id: str
    ) -> ExecutionClaim | ExecutionResult:
        async with self._database.transaction() as session:
            proposal_uuid = uuid.UUID(proposal_id)
            existing = await session.scalar(
                select(ProposalExecution).where(
                    ProposalExecution.environment == self._environment,
                    ProposalExecution.proposal_id == proposal_uuid,
                )
            )
            if existing is not None:
                return self._result(existing)
            proposal = await session.scalar(
                select(ReassignmentProposal)
                .where(
                    ReassignmentProposal.id == proposal_uuid,
                    ReassignmentProposal.environment == self._environment,
                )
                .with_for_update()
            )
            if proposal is None:
                raise ValueError("proposal not found")
            if ProposalState(proposal.state) is not ProposalState.EXECUTING:
                raise ValueError("proposal is not executing")
            execution = ProposalExecution(
                id=uuid.uuid4(),
                environment=self._environment,
                created_at=datetime.now(UTC),
                proposal_id=proposal.id,
                state=ProposalState.EXECUTING.value,
                external_correlation_id=correlation_id,
                result={"write_attempted": False},
                write_attempted=False,
            )
            session.add(execution)
            await AuditRepository(session).append(
                environment=self._environment,
                action_type="proposal.execution_started",
                actor_type="service",
                actor_id="workforce-risk-mcp",
                subject_ids=[proposal_id, proposal.task_key],
                correlation_id=correlation_id,
                new_state={"state": ProposalState.EXECUTING.value},
            )
            await session.flush()
            return ExecutionClaim(
                execution_id=str(execution.id),
                proposal_id=proposal_id,
                environment=self._environment,
                project_key=proposal.project_key,
                issue_key=proposal.task_key,
                expected_assignee_id=proposal.expected_assignee,
                proposed_assignee_id=proposal.proposed_assignee,
                idempotency_key=f"execute-{proposal_id}",
                correlation_id=correlation_id,
            )

    async def mark_write_attempted(self, claim: ExecutionClaim) -> None:
        async with self._database.transaction() as session:
            execution = await session.scalar(
                select(ProposalExecution)
                .where(
                    ProposalExecution.id == uuid.UUID(claim.execution_id),
                    ProposalExecution.environment == self._environment,
                )
                .with_for_update()
            )
            if execution is None or execution.state != ProposalState.EXECUTING.value:
                raise ValueError("execution is not active")
            execution.write_attempted = True
            execution.result = {"write_attempted": True}

    async def finalize(
        self, claim: ExecutionClaim, result: ExecutionResult
    ) -> ExecutionResult:
        async with self._database.transaction() as session:
            execution = await session.scalar(
                select(ProposalExecution)
                .where(
                    ProposalExecution.id == uuid.UUID(claim.execution_id),
                    ProposalExecution.environment == self._environment,
                )
                .with_for_update()
            )
            proposal = await session.scalar(
                select(ReassignmentProposal)
                .where(ReassignmentProposal.id == uuid.UUID(claim.proposal_id))
                .with_for_update()
            )
            if execution is None or proposal is None:
                raise ValueError("execution state not found")
            if ProposalState(execution.state) is not ProposalState.EXECUTING:
                return self._result(execution)
            validate_transition(ProposalState(proposal.state), result.state)
            safe_result: dict[str, Any] = {
                "observed_assignee_id": result.observed_assignee_id,
                "safe_error_code": result.safe_error_code,
                "write_attempted": execution.write_attempted,
            }
            execution.state = result.state.value
            execution.result = safe_result
            proposal.state = result.state.value
            proposal.version += 1
            await AuditRepository(session).append(
                environment=self._environment,
                action_type=f"proposal.{result.state.value}",
                actor_type="service",
                actor_id="workforce-risk-mcp",
                subject_ids=[claim.proposal_id, claim.issue_key],
                correlation_id=claim.correlation_id,
                prior_state={"state": ProposalState.EXECUTING.value},
                new_state={"state": result.state.value},
                safe_metadata=safe_result,
            )
            if result.state is ProposalState.UNCERTAIN:
                await OutboxRepository(session).append(
                    environment=self._environment,
                    consumer_key=f"uncertain-execution:{claim.execution_id}",
                    event_type="manager.uncertain_reassignment",
                    payload={
                        "proposal_id": claim.proposal_id,
                        "issue_key": claim.issue_key,
                        "correlation_id": claim.correlation_id,
                    },
                    created_at=datetime.now(UTC),
                )
            return result


class DatabaseReconciliationStore:
    def __init__(
        self,
        database: Database,
        *,
        environment: str,
        abandoned_after: timedelta = timedelta(minutes=2),
        lease_duration: timedelta = timedelta(minutes=1),
    ) -> None:
        self._database = database
        self._environment = environment
        self._abandoned_after = abandoned_after
        self._lease_duration = lease_duration

    async def lease_abandoned(
        self, *, worker_id: str, limit: int
    ) -> list[ReconciliationClaim]:
        now = datetime.now(UTC)
        cutoff = now - self._abandoned_after
        lease_expiry = now - self._lease_duration
        async with self._database.transaction() as session:
            rows = (
                await session.execute(
                    select(ProposalExecution, ReassignmentProposal)
                    .join(
                        ReassignmentProposal,
                        ReassignmentProposal.id == ProposalExecution.proposal_id,
                    )
                    .where(
                        ProposalExecution.environment == self._environment,
                        ProposalExecution.state.in_(
                            [
                                ProposalState.EXECUTING.value,
                                ProposalState.UNCERTAIN.value,
                            ]
                        ),
                        ProposalExecution.created_at <= cutoff,
                        (ProposalExecution.leased_at.is_(None))
                        | (ProposalExecution.leased_at < lease_expiry),
                    )
                    .order_by(ProposalExecution.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            claims: list[ReconciliationClaim] = []
            for execution, proposal in rows:
                execution.lease_owner = worker_id
                execution.leased_at = now
                claims.append(
                    ReconciliationClaim(
                        execution_id=str(execution.id),
                        proposal_id=str(proposal.id),
                        issue_key=proposal.task_key,
                        expected_assignee_id=proposal.expected_assignee,
                        proposed_assignee_id=proposal.proposed_assignee,
                        correlation_id=execution.external_correlation_id or "unknown",
                        write_attempted=execution.write_attempted,
                    )
                )
            return claims

    async def lease_proposal(
        self, proposal_id: str, *, worker_id: str
    ) -> ReconciliationClaim | None:
        now = datetime.now(UTC)
        async with self._database.transaction() as session:
            row = (
                await session.execute(
                    select(ProposalExecution, ReassignmentProposal)
                    .join(
                        ReassignmentProposal,
                        ReassignmentProposal.id == ProposalExecution.proposal_id,
                    )
                    .where(
                        ProposalExecution.environment == self._environment,
                        ProposalExecution.proposal_id == uuid.UUID(proposal_id),
                        ProposalExecution.state == ProposalState.UNCERTAIN.value,
                    )
                    .with_for_update()
                )
            ).one_or_none()
            if row is None:
                return None
            execution, proposal = row
            execution.lease_owner = worker_id
            execution.leased_at = now
            return ReconciliationClaim(
                execution_id=str(execution.id),
                proposal_id=str(proposal.id),
                issue_key=proposal.task_key,
                expected_assignee_id=proposal.expected_assignee,
                proposed_assignee_id=proposal.proposed_assignee,
                correlation_id=execution.external_correlation_id or "unknown",
                write_attempted=execution.write_attempted,
            )

    async def resolve(
        self,
        claim: ReconciliationClaim,
        *,
        state: ProposalState,
        evidence: dict[str, Any],
    ) -> None:
        async with self._database.transaction() as session:
            execution = await session.scalar(
                select(ProposalExecution)
                .where(
                    ProposalExecution.id == uuid.UUID(claim.execution_id),
                    ProposalExecution.environment == self._environment,
                )
                .with_for_update()
            )
            proposal = await session.scalar(
                select(ReassignmentProposal)
                .where(ReassignmentProposal.id == uuid.UUID(claim.proposal_id))
                .with_for_update()
            )
            if execution is None or proposal is None:
                raise ValueError("reconciliation state not found")
            current = ProposalState(execution.state)
            if current == state:
                return
            if current not in {ProposalState.EXECUTING, ProposalState.UNCERTAIN}:
                return
            validate_transition(ProposalState(proposal.state), state)
            execution.state = state.value
            execution.result = evidence
            execution.lease_owner = None
            execution.leased_at = None
            proposal.state = state.value
            proposal.version += 1
            await AuditRepository(session).append(
                environment=self._environment,
                action_type=f"proposal.reconciled_{state.value}",
                actor_type="service",
                actor_id="reconciliation-worker",
                subject_ids=[claim.proposal_id, claim.issue_key],
                correlation_id=claim.correlation_id,
                prior_state={"state": current.value},
                new_state={"state": state.value},
                safe_metadata=evidence,
            )
            if state is ProposalState.UNCERTAIN:
                await OutboxRepository(session).append(
                    environment=self._environment,
                    consumer_key=f"uncertain-execution:{claim.execution_id}",
                    event_type="manager.uncertain_reassignment",
                    payload={
                        "proposal_id": claim.proposal_id,
                        "issue_key": claim.issue_key,
                        "correlation_id": claim.correlation_id,
                    },
                    created_at=datetime.now(UTC),
                )
