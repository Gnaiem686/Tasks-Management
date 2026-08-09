from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from workforce_risk.proposals.models import (
    ProposalActor,
    ProposalCreateCommand,
    ProposalDecisionCommand,
    is_expired,
)
from workforce_risk.proposals.state import ProposalState, validate_transition

from workforce_persistence.models import ApprovalDecision, ReassignmentProposal
from workforce_persistence.repositories import AuditRepository
from workforce_persistence.simulation_repository import SimulationRepository


@dataclass(frozen=True)
class StoredProposal:
    proposal_id: str
    state: ProposalState
    version: int
    task_id: str
    current_assignee_id: str
    proposed_assignee_id: str
    evidence_fingerprint: str
    expires_at: datetime


class ProposalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _view(record: ReassignmentProposal) -> StoredProposal:
        return StoredProposal(
            proposal_id=str(record.id),
            state=ProposalState(record.state),
            version=record.version,
            task_id=record.task_key,
            current_assignee_id=record.expected_assignee,
            proposed_assignee_id=record.proposed_assignee,
            evidence_fingerprint=record.evidence_fingerprint,
            expires_at=record.expires_at,
        )

    async def create(
        self, command: ProposalCreateCommand, actor: ProposalActor
    ) -> StoredProposal:
        simulation = command.simulation
        if actor.environment != simulation.environment:
            raise PermissionError("proposal environment mismatch")
        if simulation.project_key not in actor.project_scopes:
            raise PermissionError("proposal project scope mismatch")
        existing = await self._session.scalar(
            select(ReassignmentProposal).where(
                ReassignmentProposal.environment == actor.environment,
                ReassignmentProposal.idempotency_key == command.idempotency_key,
            )
        )
        if existing is not None:
            return self._view(existing)
        record = ReassignmentProposal(
            id=uuid.uuid4(),
            environment=actor.environment,
            created_at=command.requested_at,
            simulation_id=simulation.simulation_id,
            project_key=simulation.project_key,
            task_key=simulation.task_id,
            expected_assignee=simulation.current_assignee_id,
            proposed_assignee=simulation.proposed_assignee_id,
            state=ProposalState.PENDING.value,
            idempotency_key=command.idempotency_key,
            evidence_fingerprint=simulation.evidence_fingerprint,
            confidence=simulation.confidence.value,
            scoring_versions=list(simulation.scoring_model_versions),
            simulation_payload=simulation.safe_payload,
            requested_by=actor.actor_id,
            expires_at=command.expires_at,
            version=1,
        )
        self._session.add(record)
        await AuditRepository(self._session).append(
            environment=actor.environment,
            action_type="proposal.created",
            actor_type=actor.role,
            actor_id=actor.actor_id,
            subject_ids=[str(record.id), simulation.task_id],
            correlation_id=actor.correlation_id,
            new_state={"state": ProposalState.PENDING.value, "version": 1},
            safe_metadata={
                "simulation_id": simulation.simulation_id,
                "scoring_versions": list(simulation.scoring_model_versions),
            },
        )
        await self._session.flush()
        return self._view(record)

    async def create_from_stored_simulation(
        self,
        *,
        simulation_id: str,
        idempotency_key: str,
        expires_at: datetime,
        requested_at: datetime,
        actor: ProposalActor,
    ) -> StoredProposal:
        simulation = await SimulationRepository(self._session).get(
            environment=actor.environment, simulation_id=simulation_id
        )
        if simulation is None:
            raise ValueError("stored simulation not found")
        return await self.create(
            ProposalCreateCommand(
                simulation=simulation,
                idempotency_key=idempotency_key,
                expires_at=expires_at,
                requested_at=requested_at,
            ),
            actor,
        )

    async def decide(
        self, command: ProposalDecisionCommand, actor: ProposalActor
    ) -> StoredProposal:
        duplicate = await self._session.scalar(
            select(ApprovalDecision).where(
                ApprovalDecision.environment == actor.environment,
                ApprovalDecision.idempotency_key == command.idempotency_key,
            )
        )
        if duplicate is not None:
            record = await self._session.get(
                ReassignmentProposal, duplicate.proposal_id
            )
            assert record is not None
            return self._view(record)
        record = await self._session.scalar(
            select(ReassignmentProposal)
            .where(
                ReassignmentProposal.id == uuid.UUID(command.proposal_id),
                ReassignmentProposal.environment == actor.environment,
            )
            .with_for_update()
        )
        if record is None or record.project_key not in actor.project_scopes:
            raise PermissionError("proposal not found in authorized scope")
        if record.version != command.expected_version:
            raise ValueError("proposal version conflict")
        current = ProposalState(record.state)
        if current is not ProposalState.PENDING:
            raise ValueError("proposal is not pending")
        if is_expired(record.expires_at, command.decided_at):
            target = ProposalState.EXPIRED
        elif record.evidence_fingerprint != command.current_evidence_fingerprint:
            target = ProposalState.STALE
        elif command.decision == "reject":
            target = ProposalState.REJECTED
        else:
            target = ProposalState.EXECUTING
        validate_transition(current, target)
        result = await self._session.execute(
            update(ReassignmentProposal)
            .where(
                ReassignmentProposal.id == record.id,
                ReassignmentProposal.version == command.expected_version,
                ReassignmentProposal.state == ProposalState.PENDING.value,
            )
            .values(state=target.value, version=ReassignmentProposal.version + 1)
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            raise ValueError("proposal concurrent transition conflict")
        self._session.add(
            ApprovalDecision(
                id=uuid.uuid4(),
                environment=actor.environment,
                created_at=command.decided_at,
                proposal_id=record.id,
                actor_id=actor.actor_id,
                decision=command.decision,
                correlation_id=actor.correlation_id,
                idempotency_key=command.idempotency_key,
            )
        )
        await AuditRepository(self._session).append(
            environment=actor.environment,
            action_type=f"proposal.{target.value}",
            actor_type=actor.role,
            actor_id=actor.actor_id,
            subject_ids=[str(record.id), record.task_key],
            correlation_id=actor.correlation_id,
            prior_state={"state": current.value, "version": record.version},
            new_state={"state": target.value, "version": record.version + 1},
        )
        record.state = target.value
        record.version += 1
        return self._view(record)
