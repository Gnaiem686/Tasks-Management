from enum import StrEnum


class ProposalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    EXECUTED_VERIFIED = "executed_verified"
    EXECUTION_FAILED = "execution_failed"
    UNCERTAIN = "uncertain"
    REJECTED = "rejected"
    EXPIRED = "expired"
    STALE = "stale"


TERMINAL_STATES = {
    ProposalState.EXECUTED_VERIFIED,
    ProposalState.EXECUTION_FAILED,
    ProposalState.REJECTED,
    ProposalState.EXPIRED,
    ProposalState.STALE,
}

ALLOWED_TRANSITIONS = {
    ProposalState.PENDING: {
        ProposalState.EXECUTING,
        ProposalState.REJECTED,
        ProposalState.EXPIRED,
        ProposalState.STALE,
    },
    ProposalState.EXECUTING: {
        ProposalState.EXECUTED_VERIFIED,
        ProposalState.EXECUTION_FAILED,
        ProposalState.UNCERTAIN,
        ProposalState.STALE,
    },
    ProposalState.UNCERTAIN: {
        ProposalState.EXECUTED_VERIFIED,
        ProposalState.EXECUTION_FAILED,
    },
}


def validate_transition(current: ProposalState, target: ProposalState) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"illegal proposal transition: {current} -> {target}")
