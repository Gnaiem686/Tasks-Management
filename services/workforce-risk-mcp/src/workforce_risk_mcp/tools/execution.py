from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from workforce_risk.proposals.execution import (
    ExecutionResult,
    ReassignmentExecutionService,
)


class ExecuteProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_key: str
    proposal_id: str


async def execute_reassignment(
    request: ExecuteProposalRequest,
    *,
    service: ReassignmentExecutionService,
    correlation_id: str,
) -> ExecutionResult:
    return await service.execute(request.proposal_id, correlation_id=correlation_id)
