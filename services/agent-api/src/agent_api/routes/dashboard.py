from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from workforce_persistence.database import Database
from workforce_persistence.repositories import ProfileRepository, StoredProfile

from agent_api.dashboard.models import DashboardSnapshot
from agent_api.dashboard.service import DashboardService, WorkforceProfile
from agent_api.dependencies import (
    EmployeeEvidenceProvider,
    SingleIssueJiraEvidenceProvider,
    WorkforceScoringClient,
    get_evidence_provider,
    get_scoring_client,
)
from agent_api.progress_history import DatabaseProgressHistoryRecorder
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


def _configured_workforce_profiles(raw: str) -> dict[str, WorkforceProfile]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("WORKFORCE_DASHBOARD_PROFILES must be an object")
    return {
        str(account_id): WorkforceProfile.model_validate(profile)
        for account_id, profile in parsed.items()
    }


def _database_workforce_profiles(
    profiles: tuple[StoredProfile, ...], *, project_key: str
) -> dict[str, WorkforceProfile]:
    now = datetime.now(UTC)
    result: dict[str, WorkforceProfile] = {}
    for profile in profiles:
        allocation = dict(profile.allocations).get(project_key)
        if profile.jira_account_id is None or allocation is None:
            continue
        weekly_capacity = next(
            (
                capacity
                for starts_at, ends_at, capacity, _reason in profile.capacity_overrides
                if starts_at <= now < ends_at
            ),
            profile.weekly_capacity_hours,
        )
        result[profile.jira_account_id] = WorkforceProfile(
            employee_id=profile.employee_id,
            display_name=profile.employee_id,
            role=profile.role,
            capacity_hours=weekly_capacity * allocation,
            skills=tuple(skill for skill, _proficiency in profile.skills),
        )
    return result


async def load_workforce_profiles(
    *, project_key: str | None = None
) -> dict[str, WorkforceProfile]:
    raw = os.getenv("WORKFORCE_DASHBOARD_PROFILES", "").strip()
    if raw and raw != "{}":
        return _configured_workforce_profiles(raw)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return {}
    database = Database(database_url)
    try:
        async with database.sessions() as session:
            stored = await ProfileRepository(session).list_for_environment(
                environment=os.getenv("APP_ENVIRONMENT", "dev")
            )
        return _database_workforce_profiles(
            stored,
            project_key=project_key or os.getenv("JIRA_PROJECT_KEY") or "WFD",
        )
    finally:
        await database.close()


async def get_dashboard_service(
    evidence: Annotated[EmployeeEvidenceProvider, Depends(get_evidence_provider)],
    scoring: Annotated[WorkforceScoringClient, Depends(get_scoring_client)],
    project_key: Annotated[str, Query(pattern=r"^[A-Z][A-Z0-9]{1,19}$")],
) -> DashboardService:
    if not isinstance(evidence, SingleIssueJiraEvidenceProvider):
        raise HTTPException(status_code=503, detail="Jira dashboard is unavailable")
    raw_environment = os.getenv("APP_ENVIRONMENT", "dev")
    if raw_environment not in {"dev", "prod", "test"}:
        raise RuntimeError("APP_ENVIRONMENT must be dev, prod, or test")
    return DashboardService(
        jira=evidence.jira_client,
        scoring=scoring,
        profiles=await load_workforce_profiles(project_key=project_key),
        jira_site_url=os.getenv("JIRA_SITE_URL", os.getenv("JIRA_CLOUD_ID", "")),
        today=lambda: datetime.now().astimezone().date(),
        environment=cast(Literal["dev", "prod", "test"], raw_environment),
        history=(
            DatabaseProgressHistoryRecorder(
                environment=raw_environment,
                database_url=os.getenv("DATABASE_URL"),
                timezone_name=os.getenv("WORKFORCE_TIMEZONE", "Asia/Jerusalem"),
            )
            if os.getenv("DATABASE_URL")
            else None
        ),
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
