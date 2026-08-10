from __future__ import annotations

import os
from typing import Annotated, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from workforce_contracts.auth import AuthenticatedPrincipal
from workforce_persistence.database import Database
from workforce_persistence.scan_repository import DatabaseScanStore
from workforce_risk.scans.service import ScanService

from agent_api.auth.roles import ApplicationRole
from agent_api.dependencies import get_evidence_provider, get_scoring_client
from agent_api.routes.investigations import get_investigator
from agent_api.scans.pipeline import (
    DatabaseScanResultSink,
    EmployeeOverloadScanPipeline,
)

router = APIRouter(prefix="/api/v1")


class ManualScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(min_length=1, max_length=256)
    window: str = Field(min_length=1, max_length=128)


def get_scan_service() -> ScanService:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=503, detail="scan persistence unavailable")
    environment = cast(
        Literal["dev", "prod", "test"], os.getenv("APP_ENVIRONMENT", "dev")
    )
    database = Database(database_url)
    employee_ids = tuple(
        value.strip()
        for value in os.getenv("SCAN_EMPLOYEE_IDS", "EMP-002").split(",")
        if value.strip()
    )
    pipeline = EmployeeOverloadScanPipeline(
        evidence=get_evidence_provider(),
        scoring=get_scoring_client(),
        sink=DatabaseScanResultSink(database, environment=environment),
        employee_ids=employee_ids,
    )
    return ScanService(
        environment=environment,
        store=DatabaseScanStore(database),
        pipeline=pipeline,
    )


async def get_scan_manager(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_investigator)],
) -> AuthenticatedPrincipal:
    if principal.role not in {
        ApplicationRole.MANAGER,
        ApplicationRole.ADMINISTRATOR,
    }:
        raise HTTPException(status_code=403, detail="not authorized")
    return principal


@router.post("/scans", status_code=202)
async def request_manual_scan(
    payload: ManualScanRequest,
    background_tasks: BackgroundTasks,
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_scan_manager)],
    service: Annotated[ScanService, Depends(get_scan_service)],
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    if payload.scope != project_key or project_key not in principal.project_scopes:
        raise HTTPException(status_code=403, detail="scan scope is not authorized")
    correlation_id = x_correlation_id or f"corr-{uuid4()}"
    ticket = await service.request(
        scope=payload.scope, window=payload.window, correlation_id=correlation_id
    )
    if not ticket.duplicate:
        background_tasks.add_task(
            service.execute,
            ticket,
            scope=payload.scope,
            correlation_id=correlation_id,
        )
    return {
        "scan_run_id": ticket.scan_run_id,
        "state": ticket.state.value,
        "duplicate": ticket.duplicate,
        "correlation_id": correlation_id,
    }


@router.get("/scans/{scan_run_id}")
async def scan_status(
    scan_run_id: str,
    principal: Annotated[AuthenticatedPrincipal, Depends(get_scan_manager)],
    service: Annotated[ScanService, Depends(get_scan_service)],
) -> dict[str, object]:
    ticket = await service.status(scan_run_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="scan not found")
    return {"scan_run_id": ticket.scan_run_id, "state": ticket.state.value}
