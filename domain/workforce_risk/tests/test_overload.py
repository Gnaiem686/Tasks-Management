from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from workforce_risk.models import ConfidenceLevel, EmployeeOverloadInput, RiskLevel
from workforce_risk.scoring.config import ScoringConfiguration, load_scoring_config
from workforce_risk.scoring.overload import (
    risk_level_for_score,
    score_employee_overload,
)

ROOT = Path(__file__).parents[3]
SCORING_CONFIG = ROOT / "config" / "scoring" / "v1.yaml"
SCENARIOS = ROOT / "tests" / "fixtures" / "scenarios"
SCORED_AT = datetime(2026, 8, 6, 12, tzinfo=UTC)


def scenario(name: str) -> EmployeeOverloadInput:
    return EmployeeOverloadInput.model_validate_json(
        (SCENARIOS / f"{name}.json").read_text()
    )


@pytest.mark.unit
def test_balanced_and_overloaded_scenarios_are_exact_and_repeatable() -> None:
    config = load_scoring_config(SCORING_CONFIG)

    balanced = score_employee_overload(scenario("balanced_team"), config, SCORED_AT)
    overloaded = score_employee_overload(
        scenario("overloaded_employee"), config, SCORED_AT
    )

    assert (balanced.score, balanced.level, balanced.confidence) == (
        13,
        RiskLevel.LOW,
        ConfidenceLevel.HIGH,
    )
    assert (overloaded.score, overloaded.level, overloaded.confidence) == (
        88,
        RiskLevel.CRITICAL,
        ConfidenceLevel.HIGH,
    )
    assert overloaded == score_employee_overload(
        scenario("overloaded_employee"), config, SCORED_AT
    )
    assert overloaded.scoring_model_version == "employee-overload-v1"
    assert overloaded.scored_at == SCORED_AT
    assert sum(f.weight for f in overloaded.factors) == pytest.approx(1.0)
    assert all(f.direction == "increases_risk" for f in overloaded.factors)
    assert "profile:EMP-002:capacity" in overloaded.evidence_references


@pytest.mark.unit
@pytest.mark.parametrize(
    ("score", "level"),
    [
        (0, RiskLevel.LOW),
        (29, RiskLevel.LOW),
        (30, RiskLevel.MEDIUM),
        (54, RiskLevel.MEDIUM),
        (55, RiskLevel.HIGH),
        (74, RiskLevel.HIGH),
        (75, RiskLevel.CRITICAL),
        (100, RiskLevel.CRITICAL),
    ],
)
def test_risk_level_boundaries(score: int, level: RiskLevel) -> None:
    assert risk_level_for_score(score) is level


@pytest.mark.unit
def test_extreme_utilization_is_capped_and_score_is_clamped() -> None:
    config = load_scoring_config(SCORING_CONFIG)
    raw = scenario("overloaded_employee").model_dump()
    raw["remaining_estimated_hours"] = 100_000

    result = score_employee_overload(
        EmployeeOverloadInput.model_validate(raw), config, SCORED_AT
    )

    utilization = next(f for f in result.factors if f.name == "utilization")
    assert utilization.normalized_value == 1.0
    assert result.score is not None and 0 <= result.score <= 100


@pytest.mark.unit
@pytest.mark.parametrize(
    "missing", ["available_capacity_hours", "remaining_estimated_hours"]
)
def test_missing_mandatory_evidence_returns_insufficient_data(missing: str) -> None:
    config = load_scoring_config(SCORING_CONFIG)
    raw = scenario("balanced_team").model_dump()
    raw[missing] = None

    result = score_employee_overload(
        EmployeeOverloadInput.model_validate(raw), config, SCORED_AT
    )

    assert result.score is None
    assert result.level is None
    assert result.confidence is ConfidenceLevel.INSUFFICIENT_DATA
    assert missing in result.missing_evidence


@pytest.mark.unit
def test_stale_evidence_is_excluded_instead_of_treated_as_zero_risk() -> None:
    config = load_scoring_config(SCORING_CONFIG)
    raw = scenario("balanced_team").model_dump()
    raw["evidence_timestamp"] = SCORED_AT - timedelta(
        hours=config.employee_overload.max_evidence_age_hours + 1
    )

    result = score_employee_overload(
        EmployeeOverloadInput.model_validate(raw), config, SCORED_AT
    )

    assert result.score is None
    assert result.confidence is ConfidenceLevel.INSUFFICIENT_DATA
    assert "stale_evidence" in result.excluded_evidence


@pytest.mark.unit
def test_values_without_evidence_references_do_not_count_toward_confidence() -> None:
    config = load_scoring_config(SCORING_CONFIG)
    raw = scenario("balanced_team").model_dump()
    raw["evidence_references"] = {}

    result = score_employee_overload(
        EmployeeOverloadInput.model_validate(raw), config, SCORED_AT
    )

    assert result.score is None
    assert result.confidence is ConfidenceLevel.INSUFFICIENT_DATA
    assert "utilization" in result.missing_evidence


@pytest.mark.unit
def test_configuration_rejects_invalid_weight_sum_and_missing_direction() -> None:
    config = load_scoring_config(SCORING_CONFIG).model_dump()
    broken_sum = copy.deepcopy(config)
    broken_sum["employee_overload"]["factors"]["utilization"]["weight"] = 0.29
    missing_direction = copy.deepcopy(config)
    del missing_direction["employee_overload"]["factors"]["utilization"]["direction"]

    with pytest.raises(ValueError, match="sum to 1.0"):
        ScoringConfiguration.model_validate(broken_sum)
    with pytest.raises(ValueError):
        ScoringConfiguration.model_validate(missing_direction)


@pytest.mark.unit
def test_fixture_is_plain_json_without_generated_values() -> None:
    raw = json.loads((SCENARIOS / "balanced_team.json").read_text())
    assert raw["employee_id"] == "EMP-001"
