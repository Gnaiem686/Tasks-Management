from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from workforce_risk.proposals.state import ProposalState


class ReconciliationClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    execution_id: str
    proposal_id: str
    issue_key: str
    expected_assignee_id: str
    proposed_assignee_id: str
    correlation_id: str
    write_attempted: bool


class ReconciliationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    execution_id: str
    state: ProposalState
    observed_assignee_id: str | None = None
    safe_error_code: str | None = None


class ReconciliationStore(Protocol):
    async def lease_abandoned(
        self, *, worker_id: str, limit: int
    ) -> list[ReconciliationClaim]: ...

    async def lease_proposal(
        self, proposal_id: str, *, worker_id: str
    ) -> ReconciliationClaim | None: ...

    async def resolve(
        self,
        claim: ReconciliationClaim,
        *,
        state: ProposalState,
        evidence: dict[str, Any],
    ) -> None: ...


class AssigneeReader(Protocol):
    async def read_assignee(
        self, issue_key: str, *, correlation_id: str
    ) -> str | None: ...


class ReconciliationService:
    def __init__(self, *, store: ReconciliationStore, reader: AssigneeReader) -> None:
        self._store = store
        self._reader = reader

    async def run_once(
        self, *, worker_id: str, limit: int = 20
    ) -> list[ReconciliationResult]:
        claims = await self._store.lease_abandoned(worker_id=worker_id, limit=limit)
        results: list[ReconciliationResult] = []
        for claim in claims:
            results.append(await self._reconcile(claim))
        return results

    async def run_proposal(
        self, proposal_id: str, *, worker_id: str
    ) -> ReconciliationResult | None:
        claim = await self._store.lease_proposal(proposal_id, worker_id=worker_id)
        return None if claim is None else await self._reconcile(claim)

    async def _reconcile(self, claim: ReconciliationClaim) -> ReconciliationResult:
        observed: str | None = None
        error_code: str | None = None
        try:
            observed = await self._reader.read_assignee(
                claim.issue_key, correlation_id=claim.correlation_id
            )
        except Exception:
            error_code = "jira_reconciliation_read_failed"
        if observed == claim.proposed_assignee_id:
            state = ProposalState.EXECUTED_VERIFIED
        elif observed == claim.expected_assignee_id and not claim.write_attempted:
            state = ProposalState.EXECUTION_FAILED
        else:
            state = ProposalState.UNCERTAIN
            error_code = error_code or "jira_reconciliation_ambiguous"
        evidence: dict[str, Any] = {
            "observed_assignee_id": observed,
            "safe_error_code": error_code,
            "write_attempted": claim.write_attempted,
        }
        await self._store.resolve(claim, state=state, evidence=evidence)
        return ReconciliationResult(
            execution_id=claim.execution_id,
            state=state,
            observed_assignee_id=observed,
            safe_error_code=error_code,
        )
