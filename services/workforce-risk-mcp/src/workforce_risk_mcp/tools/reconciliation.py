from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from workforce_risk.proposals.reconciliation import (
    ReconciliationResult,
    ReconciliationService,
)


class ReconcileExecutionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    worker_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=20, ge=1, le=100)


class ReconcileProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_key: str
    proposal_id: str


async def reconcile_executions(
    request: ReconcileExecutionsRequest, *, service: ReconciliationService
) -> list[ReconciliationResult]:
    return await service.run_once(worker_id=request.worker_id, limit=request.limit)


async def reconcile_proposal(
    request: ReconcileProposalRequest,
    *,
    service: ReconciliationService,
    worker_id: str,
) -> ReconciliationResult | None:
    return await service.run_proposal(request.proposal_id, worker_id=worker_id)
