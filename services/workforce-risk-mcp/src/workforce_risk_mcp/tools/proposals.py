from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Protocol, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from workforce_contracts.auth import (
    ApplicationRole,
    InternalContextSigner,
    VerifiedInternalContext,
)
from workforce_persistence.proposal_repository import ProposalRepository, StoredProposal
from workforce_risk.proposals.models import (
    ProposalActor,
    ProposalDecisionCommand,
)


class ProposalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_key: str
    simulation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)
    expires_at: AwareDatetime
    requested_at: AwareDatetime


class ProposalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_key: str
    proposal_id: str
    expected_version: int = Field(ge=1)
    decision: Literal["approve", "reject"]
    idempotency_key: str = Field(min_length=8, max_length=128)
    decided_at: AwareDatetime


class ProposalGetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_key: str
    proposal_id: str


class FreshnessProvider(Protocol):
    async def fingerprint_for_proposal(self, proposal_id: str) -> str: ...


def authorize_proposal(
    *,
    transport_context: str | None,
    secret: bytes,
    environment: Literal["dev", "prod", "test"],
    project_key: str,
    now: datetime,
) -> VerifiedInternalContext:
    return InternalContextSigner(secret, lifetime=timedelta(seconds=60)).verify(
        transport_context,
        expected_environment=environment,
        required_project=project_key,
        required_roles={ApplicationRole.MANAGER, ApplicationRole.ADMINISTRATOR},
        now=now,
    )


def actor_from_context(context: VerifiedInternalContext) -> ProposalActor:
    if context.role.value not in {"manager", "administrator"}:
        raise PermissionError("proposal role is not authorized")
    return ProposalActor(
        actor_id=context.actor_id,
        role=cast(Literal["manager", "administrator"], context.role.value),
        environment=context.environment,
        project_scopes=context.project_scopes,
        correlation_id=context.correlation_id,
    )


async def create_proposal(
    request: ProposalCreateRequest,
    *,
    context: VerifiedInternalContext,
    repository: ProposalRepository,
) -> StoredProposal:
    return await repository.create_from_stored_simulation(
        simulation_id=request.simulation_id,
        idempotency_key=request.idempotency_key,
        expires_at=request.expires_at,
        requested_at=request.requested_at,
        actor=actor_from_context(context),
    )


async def decide_proposal(
    request: ProposalDecisionRequest,
    *,
    context: VerifiedInternalContext,
    repository: ProposalRepository,
    freshness: FreshnessProvider,
) -> StoredProposal:
    fingerprint = await freshness.fingerprint_for_proposal(request.proposal_id)
    return await repository.decide(
        ProposalDecisionCommand(
            proposal_id=request.proposal_id,
            expected_version=request.expected_version,
            decision=request.decision,
            idempotency_key=request.idempotency_key,
            current_evidence_fingerprint=fingerprint,
            decided_at=request.decided_at,
        ),
        actor_from_context(context),
    )


async def get_proposal(
    request: ProposalGetRequest,
    *,
    context: VerifiedInternalContext,
    repository: ProposalRepository,
) -> StoredProposal:
    result = await repository.get_authorized(
        request.proposal_id, actor=actor_from_context(context)
    )
    if result is None:
        raise ValueError("proposal not found")
    return result
