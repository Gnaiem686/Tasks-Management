from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import NamedTuple

from workforce_risk.models import RiskLevel


class AlertRouting(NamedTuple):
    create_inbox_alert: bool
    send_email: bool
    prominent: bool


def route_risk(level: RiskLevel | None) -> AlertRouting:
    if level is RiskLevel.CRITICAL:
        return AlertRouting(True, True, True)
    if level is RiskLevel.HIGH:
        return AlertRouting(True, True, False)
    if level is RiskLevel.MEDIUM:
        return AlertRouting(True, False, False)
    return AlertRouting(False, False, False)


def alert_dedup_key(subject_id: str, risk_type: str, scoring_window: str) -> str:
    material = f"{subject_id}:{risk_type}:{scoring_window}"
    return hashlib.sha256(material.encode()).hexdigest()


def should_notify(
    *,
    previous_level: RiskLevel | None,
    current_level: RiskLevel,
    last_notified_at: datetime | None,
    now: datetime,
    cooldown: timedelta,
    important_new_evidence: bool = False,
) -> bool:
    if not route_risk(current_level).send_email:
        return False
    rank = {
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
        RiskLevel.CRITICAL: 4,
    }
    if previous_level is None or rank[current_level] > rank[previous_level]:
        return True
    if important_new_evidence:
        return True
    return last_notified_at is None or now - last_notified_at >= cooldown
