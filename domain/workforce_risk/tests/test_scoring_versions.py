from pathlib import Path

import pytest
from pydantic import ValidationError
from workforce_risk.scoring.config import ScoringConfiguration, load_scoring_config

ROOT = Path(__file__).parents[3]


@pytest.mark.unit
def test_all_score_family_weights_sum_to_one_and_versions_are_explicit() -> None:
    config = load_scoring_config(ROOT / "config/scoring/v1.yaml")

    assert config.employee_overload.version == "employee-overload-v1"
    assert config.task_fit.version == "task-fit-v1"
    assert config.project_delivery.version == "project-delivery-v1"
    for family in (config.employee_overload, config.task_fit, config.project_delivery):
        assert sum(item.weight for item in family.factors.values()) == pytest.approx(1)


@pytest.mark.unit
def test_scoring_configuration_is_immutable_and_rejects_bad_family_weights() -> None:
    config = load_scoring_config(ROOT / "config/scoring/v1.yaml")
    with pytest.raises(ValidationError):
        config.task_fit.version = "changed"
    raw = config.model_dump()
    raw["task_fit"]["factors"]["required_skill_gap"]["weight"] = 0.29
    with pytest.raises(ValidationError, match="sum to 1.0"):
        ScoringConfiguration.model_validate(raw)
