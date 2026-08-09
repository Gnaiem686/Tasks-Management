from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.main import app
from agent_api.routes.investigations import get_investigator
from agent_api.routes.scans import get_scan_service
from httpx import ASGITransport, AsyncClient
from workforce_contracts.auth import AuthenticatedPrincipal
from workforce_risk.scans.service import (
    PipelineResult,
    ScanService,
    ScanState,
    ScanTicket,
)


class Store:
    def __init__(self) -> None:
        self.state = ScanState.QUEUED

    async def enqueue(self, **kwargs: str) -> ScanTicket:
        return ScanTicket("scan-api-1", self.state)

    async def transition(
        self,
        scan_run_id: str,
        *,
        expected: ScanState,
        target: ScanState,
        failure_reason: str | None = None,
    ) -> bool:
        self.state = target
        return True

    async def get(self, scan_run_id: str) -> ScanTicket | None:
        return ScanTicket(scan_run_id, self.state)


class Pipeline:
    async def run(self, *, scope: str, correlation_id: str) -> PipelineResult:
        return PipelineResult(False, ("risk-1",), ("alert-1",), "report-1")


def dependency(value: Any) -> Any:
    async def provide() -> Any:
        return value

    return provide


@pytest.fixture(autouse=True)
def overrides() -> Generator[None, None, None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


async def post_scan() -> Any:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            "/api/v1/scans?project_key=WRD",
            json={"scope": "WRD", "window": "2026-08-09"},
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manual_scan_returns_202_and_run_id_for_manager() -> None:
    principal = AuthenticatedPrincipal(
        actor_id="manager-1",
        display_label="Manager",
        role=ApplicationRole.MANAGER,
        environment="test",
        project_scopes=("WRD",),
    )
    app.dependency_overrides[get_investigator] = dependency(principal)
    app.dependency_overrides[get_scan_service] = dependency(
        ScanService(environment="test", store=Store(), pipeline=Pipeline())
    )
    response = await post_scan()
    assert response.status_code == 202
    assert response.json()["scan_run_id"] == "scan-api-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_viewer_cannot_request_manual_scan() -> None:
    principal = AuthenticatedPrincipal(
        actor_id="viewer-1",
        display_label="Viewer",
        role=ApplicationRole.VIEWER,
        environment="test",
        project_scopes=("WRD",),
    )
    app.dependency_overrides[get_investigator] = dependency(principal)
    app.dependency_overrides[get_scan_service] = dependency(
        ScanService(environment="test", store=Store(), pipeline=Pipeline())
    )
    assert (await post_scan()).status_code == 403
