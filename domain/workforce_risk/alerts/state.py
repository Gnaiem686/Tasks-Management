from __future__ import annotations

from enum import StrEnum


class AlertState(StrEnum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


ALLOWED_TRANSITIONS = {
    AlertState.NEW: {
        AlertState.ACKNOWLEDGED,
        AlertState.INVESTIGATING,
        AlertState.RESOLVED,
        AlertState.DISMISSED,
    },
    AlertState.ACKNOWLEDGED: {
        AlertState.INVESTIGATING,
        AlertState.RESOLVED,
        AlertState.DISMISSED,
    },
    AlertState.INVESTIGATING: {AlertState.RESOLVED, AlertState.DISMISSED},
    AlertState.RESOLVED: {AlertState.NEW},
    AlertState.DISMISSED: {AlertState.NEW},
}


def validate_transition(
    current: AlertState, target: AlertState, *, dismissal_reason: str | None = None
) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"illegal alert transition: {current} -> {target}")
    if target is AlertState.DISMISSED and not dismissal_reason:
        raise ValueError("dismissal requires a reason")
