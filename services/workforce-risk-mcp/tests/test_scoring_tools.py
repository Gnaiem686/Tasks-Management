from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from workforce_risk.models import ProjectDeliveryInput, TaskFitInput
from workforce_risk_mcp.tools.scoring import (
    ScoreProjectDeliveryRequest,
    ScoreTaskFitRequest,
    score_project_delivery_tool,
    score_task_fit_tool,
)

ROOT = Path(__file__).parents[3]
CONFIG = ROOT / "config/scoring/v1.yaml"
NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)


def references(names: tuple[str, ...], subject: str) -> dict[str, tuple[str, ...]]:
    return {name: (f"jira:{subject}:{name}",) for name in names}


@pytest.mark.unit
def test_task_fit_tool_returns_typed_envelope() -> None:
    names = (
        "required_skill_gap",
        "difficulty_seniority_mismatch",
        "deadline_pressure",
        "dependency_impact",
        "task_criticality",
        "similar_task_evidence",
        "mentoring_review_support",
    )
    input_data = TaskFitInput(
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
        evidence_references=references(names, "WRD-10"),
    )
    response = score_task_fit_tool(
        ScoreTaskFitRequest(
            schema_version="1.0",
            environment="dev",
            correlation_id="corr-task-fit-tool",
            deadline_at=NOW + timedelta(seconds=10),
            scored_at=NOW,
            input=input_data,
        ),
        config_path=CONFIG,
        service_environment="dev",
    )
    assert response.status == "success"
    assert response.result.score == 95
    assert response.result.scoring_model_version == "task-fit-v1"


@pytest.mark.unit
def test_project_delivery_tool_rejects_environment_mismatch() -> None:
    input_data = ProjectDeliveryInput(
        project_id="WRD", environment="dev", evidence_timestamp=NOW
    )
    request = ScoreProjectDeliveryRequest(
        schema_version="1.0",
        environment="dev",
        correlation_id="corr-project-tool",
        deadline_at=NOW + timedelta(seconds=10),
        scored_at=NOW,
        input=input_data,
    )
    with pytest.raises(ValueError, match="environment mismatch"):
        score_project_delivery_tool(
            request, config_path=CONFIG, service_environment="prod"
        )
