from datetime import UTC, datetime
from pathlib import Path

import pytest
from workforce_risk.models import ProjectDeliveryInput, RiskLevel
from workforce_risk.scoring.config import load_scoring_config
from workforce_risk.scoring.project_delivery import score_project_delivery

ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)


@pytest.mark.unit
def test_project_delivery_score_is_weighted_and_repeatable() -> None:
    config = load_scoring_config(ROOT / "config/scoring/v1.yaml")
    values = {
        "schedule_gap": 0.8,
        "remaining_capacity_pressure": 1,
        "blocked_overdue_work": 0.7,
        "workload_concentration": 0.6,
        "unplanned_work": 0.5,
        "critical_weak_fit": 1,
    }
    input_data = ProjectDeliveryInput(
        project_id="WRD",
        environment="dev",
        **values,
        evidence_timestamp=NOW,
        evidence_references={name: (f"jira:WRD:{name}",) for name in values},
    )
    first = score_project_delivery(input_data, config, NOW)
    assert first.score == 78
    assert first.level is RiskLevel.CRITICAL
    assert first == score_project_delivery(input_data, config, NOW)
