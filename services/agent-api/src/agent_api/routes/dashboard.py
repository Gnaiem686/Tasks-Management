from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict

from agent_api.dashboard.models import DashboardSnapshot
from agent_api.dashboard.service import DashboardService, WorkforceProfile
from agent_api.dependencies import (
    EmployeeEvidenceProvider,
    SingleIssueJiraEvidenceProvider,
    WorkforceScoringClient,
    get_evidence_provider,
    get_scoring_client,
)
from agent_api.project_access import (
    ConfiguredProject,
    ProjectAccessDenied,
    anonymous_read_principal,
    configured_projects,
)

router = APIRouter(prefix="/api/v1")


class ProjectListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    items: tuple[ConfiguredProject, ...]


def load_workforce_profiles() -> dict[str, WorkforceProfile]:
    raw = os.getenv("WORKFORCE_DASHBOARD_PROFILES", "{}")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("WORKFORCE_DASHBOARD_PROFILES must be an object")
    return {
        str(account_id): WorkforceProfile.model_validate(profile)
        for account_id, profile in parsed.items()
    }


def get_dashboard_service(
    evidence: Annotated[EmployeeEvidenceProvider, Depends(get_evidence_provider)],
    scoring: Annotated[WorkforceScoringClient, Depends(get_scoring_client)],
) -> DashboardService:
    if not isinstance(evidence, SingleIssueJiraEvidenceProvider):
        raise HTTPException(status_code=503, detail="Jira dashboard is unavailable")
    raw_environment = os.getenv("APP_ENVIRONMENT", "dev")
    if raw_environment not in {"dev", "prod", "test"}:
        raise RuntimeError("APP_ENVIRONMENT must be dev, prod, or test")
    return DashboardService(
        jira=evidence.jira_client,
        scoring=scoring,
        profiles=load_workforce_profiles(),
        jira_site_url=os.getenv("JIRA_SITE_URL", os.getenv("JIRA_CLOUD_ID", "")),
        today=lambda: datetime.now().astimezone().date(),
        environment=cast(Literal["dev", "prod", "test"], raw_environment),
    )


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects() -> ProjectListResponse:
    if os.getenv("ALLOW_ANONYMOUS_READ", "false").casefold() != "true":
        raise HTTPException(status_code=401, detail="authentication required")
    return ProjectListResponse(items=configured_projects())


@router.get("/dashboard", response_model=DashboardSnapshot)
async def dashboard(
    response: Response,
    project_key: Annotated[str, Query(pattern=r"^[A-Z][A-Z0-9]{1,19}$")],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> DashboardSnapshot:
    try:
        anonymous_read_principal(project_key)
    except ProjectAccessDenied as exc:
        raise HTTPException(status_code=403, detail="project is not available") from exc
    correlation_id = x_correlation_id or f"corr-{uuid4()}"
    response.headers["X-Correlation-ID"] = correlation_id
    return await service.build(project_key, correlation_id)
