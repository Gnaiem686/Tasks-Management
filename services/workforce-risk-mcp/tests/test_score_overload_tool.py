from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from workforce_risk_mcp.tools.score_overload import (
    DuplicateCorrelationId,
    ScoreOverloadRequest,
    score_overload,
)

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "scenarios" / "overloaded_employee.json"
CONFIG = ROOT / "config" / "scoring" / "v1.yaml"


def request(**changes: object) -> ScoreOverloadRequest:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "environment": "dev",
        "correlation_id": "corr-mcp-score-1",
        "deadline_at": "2026-08-06T12:01:00Z",
        "scored_at": "2026-08-06T12:00:00Z",
        "input": json.loads(FIXTURE.read_text()),
    }
    payload.update(changes)
    return ScoreOverloadRequest.model_validate(payload)


@pytest.mark.unit
def test_tool_returns_typed_deterministic_result() -> None:
    response = score_overload(request(), config_path=CONFIG, service_environment="dev")

    assert response.schema_version == "1.0"
    assert response.environment == "dev"
    assert response.correlation_id == "corr-mcp-score-1"
    assert response.status == "success"
    assert response.result is not None
    assert response.result.score == 88
    assert response.result.level == "critical"
    assert response.result.confidence == "high"
    assert response.result.scoring_model_version == "employee-overload-v1"


@pytest.mark.unit
def test_tool_rejects_environment_mismatch_and_expired_deadline() -> None:
    with pytest.raises(ValueError, match="environment mismatch"):
        score_overload(request(), config_path=CONFIG, service_environment="prod")
    expired = request(
        correlation_id="corr-expired",
        deadline_at=datetime(2026, 8, 6, 11, tzinfo=UTC),
    )
    with pytest.raises(TimeoutError, match="deadline"):
        score_overload(expired, config_path=CONFIG, service_environment="dev")


@pytest.mark.unit
def test_duplicate_correlation_id_is_rejected() -> None:
    first = request(correlation_id="corr-duplicate")
    score_overload(first, config_path=CONFIG, service_environment="dev")

    with pytest.raises(DuplicateCorrelationId):
        score_overload(first, config_path=CONFIG, service_environment="dev")


@pytest.mark.unit
def test_insufficient_data_is_explicit() -> None:
    raw = json.loads(FIXTURE.read_text())
    raw["available_capacity_hours"] = None
    response = score_overload(
        request(correlation_id="corr-missing", input=raw),
        config_path=CONFIG,
        service_environment="dev",
    )

    assert response.status == "success"
    assert response.result is not None
    assert response.result.score is None
    assert response.result.confidence == "insufficient-data"
