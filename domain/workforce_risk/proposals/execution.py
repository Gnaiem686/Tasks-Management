from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from workforce_risk.proposals.state import ProposalState


class ExecutionClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    execution_id: str
    proposal_id: str
    environment: str
    project_key: str
    issue_key: str
    expected_assignee_id: str
    proposed_assignee_id: str
    idempotency_key: str
    correlation_id: str


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    execution_id: str
    proposal_id: str
    state: ProposalState
    correlation_id: str
    observed_assignee_id: str | None = None
    safe_error_code: str | None = None


class ExecutionStore(Protocol):
    async def prepare(
        self, proposal_id: str, correlation_id: str
    ) -> ExecutionClaim | ExecutionResult: ...

    async def mark_write_attempted(self, claim: ExecutionClaim) -> None: ...

    async def finalize(
        self, claim: ExecutionClaim, result: ExecutionResult
    ) -> ExecutionResult: ...


class AssigneeMutator(Protocol):
    async def execute(self, command: Any) -> Any: ...


class ReassignmentExecutionService:
    def __init__(self, *, store: ExecutionStore, mutator: AssigneeMutator) -> None:
        self._store = store
        self._mutator = mutator

    async def execute(
        self, proposal_id: str, *, correlation_id: str
    ) -> ExecutionResult:
        from jira_mcp_client.mutation import ReassignmentMutation

        prepared = await self._store.prepare(proposal_id, correlation_id)
        if isinstance(prepared, ExecutionResult):
            return prepared
        await self._store.mark_write_attempted(prepared)
        receipt = await self._mutator.execute(
            ReassignmentMutation(
                environment=prepared.environment,
                project_key=prepared.project_key,
                issue_key=prepared.issue_key,
                expected_assignee_id=prepared.expected_assignee_id,
                proposed_assignee_id=prepared.proposed_assignee_id,
                proposal_id=prepared.proposal_id,
                idempotency_key=prepared.idempotency_key,
                correlation_id=prepared.correlation_id,
            )
        )
        result = ExecutionResult(
            execution_id=prepared.execution_id,
            proposal_id=prepared.proposal_id,
            state=ProposalState(receipt.outcome.value),
            correlation_id=prepared.correlation_id,
            observed_assignee_id=receipt.observed_assignee_id,
            safe_error_code=receipt.safe_error_code,
        )
        return await self._store.finalize(prepared, result)
