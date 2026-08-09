from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from agent_api.auth.principal import AuthenticatedPrincipal
from agent_api.auth.roles import ApplicationRole
from agent_api.main import app
from agent_api.routes.profiles import get_administrator, get_profile_client


class RecordingProfileClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def update_capacity(
        self,
        *,
        employee_id: str,
        project_key: str,
        expected_version: int,
        weekly_capacity_hours: float,
        principal: AuthenticatedPrincipal,
        correlation_id: str,
    ) -> dict[str, Any]:
        self.calls.append(locals())
        return {
            "employee_id": employee_id,
            "weekly_capacity_hours": weekly_capacity_hours,
            "version": expected_version + 1,
        }

    async def create_profile(
        self,
        *,
        profile: dict[str, Any],
        project_key: str,
        principal: AuthenticatedPrincipal,
        correlation_id: str,
    ) -> dict[str, Any]:
        self.calls.append(locals())
        return {**profile, "version": 1}


async def administrator() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        actor_id="admin-001",
        display_label="Synthetic Admin",
        role=ApplicationRole.ADMINISTRATOR,
        environment="dev",
        project_scopes=("WRD",),
    )


def profile_client_dependency(client: RecordingProfileClient) -> Any:
    async def dependency() -> RecordingProfileClient:
        return client

    return dependency


@pytest.fixture(autouse=True)
def reset_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_admin_updates_capacity_with_etag_and_verified_identity() -> None:
    client = RecordingProfileClient()
    app.dependency_overrides[get_administrator] = administrator
    app.dependency_overrides[get_profile_client] = profile_client_dependency(client)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        response = await api.patch(
            "/api/v1/profiles/EMP-001/capacity?project_key=WRD",
            headers={"If-Match": '"1"', "X-Correlation-ID": "corr-profile"},
            json={"weekly_capacity_hours": 32},
        )

    assert response.status_code == 200
    assert response.headers["etag"] == '"2"'
    assert client.calls[0]["principal"].actor_id == "admin-001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_profile_body_cannot_forge_identity_and_etag_is_required() -> None:
    app.dependency_overrides[get_administrator] = administrator
    app.dependency_overrides[get_profile_client] = profile_client_dependency(
        RecordingProfileClient()
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        missing = await api.patch(
            "/api/v1/profiles/EMP-001/capacity?project_key=WRD",
            json={"weekly_capacity_hours": 32},
        )
        forged = await api.patch(
            "/api/v1/profiles/EMP-001/capacity?project_key=WRD",
            headers={"If-Match": '"1"'},
            json={"weekly_capacity_hours": 32, "actor_id": "forged"},
        )

    assert missing.status_code == 428
    assert forged.status_code == 422


@pytest.mark.unit
@pytest.mark.asyncio
async def test_admin_creates_profile_without_body_identity_or_environment() -> None:
    client = RecordingProfileClient()
    app.dependency_overrides[get_administrator] = administrator
    app.dependency_overrides[get_profile_client] = profile_client_dependency(client)
    payload = {
        "employee_id": "EMP-003",
        "role": "Backend Engineer",
        "seniority": "mid",
        "documented_skills": [{"name": "Python", "proficiency": 4}],
        "weekly_capacity_hours": 40,
        "project_allocations": [{"project_key": "WRD", "fraction": 1}],
        "mentoring_available": True,
        "capacity_overrides": [],
        "jira_account_id": None,
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        response = await api.post(
            "/api/v1/profiles?project_key=WRD",
            headers={"X-Correlation-ID": "corr-create-profile"},
            json=payload,
        )
        forged = await api.post(
            "/api/v1/profiles?project_key=WRD",
            json={**payload, "environment": "prod", "actor_id": "forged"},
        )

    assert response.status_code == 201
    assert response.headers["etag"] == '"1"'
    assert client.calls[0]["principal"].actor_id == "admin-001"
    assert "environment" not in client.calls[0]["profile"]
    assert forged.status_code == 422
