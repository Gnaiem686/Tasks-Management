from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.main import app
from agent_api.routes.investigations import get_investigator
from agent_api.routes.proposals import get_proposal_client
from httpx import ASGITransport, AsyncClient
from workforce_contracts.auth import AuthenticatedPrincipal


class Client:
    def __init__(self) -> None:
        self.request: dict[str, Any] = {}
        self.principal: AuthenticatedPrincipal | None = None

    async def create_proposal(
        self,
        *,
        request: dict[str, Any],
        principal: AuthenticatedPrincipal,
        correlation_id: str,
    ) -> dict[str, Any]:
        self.request, self.principal = request, principal
        return {"proposal_id": "proposal-1", "state": "pending", "version": 1}

    async def get_proposal(
        self,
        *,
        request: dict[str, Any],
        principal: AuthenticatedPrincipal,
        correlation_id: str,
    ) -> dict[str, Any]:
        self.request, self.principal = request, principal
        return {"proposal_id": request["proposal_id"], "state": "pending", "version": 1}

    async def decide_proposal(
        self,
        *,
        request: dict[str, Any],
        principal: AuthenticatedPrincipal,
        correlation_id: str,
    ) -> dict[str, Any]:
        self.request, self.principal = request, principal
        return {
            "proposal_id": request["proposal_id"],
            "state": "executing",
            "version": 2,
        }


def principal(
    role: ApplicationRole = ApplicationRole.MANAGER,
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        actor_id="verified-manager",
        display_label="Manager",
        role=role,
        environment="test",
        project_scopes=("WRD",),
    )


def simulation() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "simulation_id": "simulation-1",
        "environment": "test",
        "project_key": "WRD",
        "task_id": "WRD-1",
        "current_assignee_id": "EMP-002",
        "proposed_assignee_id": "EMP-003",
        "candidate_ids": ["EMP-003"],
        "confidence": "high",
        "evidence_fingerprint": "a" * 64,
        "scoring_model_versions": ["employee-v1", "task-v1", "project-v1"],
        "simulated_at": now.isoformat(),
        "safe_payload": {"score": 30},
    }


def dependency(value: Any) -> Any:
    async def provide() -> Any:
        return value

    return provide


@pytest.fixture(autouse=True)
def overrides() -> Generator[None, None, None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manager_creates_and_approves_without_identity_or_fingerprint_input() -> (
    None
):
    client = Client()
    app.dependency_overrides[get_investigator] = dependency(principal())
    app.dependency_overrides[get_proposal_client] = dependency(client)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        created = await http.post(
            "/api/v1/proposals?project_key=WRD",
            json={
                "simulation_id": "simulation-1",
                "idempotency_key": "create-key-1",
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            },
            headers={"Authorization": "Bearer wrk_test_super-secret"},
        )
        approved = await http.post(
            "/api/v1/proposals/proposal-1/approve?project_key=WRD",
            json={"expected_version": 1, "idempotency_key": "approve-key-1"},
        )
    assert created.status_code == 201 and approved.status_code == 202
    assert client.principal is not None
    assert client.principal.actor_id == "verified-manager"
    assert "actor_id" not in client.request
    assert "current_evidence_fingerprint" not in client.request
    assert "wrk_test_super-secret" not in str(client.request)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_viewer_and_forged_identity_are_rejected() -> None:
    client = Client()
    app.dependency_overrides[get_investigator] = dependency(
        principal(ApplicationRole.VIEWER)
    )
    app.dependency_overrides[get_proposal_client] = dependency(client)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        denied = await http.post(
            "/api/v1/proposals/proposal-1/approve?project_key=WRD",
            json={"expected_version": 1, "idempotency_key": "approve-key-1"},
        )
        forged = await http.post(
            "/api/v1/proposals/proposal-1/approve?project_key=WRD",
            json={
                "expected_version": 1,
                "idempotency_key": "approve-key-1",
                "actor_id": "administrator",
            },
        )
    assert denied.status_code == 403
    assert forged.status_code in {403, 422}
