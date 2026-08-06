from __future__ import annotations

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict
from workforce_risk.models import RiskResult

from agent_api.dependencies import (
    EmployeeEvidenceProvider,
    JiraEvidenceTimeout,
    WorkforceMcpInvalidResponse,
    WorkforceScoringClient,
    get_evidence_provider,
    get_scoring_client,
)
from agent_api.errors import safe_error

router = APIRouter(prefix="/api/v1")


class OverloadRiskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    correlation_id: str
    degraded: bool
    persisted: bool = False
    missing_sources: tuple[str, ...]
    result: RiskResult


@router.get("/employees/{employee_id}/overload-risk")
async def employee_overload_risk(
    employee_id: str,
    response: Response,
    project_key: Annotated[str, Query(min_length=1)],
    evidence_provider: Annotated[
        EmployeeEvidenceProvider, Depends(get_evidence_provider)
    ],
    scoring_client: Annotated[WorkforceScoringClient, Depends(get_scoring_client)],
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> Any:
    correlation_id = x_correlation_id or f"corr-{uuid4()}"
    response.headers["X-Correlation-ID"] = correlation_id
    if project_key != "WRD":
        return safe_error(
            status_code=403,
            error_code="PROJECT_NOT_ALLOWED",
            message="The requested project is outside the configured scope.",
            correlation_id=correlation_id,
        )
    try:
        evidence = await evidence_provider.get_employee_overload(
            employee_id, project_key, correlation_id
        )
    except JiraEvidenceTimeout:
        return safe_error(
            status_code=503,
            error_code="JIRA_EVIDENCE_UNAVAILABLE",
            message="Current evidence is unavailable; no risk claim was produced.",
            correlation_id=correlation_id,
            degraded=True,
        )
    try:
        raw_result = await scoring_client.score(evidence.input, correlation_id)
        result = RiskResult.model_validate(raw_result)
    except (WorkforceMcpInvalidResponse, ValueError):
        return safe_error(
            status_code=502,
            error_code="WORKFORCE_MCP_INVALID_RESPONSE",
            message="The scoring service returned an invalid response.",
            correlation_id=correlation_id,
        )
    return OverloadRiskResponse(
        correlation_id=correlation_id,
        degraded=evidence.degraded,
        missing_sources=evidence.missing_sources,
        result=result,
    )
