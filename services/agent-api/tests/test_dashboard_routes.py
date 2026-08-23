from __future__ import annotations

import inspect
from collections.abc import Generator
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from agent_api.dashboard.models import (
    DashboardSnapshot,
    ProjectSummary,
    WorkloadDistribution,
)
from agent_api.main import app
from agent_api.routes import dashboard as dashboard_routes
from agent_api.routes.dashboard import get_dashboard_service
from httpx import ASGITransport, AsyncClient


class Service:
    async def build(self, project_key: str, correlation_id: str) -> DashboardSnapshot:
        return DashboardSnapshot(
            correlation_id=correlation_id,
            evidence_timestamp=datetime(2026, 8, 20, tzinfo=UTC),
            project=ProjectSummary(
                key=project_key,
                name="Workforce Real Data",
                total_tasks=15,
                completed_tasks=1,
                active_tasks=14,
                overdue_tasks=2,
                due_soon_tasks=5,
                blocked_tasks=3,
                missing_estimate_tasks=1,
                completion_percent=7,
            ),
            employees=(),
            tasks=(),
            alerts=(),
            workload=WorkloadDistribution(
                overloaded=0, balanced=0, insufficient_data=0
            ),
        )


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv(
        "ALLOWED_JIRA_PROJECTS",
        "WFD:Workforce Real Data,WRD:Workforce Risk Demo",
    )
    monkeypatch.setenv("ALLOW_ANONYMOUS_READ", "true")

    async def service() -> Service:
        return Service()

    app.dependency_overrides[get_dashboard_service] = service
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_projects_and_dashboard_are_available_without_browser_key() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        projects = await client.get("/api/v1/projects")
        dashboard = await client.get("/api/v1/dashboard?project_key=WFD")

    assert projects.status_code == 200
    assert [item["key"] for item in projects.json()["items"]] == ["WFD", "WRD"]
    assert dashboard.status_code == 200
    assert dashboard.json()["project"]["total_tasks"] == 15
    assert dashboard.headers["x-correlation-id"].startswith("corr-")


@pytest.mark.asyncio
async def test_dashboard_rejects_project_outside_allowlist() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/dashboard?project_key=OTHER")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_dashboard_profiles_load_from_postgres_when_env_fallback_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = SimpleNamespace(
        employee_id="WFD-EMP-001",
        role="Backend Engineer",
        weekly_capacity_hours=24.0,
        jira_account_id="account-1",
        skills=(("Java", 4), ("Spring Boot", 4)),
        allocations=(("WFD", 1.0),),
        capacity_overrides=(),
    )

    class SessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Database:
        closed = False

        def __init__(self, url: str) -> None:
            assert url == "postgresql+asyncpg://configured"

        def sessions(self) -> SessionContext:
            return SessionContext()

        async def close(self) -> None:
            Database.closed = True

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        async def list_for_environment(self, *, environment: str) -> tuple[object, ...]:
            assert environment == "dev"
            return (profile,)

    monkeypatch.delenv("WORKFORCE_DASHBOARD_PROFILES", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://configured")
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "WRD")
    monkeypatch.setattr(dashboard_routes, "Database", Database, raising=False)
    monkeypatch.setattr(
        dashboard_routes, "ProfileRepository", Repository, raising=False
    )

    result = dashboard_routes.load_workforce_profiles(project_key="WFD")
    profiles = await result if inspect.isawaitable(result) else result

    assert profiles["account-1"].employee_id == "WFD-EMP-001"
    assert profiles["account-1"].capacity_hours == 24
    assert profiles["account-1"].skills == ("Java", "Spring Boot")
    assert Database.closed is True
