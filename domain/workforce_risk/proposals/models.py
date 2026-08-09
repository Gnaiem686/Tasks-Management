from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from workforce_risk.models import ConfidenceLevel


class StoredSimulation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    simulation_id: str
    environment: Literal["dev", "prod", "test"]
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,19}$")
    task_id: str
    current_assignee_id: str
    proposed_assignee_id: str
    candidate_ids: tuple[str, ...]
    confidence: ConfidenceLevel
    evidence_fingerprint: str = Field(min_length=64, max_length=64)
    scoring_model_versions: tuple[str, ...]
    simulated_at: AwareDatetime
    safe_payload: dict[str, object]

    @model_validator(mode="after")
    def validate_candidate(self) -> StoredSimulation:
        if self.current_assignee_id == self.proposed_assignee_id:
            raise ValueError("proposal must change the assignee")
        if self.proposed_assignee_id not in self.candidate_ids:
            raise ValueError("proposed assignee is not in deterministic candidates")
        if self.confidence not in {ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH}:
            raise ValueError("proposal confidence is below minimum")
        return self


class ProposalCreateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    simulation: StoredSimulation
    idempotency_key: str = Field(min_length=8, max_length=128)
    expires_at: AwareDatetime
    requested_at: AwareDatetime

    @model_validator(mode="after")
    def validate_expiry(self) -> ProposalCreateCommand:
        if self.expires_at <= self.requested_at:
            raise ValueError("proposal expiry must be in the future")
        return self


class ProposalDecisionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    proposal_id: str
    expected_version: int = Field(ge=1)
    decision: Literal["approve", "reject"]
    idempotency_key: str = Field(min_length=8, max_length=128)
    current_evidence_fingerprint: str = Field(min_length=64, max_length=64)
    decided_at: AwareDatetime


class ProposalActor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor_id: str
    role: Literal["manager", "administrator"]
    environment: Literal["dev", "prod", "test"]
    project_scopes: tuple[str, ...]
    correlation_id: str


def is_expired(expires_at: datetime, now: datetime) -> bool:
    return expires_at <= now
