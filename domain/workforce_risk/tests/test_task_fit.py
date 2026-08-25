from datetime import UTC, datetime
from pathlib import Path

import pytest
from workforce_risk.models import ConfidenceLevel, RiskLevel, TaskFitInput
from workforce_risk.scoring.config import load_scoring_config
from workforce_risk.scoring.task_fit import score_task_fit

ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)


@pytest.mark.unit
def test_weak_fit_and_protective_support_are_deterministic() -> None:
    config = load_scoring_config(ROOT / "config/scoring/v1.yaml")
    weak = TaskFitInput(
        task_id="WRD-10",
        environment="dev",
        required_skill_gap=1,
        difficulty_seniority_mismatch=1,
        deadline_pressure=0.8,
        dependency_impact=0.8,
        task_criticality=1,
        similar_task_evidence=0,
        mentoring_review_support=0,
        evidence_timestamp=NOW,
        evidence_references={
            name: (f"jira:WRD-10:{name}",)
            for name in (
                "required_skill_gap",
                "difficulty_seniority_mismatch",
                "deadline_pressure",
                "dependency_impact",
                "task_criticality",
                "similar_task_evidence",
                "mentoring_review_support",
            )
        },
    )
    protected = weak.model_copy(
        update={"similar_task_evidence": 1, "mentoring_review_support": 1}
    )

    weak_result = score_task_fit(weak, config, NOW)
    protected_result = score_task_fit(protected, config, NOW)

    assert weak_result.score == 95
    assert weak_result.level is RiskLevel.CRITICAL
    assert protected_result.score == 80
    assert protected_result.score < weak_result.score
    assert {factor.direction for factor in weak_result.factors} >= {"inverse_risk"}


@pytest.mark.unit
def test_missing_task_fit_evidence_never_becomes_zero_risk() -> None:
    config = load_scoring_config(ROOT / "config/scoring/v1.yaml")
    result = score_task_fit(
        TaskFitInput(task_id="WRD-10", environment="dev", evidence_timestamp=NOW),
        config,
        NOW,
    )
    assert result.score is None
    assert result.confidence is ConfidenceLevel.INSUFFICIENT_DATA
