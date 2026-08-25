from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from workforce_risk.models import ProjectDeliveryInput, RiskResult, TaskFitInput
from workforce_risk.scoring.config import load_scoring_config
from workforce_risk.scoring.project_delivery import score_project_delivery
from workforce_risk.scoring.task_fit import score_task_fit


class ScoreTaskFitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    environment: Literal["dev", "prod", "test"]
    correlation_id: str = Field(min_length=1, max_length=128)
    deadline_at: AwareDatetime
    scored_at: AwareDatetime
    input: TaskFitInput


class ScoreProjectDeliveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    environment: Literal["dev", "prod", "test"]
    correlation_id: str = Field(min_length=1, max_length=128)
    deadline_at: AwareDatetime
    scored_at: AwareDatetime
    input: ProjectDeliveryInput


class ScoreFamilyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    environment: Literal["dev", "prod", "test"]
    correlation_id: str
    status: Literal["success"] = "success"
    result: RiskResult


def _validate_request(
    request: ScoreTaskFitRequest | ScoreProjectDeliveryRequest,
    service_environment: str,
) -> None:
    if request.environment != service_environment:
        raise ValueError("request environment mismatch")
    if request.deadline_at <= request.scored_at:
        raise TimeoutError("request deadline has expired")


def score_task_fit_tool(
    request: ScoreTaskFitRequest, *, config_path: Path, service_environment: str
) -> ScoreFamilyResponse:
    _validate_request(request, service_environment)
    result = score_task_fit(
        request.input, load_scoring_config(config_path), request.scored_at
    )
    return ScoreFamilyResponse(
        environment=request.environment,
        correlation_id=request.correlation_id,
        result=result,
    )


def score_project_delivery_tool(
    request: ScoreProjectDeliveryRequest,
    *,
    config_path: Path,
    service_environment: str,
) -> ScoreFamilyResponse:
    _validate_request(request, service_environment)
    result = score_project_delivery(
        request.input, load_scoring_config(config_path), request.scored_at
    )
    return ScoreFamilyResponse(
        environment=request.environment,
        correlation_id=request.correlation_id,
        result=result,
    )
