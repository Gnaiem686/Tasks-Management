from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from workforce_risk.evidence.fingerprint import (
    EvidenceFingerprintInput,
    material_changes,
)
from workforce_risk.evidence.freshness import evidence_is_stale

NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


def evidence(**changes: object) -> EvidenceFingerprintInput:
    values: dict[str, object] = {
        "schema_version": "1.0",
        "environment": "dev",
        "subject_id": "WRD-10",
        "task_state": "In Progress",
        "current_assignee": "synthetic-account-a",
        "employee_workloads": {"EMP-001": 32.0, "EMP-002": 18.0},
        "due_date": date(2026, 8, 15),
        "dependencies": ("WRD-8", "WRD-9"),
        "scoring_versions": (
            "employee-overload-v1",
            "task-fit-v1",
            "project-delivery-v1",
        ),
        "evidence_timestamp": NOW,
        "irrelevant_metadata": {"ui_color": "blue"},
    }
    values.update(changes)
    return EvidenceFingerprintInput.model_validate(values)


@pytest.mark.unit
def test_fingerprint_is_canonical_and_ignores_irrelevant_metadata() -> None:
    first = evidence()
    reordered = evidence(
        employee_workloads={"EMP-002": 18.0, "EMP-001": 32.0},
        dependencies=("WRD-9", "WRD-8"),
        irrelevant_metadata={"ui_color": "red"},
    )
    assert first.fingerprint() == reordered.fingerprint()


@pytest.mark.unit
@pytest.mark.parametrize(
    "change",
    [
        {"task_state": "Blocked"},
        {"current_assignee": "synthetic-account-b"},
        {"employee_workloads": {"EMP-001": 40.0, "EMP-002": 18.0}},
        {"due_date": date(2026, 8, 12)},
        {"dependencies": ("WRD-8",)},
        {"scoring_versions": ("task-fit-v2",)},
    ],
)
def test_each_material_change_invalidates_fingerprint(
    change: dict[str, object],
) -> None:
    assert evidence().fingerprint() != evidence(**change).fingerprint()
    assert material_changes(evidence(), evidence(**change))


@pytest.mark.unit
def test_environment_mismatch_is_rejected_and_staleness_is_explicit() -> None:
    with pytest.raises(ValueError, match="environment"):
        material_changes(evidence(), evidence(environment="prod"))
    assert evidence_is_stale(
        evidence_timestamp=NOW - timedelta(hours=25),
        checked_at=NOW,
        max_age=timedelta(hours=24),
    )
    assert not evidence_is_stale(
        evidence_timestamp=NOW - timedelta(hours=24),
        checked_at=NOW,
        max_age=timedelta(hours=24),
    )
