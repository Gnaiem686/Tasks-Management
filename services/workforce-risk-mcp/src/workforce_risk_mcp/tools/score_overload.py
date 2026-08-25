from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from workforce_risk.models import EmployeeOverloadInput, RiskResult
from workforce_risk.scoring.config import load_scoring_config
from workforce_risk.scoring.overload import score_employee_overload


class DuplicateCorrelationId(ValueError):
    pass


class ScoreOverloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    environment: Literal["dev", "prod", "test"]
    correlation_id: str = Field(min_length=1, max_length=128)
    deadline_at: AwareDatetime
    scored_at: AwareDatetime
    input: EmployeeOverloadInput


class ScoreOverloadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    environment: Literal["dev", "prod", "test"]
    correlation_id: str
    status: Literal["success"] = "success"
    result: RiskResult | None


_correlations: set[str] = set()
_correlation_lock = Lock()


def score_overload(
    request: ScoreOverloadRequest,
    *,
    config_path: Path,
    service_environment: str,
) -> ScoreOverloadResponse:
    if request.environment != service_environment:
        raise ValueError("request environment mismatch")
    if request.deadline_at <= request.scored_at:
        raise TimeoutError("request deadline has expired")
    with _correlation_lock:
        if request.correlation_id in _correlations:
            raise DuplicateCorrelationId("duplicate correlation ID")
        _correlations.add(request.correlation_id)
    config = load_scoring_config(config_path)
    result = score_employee_overload(request.input, config, request.scored_at)
    return ScoreOverloadResponse(
        environment=request.environment,
        correlation_id=request.correlation_id,
        result=result,
    )
