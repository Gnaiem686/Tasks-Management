from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.main import app
from agent_api.routes.alerts import get_alert_store
from agent_api.routes.investigations import get_investigator
from httpx import ASGITransport, AsyncClient
from workforce_contracts.auth import AuthenticatedPrincipal


class Store:
    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        return (
            [
                {
                    "id": ALERT_ID,
                    "state": "new",
                    "severity": "high",
                    "version": 3,
                    "recurrence_count": 2,
                }
            ],
            1,
        )

    async def transition(self, **kwargs: Any) -> dict[str, Any] | None:
        return {"id": ALERT_ID, "state": "acknowledged", "version": 4}


ALERT_ID = "00000000-0000-4000-8000-000000000001"


async def principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        actor_id="manager",
        display_label="Manager",
        role=ApplicationRole.MANAGER,
        environment="test",
        project_scopes=("WRD",),
    )


async def store() -> Store:
    return Store()


@pytest.fixture(autouse=True)
def overrides(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("JIRA_PROJECT_KEY", "WRD")
    app.dependency_overrides[get_investigator] = principal
    app.dependency_overrides[get_alert_store] = store
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_alerts_are_paginated_and_transition_uses_etag() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        listed = await client.get(
            "/api/v1/alerts?project_key=WRD&page=1&page_size=20&sort=-created_at"
        )
        changed = await client.patch(
            f"/api/v1/alerts/{ALERT_ID}?project_key=WRD",
            json={"state": "acknowledged"},
            headers={"If-Match": '"3"'},
        )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["recurrence_count"] == 2
    assert changed.status_code == 200
    assert changed.headers["etag"] == '"4"'


@pytest.mark.asyncio
async def test_alert_transition_requires_etag() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            f"/api/v1/alerts/{ALERT_ID}?project_key=WRD",
            json={"state": "acknowledged"},
        )
    assert response.status_code == 428
