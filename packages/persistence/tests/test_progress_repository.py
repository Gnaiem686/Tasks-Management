from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from workforce_persistence.progress_repository import (
    TaskProgressObservation,
    derive_progress_events,
)


def observation(**changes: object) -> TaskProgressObservation:
    values: dict[str, object] = {
        "project_key": "WFD",
        "issue_key": "WFD-5",
        "assignee_id": "jira-account-1",
        "captured_at": datetime(2026, 8, 24, 9, tzinfo=UTC),
        "jira_updated_at": datetime(2026, 8, 24, 8, 55, tzinfo=UTC),
        "status": "Testing",
        "original_estimate_hours": 8.0,
        "remaining_estimate_hours": 6.0,
        "time_spent_hours": 2.0,
        "due_date": date(2026, 8, 25),
        "priority": "High",
        "blocked": False,
        "blocker_issue_keys": (),
    }
    values.update(changes)
    return TaskProgressObservation.model_validate(values)


@pytest.mark.unit
def test_observation_fingerprint_ignores_capture_time_but_tracks_jira_state() -> None:
    first = observation()
    later_scan = observation(captured_at=datetime(2026, 8, 24, 9, 30, tzinfo=UTC))
    changed = observation(remaining_estimate_hours=4.0)

    assert first.fingerprint() == later_scan.fingerprint()
    assert first.fingerprint() != changed.fingerprint()


@pytest.mark.unit
def test_derives_remaining_worklog_status_and_blocker_events() -> None:
    previous = observation()
    current = observation(
        captured_at=datetime(2026, 8, 24, 12, tzinfo=UTC),
        jira_updated_at=datetime(2026, 8, 24, 11, 55, tzinfo=UTC),
        remaining_estimate_hours=4.0,
        time_spent_hours=4.0,
        status="In Progress",
        blocked=True,
        blocker_issue_keys=("WFD-3",),
    )

    events = derive_progress_events(previous, current)

    assert {event.event_type for event in events} == {
        "remaining_estimate_changed",
        "work_logged",
        "status_changed",
        "blocker_added",
    }
    remaining = next(
        event for event in events if event.event_type == "remaining_estimate_changed"
    )
    assert remaining.old_value == 6.0
    assert remaining.new_value == 4.0


@pytest.mark.unit
def test_missing_estimate_becoming_known_is_a_planning_data_event() -> None:
    events = derive_progress_events(
        observation(remaining_estimate_hours=None),
        observation(remaining_estimate_hours=5.0),
    )

    assert [event.event_type for event in events] == ["remaining_estimate_changed"]
    assert events[0].old_value is None
    assert events[0].new_value == 5.0


@pytest.mark.unit
def test_due_date_event_values_are_json_safe() -> None:
    events = derive_progress_events(
        observation(due_date=date(2026, 8, 22)),
        observation(due_date=date(2026, 8, 23)),
    )

    event = next(item for item in events if item.event_type == "due_date_changed")
    assert event.old_value == "2026-08-22"
    assert event.new_value == "2026-08-23"
