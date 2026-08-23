from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from workforce_risk.profiles import (
    CapacityOverride,
    DocumentedSkill,
    ProjectAllocation,
    Seniority,
    SkillProficiency,
    WorkforceProfile,
    validate_profile_set,
)

NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)


def profile(employee_number: int, **changes: object) -> WorkforceProfile:
    data: dict[str, object] = {
        "employee_id": f"EMP-{employee_number:03d}",
        "environment": "dev",
        "role": "Backend Engineer",
        "seniority": "mid",
        "documented_skills": [
            {"name": "Python", "proficiency": 4},
            {"name": "Kubernetes", "proficiency": 3},
        ],
        "weekly_capacity_hours": 40,
        "project_allocations": [{"project_key": "WRD", "fraction": 0.75}],
        "mentoring_available": False,
        "capacity_overrides": [],
        "version": 1,
    }
    data.update(changes)
    return WorkforceProfile.model_validate(data)


@pytest.mark.unit
def test_profile_validates_work_planning_fields_and_effective_capacity() -> None:
    override = CapacityOverride(
        starts_at=NOW,
        ends_at=NOW + timedelta(days=2),
        capacity_hours=16,
        reason="approved temporary availability",
    )
    value = profile(1, capacity_overrides=[override])

    assert value.seniority is Seniority.MID
    assert value.documented_skills[0] == DocumentedSkill(
        name="Python", proficiency=SkillProficiency.ADVANCED
    )
    assert value.project_allocations[0] == ProjectAllocation(
        project_key="WRD", fraction=0.75
    )
    assert value.effective_capacity(NOW + timedelta(hours=1)) == 16
    assert value.effective_capacity(NOW - timedelta(hours=1)) == 40


@pytest.mark.unit
@pytest.mark.parametrize("proficiency", [0, 6])
def test_invalid_proficiency_is_rejected(proficiency: int) -> None:
    with pytest.raises(ValidationError):
        profile(1, documented_skills=[{"name": "Python", "proficiency": proficiency}])


@pytest.mark.unit
def test_overlapping_capacity_overrides_and_excess_allocation_are_rejected() -> None:
    first = {
        "starts_at": NOW,
        "ends_at": NOW + timedelta(days=2),
        "capacity_hours": 20,
        "reason": "first",
    }
    overlapping = {
        "starts_at": NOW + timedelta(days=1),
        "ends_at": NOW + timedelta(days=3),
        "capacity_hours": 30,
        "reason": "second",
    }
    with pytest.raises(ValidationError, match="overlap"):
        profile(1, capacity_overrides=[first, overlapping])
    with pytest.raises(ValidationError, match="allocations"):
        profile(
            1,
            project_allocations=[
                {"project_key": "WRD", "fraction": 0.7},
                {"project_key": "OTHER", "fraction": 0.5},
            ],
        )


@pytest.mark.unit
def test_dynamic_profile_set_accepts_real_project_team_without_fixed_count() -> None:
    profiles = [
        profile(number, employee_id=f"WFD-EMP-{number:03d}") for number in range(1, 5)
    ]
    profiles[0] = profile(
        1,
        employee_id="WFD-EMP-001",
        jira_account_id="wfd-account-one",
    )
    profiles[1] = profile(
        2,
        employee_id="WFD-EMP-002",
        jira_account_id="wfd-account-two",
    )

    validate_profile_set(
        profiles,
        environment="dev",
        jira_mapping_employee_ids={"WFD-EMP-001", "WFD-EMP-002"},
    )

    with pytest.raises(ValueError, match="unique"):
        validate_profile_set(
            [*profiles[:-1], profiles[0]],
            environment="dev",
            jira_mapping_employee_ids={"WFD-EMP-001", "WFD-EMP-002"},
        )
    invalid_mapping = [
        *profiles[:2],
        profile(
            3,
            employee_id="WFD-EMP-003",
            jira_account_id="not-allowed",
        ),
        *profiles[3:],
    ]
    with pytest.raises(ValueError, match="Jira account mapping"):
        validate_profile_set(
            invalid_mapping,
            environment="dev",
            jira_mapping_employee_ids={"WFD-EMP-001", "WFD-EMP-002"},
        )


@pytest.mark.unit
def test_cross_environment_and_duplicate_jira_mapping_are_rejected() -> None:
    profiles = [profile(number) for number in range(1, 8)]
    profiles[0] = profile(1, jira_account_id="same-account")
    profiles[1] = profile(2, jira_account_id="same-account")
    with pytest.raises(ValueError, match="unique"):
        validate_profile_set(
            profiles,
            environment="dev",
            jira_mapping_employee_ids={"EMP-001", "EMP-002"},
        )
    profiles = [profile(number) for number in range(1, 8)]
    profiles[6] = profile(7, environment="prod")
    with pytest.raises(ValueError, match="environment"):
        validate_profile_set(
            profiles,
            environment="dev",
            jira_mapping_employee_ids={"EMP-001", "EMP-002"},
        )
