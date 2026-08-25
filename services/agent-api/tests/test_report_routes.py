from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.main import app
from agent_api.routes.investigations import get_investigator
from agent_api.routes.reports import get_report_store
from httpx import ASGITransport, AsyncClient
from workforce_contracts.auth import AuthenticatedPrincipal


class Store:
    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        return ([{"id": REPORT_ID, "status": "stored", "object_version": "v7"}], 1)

    async def download_url(self, **kwargs: Any) -> str | None:
        assert kwargs["report_id"] == REPORT_ID
        return "https://signed.invalid/exact-object?versionId=v7"


REPORT_ID = "00000000-0000-4000-8000-000000000002"


async def principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        actor_id="viewer",
        display_label="Viewer",
        role=ApplicationRole.VIEWER,
        environment="test",
        project_scopes=("WRD",),
    )


async def store() -> Store:
    return Store()


@pytest.fixture(autouse=True)
def overrides(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("JIRA_PROJECT_KEY", "WRD")
    app.dependency_overrides[get_investigator] = principal
    app.dependency_overrides[get_report_store] = store
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_report_list_and_exact_version_download() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        listed = await client.get("/api/v1/reports?project_key=WRD")
        download = await client.post(
            f"/api/v1/reports/{REPORT_ID}/download?project_key=WRD"
        )
    assert listed.status_code == 200 and listed.json()["total"] == 1
    assert download.status_code == 200
    assert "versionId=v7" in download.json()["url"]
    assert download.json()["expires_in"] <= 300
