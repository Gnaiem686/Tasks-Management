from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.main import app
from agent_api.routes.audit import get_audit_store
from agent_api.routes.investigations import get_investigator
from httpx import ASGITransport, AsyncClient
from workforce_contracts.auth import AuthenticatedPrincipal


class Store:
    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int, bool]:
        return (
            [
                {
                    "sequence_number": 1,
                    "action_type": "proposal.created",
                    "safe_metadata": {},
                }
            ],
            1,
            True,
        )


async def store() -> Store:
    return Store()


def principal(role: ApplicationRole) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        actor_id="actor",
        display_label="Actor",
        role=role,
        environment="test",
        project_scopes=("WRD",),
    )


async def viewer() -> AuthenticatedPrincipal:
    return principal(ApplicationRole.VIEWER)


async def administrator() -> AuthenticatedPrincipal:
    return principal(ApplicationRole.ADMINISTRATOR)


@pytest.fixture(autouse=True)
def overrides(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("JIRA_PROJECT_KEY", "WRD")
    app.dependency_overrides[get_audit_store] = store
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_only_administrator_can_read_safe_audit_history() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        app.dependency_overrides[get_investigator] = viewer
        denied = await client.get("/api/v1/audit?project_key=WRD")
        app.dependency_overrides[get_investigator] = administrator
        allowed = await client.get("/api/v1/audit?project_key=WRD")
    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["chain_valid"] is True
    assert "token" not in str(allowed.json()).lower()
