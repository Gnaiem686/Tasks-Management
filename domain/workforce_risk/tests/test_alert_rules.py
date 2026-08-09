from datetime import UTC, datetime, timedelta

import pytest
from workforce_risk.alerts.rules import alert_dedup_key, route_risk, should_notify
from workforce_risk.alerts.state import AlertState, validate_transition
from workforce_risk.models import RiskLevel

NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


@pytest.mark.unit
def test_risk_routing_separates_report_inbox_and_email() -> None:
    assert route_risk(RiskLevel.LOW) == (False, False, False)
    assert route_risk(RiskLevel.MEDIUM) == (True, False, False)
    assert route_risk(RiskLevel.HIGH) == (True, True, False)
    assert route_risk(RiskLevel.CRITICAL) == (True, True, True)


@pytest.mark.unit
def test_dedup_key_is_reproducible_and_window_specific() -> None:
    first = alert_dedup_key("EMP-002", "overload", "2026-08-09")
    assert first == alert_dedup_key("EMP-002", "overload", "2026-08-09")
    assert first != alert_dedup_key("EMP-002", "overload", "2026-08-10")


@pytest.mark.unit
def test_cooldown_suppresses_repeat_but_not_escalation_or_new_evidence() -> None:
    assert not should_notify(
        previous_level=RiskLevel.HIGH,
        current_level=RiskLevel.HIGH,
        last_notified_at=NOW - timedelta(minutes=5),
        now=NOW,
        cooldown=timedelta(hours=4),
    )
    assert should_notify(
        previous_level=RiskLevel.HIGH,
        current_level=RiskLevel.CRITICAL,
        last_notified_at=NOW - timedelta(minutes=5),
        now=NOW,
        cooldown=timedelta(hours=4),
    )
    assert should_notify(
        previous_level=RiskLevel.HIGH,
        current_level=RiskLevel.HIGH,
        last_notified_at=NOW - timedelta(minutes=5),
        now=NOW,
        cooldown=timedelta(hours=4),
        important_new_evidence=True,
    )


@pytest.mark.unit
def test_state_rules_require_reason_and_preserve_recurrence_path() -> None:
    with pytest.raises(ValueError, match="reason"):
        validate_transition(AlertState.NEW, AlertState.DISMISSED)
    validate_transition(
        AlertState.NEW, AlertState.DISMISSED, dismissal_reason="Known planned work"
    )
    validate_transition(AlertState.DISMISSED, AlertState.NEW)
    with pytest.raises(ValueError, match="illegal"):
        validate_transition(AlertState.RESOLVED, AlertState.ACKNOWLEDGED)
