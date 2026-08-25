from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from workforce_risk.evidence.snapshot import VersionedEvidenceSnapshot


class SnapshotStore(Protocol):
    async def persist(
        self,
        snapshot: VersionedEvidenceSnapshot,
        *,
        subject_type: str,
        service_environment: str | None = None,
    ) -> UUID: ...


class PersistEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    environment: Literal["dev", "prod", "test"]
    correlation_id: str = Field(min_length=1, max_length=128)
    subject_type: Literal["employee", "task", "project"]
    snapshot: VersionedEvidenceSnapshot


class PersistEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    environment: Literal["dev", "prod", "test"]
    correlation_id: str
    status: Literal["success"] = "success"
    snapshot_id: str
    fingerprint: str


async def persist_evidence(
    request: PersistEvidenceRequest,
    *,
    repository: SnapshotStore,
    service_environment: str,
) -> PersistEvidenceResponse:
    if request.environment != service_environment:
        raise ValueError("request environment mismatch")
    if request.snapshot.evidence.environment != request.environment:
        raise ValueError("snapshot environment mismatch")
    snapshot_id = await repository.persist(
        request.snapshot,
        subject_type=request.subject_type,
        service_environment=service_environment,
    )
    return PersistEvidenceResponse(
        environment=request.environment,
        correlation_id=request.correlation_id,
        snapshot_id=str(snapshot_id),
        fingerprint=request.snapshot.fingerprint,
    )
