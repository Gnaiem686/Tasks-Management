import pytest
from workforce_risk.audit.chain import event_hash, verify_hash_chain
from workforce_risk.proposals.state import (
    TERMINAL_STATES,
    ProposalState,
    validate_transition,
)


def event(sequence: int, previous: str | None, action: str) -> dict[str, object]:
    value: dict[str, object] = {
        "sequence_number": sequence,
        "previous_hash": previous,
        "action_type": action,
        "actor_id": "manager-safe",
        "safe_metadata": {},
    }
    value["event_hash"] = event_hash(value)
    return value


@pytest.mark.security
def test_hash_chain_detects_changed_missing_and_reordered_events() -> None:
    first = event(1, None, "proposal.created")
    second = event(2, str(first["event_hash"]), "proposal.executing")
    assert verify_hash_chain((first, second))
    assert not verify_hash_chain((second, first))
    tampered = dict(second, actor_id="forged")
    assert not verify_hash_chain((first, tampered))


@pytest.mark.security
def test_terminal_and_illegal_proposal_transitions_are_rejected() -> None:
    validate_transition(ProposalState.PENDING, ProposalState.EXECUTING)
    assert ProposalState.STALE in TERMINAL_STATES
    for terminal in TERMINAL_STATES:
        with pytest.raises(ValueError, match="illegal"):
            validate_transition(terminal, ProposalState.PENDING)
    with pytest.raises(ValueError, match="illegal"):
        validate_transition(ProposalState.PENDING, ProposalState.EXECUTED_VERIFIED)
