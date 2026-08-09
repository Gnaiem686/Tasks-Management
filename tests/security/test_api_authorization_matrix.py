from __future__ import annotations

from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.main import app
from agent_api.routes import investigations
from agent_api.routes.alerts import get_alert_store
from agent_api.routes.audit import get_audit_store
from agent_api.routes.investigations import _AUTH_CACHE, _cache_key, get_investigator
from agent_api.routes.reports import get_report_store
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from workforce_contracts.auth import AuthenticatedPrincipal


class AlertStore:
    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        return [], 0

    async def transition(self, **kwargs: Any) -> dict[str, Any] | None:
        return {"id": kwargs["alert_id"], "version": 2, "state": "acknowledged"}


class ReportStore:
    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        return [], 0

    async def download_url(self, **kwargs: Any) -> str | None:
        return None


class AuditStore:
    async def list(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int, bool]:
        return [], 0, True


def provider(role: ApplicationRole, environment: str = "test") -> Any:
    async def dependency() -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            actor_id="verified",
            display_label="Verified",
            role=role,
            environment=environment,
            project_scopes=("WRD",),
        )

    return dependency


async def alerts() -> AlertStore:
    return AlertStore()


async def reports() -> ReportStore:
    return ReportStore()


async def audits() -> AuditStore:
    return AuditStore()


@pytest.fixture(autouse=True)
def overrides(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("JIRA_PROJECT_KEY", "WRD")
    app.dependency_overrides[get_alert_store] = alerts
    app.dependency_overrides[get_report_store] = reports
    app.dependency_overrides[get_audit_store] = audits
    yield
    app.dependency_overrides.clear()


@pytest.mark.security
@pytest.mark.asyncio
async def test_role_matrix_and_cross_project_access() -> None:
    alert_id = "00000000-0000-4000-8000-000000000001"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        app.dependency_overrides[get_investigator] = provider(ApplicationRole.VIEWER)
        assert (await client.get("/api/v1/alerts?project_key=WRD")).status_code == 200
        assert (
            await client.patch(
                f"/api/v1/alerts/{alert_id}?project_key=WRD",
                json={"state": "acknowledged"},
                headers={"If-Match": '"1"'},
            )
        ).status_code == 403
        assert (await client.get("/api/v1/audit?project_key=WRD")).status_code == 403
        assert (
            await client.get("/api/v1/reports?project_key=OTHER")
        ).status_code == 403
        app.dependency_overrides[get_investigator] = provider(ApplicationRole.MANAGER)
        assert (
            await client.patch(
                f"/api/v1/alerts/{alert_id}?project_key=WRD",
                json={"state": "acknowledged"},
                headers={"If-Match": '"1"'},
            )
        ).status_code == 200
        assert (await client.get("/api/v1/audit?project_key=WRD")).status_code == 403
        app.dependency_overrides[get_investigator] = provider(
            ApplicationRole.ADMINISTRATOR
        )
        assert (await client.get("/api/v1/audit?project_key=WRD")).status_code == 200


def test_authentication_cache_never_uses_raw_api_key_as_key() -> None:
    raw = "Bearer wrk_test_top-secret-value"
    digest = _cache_key(raw)
    assert digest is not None
    assert raw not in digest and "top-secret-value" not in digest


class UnavailableDatabase:
    def __init__(self, url: str) -> None:
        pass

    @asynccontextmanager
    async def transaction(self) -> Any:
        raise ConnectionError("database unavailable")
        yield

    async def close(self) -> None:
        pass


def request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [],
        }
    )


@pytest.mark.security
@pytest.mark.asyncio
async def test_auth_store_outage_allows_cached_read_but_write_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unavailable")
    monkeypatch.setenv("API_KEY_HMAC_PEPPER", "x" * 32)
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setattr(investigations, "Database", UnavailableDatabase)
    raw = "Bearer wrk_test_cached"
    key = _cache_key(raw)
    assert key is not None
    cached = AuthenticatedPrincipal(
        actor_id="cached-viewer",
        display_label="Cached",
        role=ApplicationRole.VIEWER,
        environment="test",
        project_scopes=("WRD",),
    )
    _AUTH_CACHE[key] = (datetime.now(UTC) + timedelta(seconds=10), cached)
    assert (
        await get_investigator(request("GET", "/api/v1/alerts"), "WRD", raw) == cached
    )
    with pytest.raises(HTTPException) as denied:
        await get_investigator(request("POST", "/api/v1/proposals"), "WRD", raw)
    assert denied.value.status_code == 503
    _AUTH_CACHE.clear()
