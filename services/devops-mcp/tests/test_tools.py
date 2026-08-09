from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from devops_mcp.backends import FixtureBackend
from devops_mcp.tools.deployments import DeploymentRequest, inspect_deployment
from devops_mcp.tools.kubernetes import KubernetesRequest, inspect_workloads
from devops_mcp.tools.logs import LogRequest, read_logs
from devops_mcp.tools.prometheus import MetricRequest, query_metric
from devops_mcp.tools.queues import QueueRequest, inspect_queues
from pydantic import ValidationError


class UnsafeLogs(FixtureBackend):
    async def read(self, **kwargs: Any) -> list[str]:
        return ["Authorization: Bearer top-secret", "password=hidden-value"]


def base() -> dict[str, str]:
    return {
        "environment": "dev",
        "correlation_id": "corr-devops",
        "schema_version": "1.0",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_each_read_only_tool_returns_typed_environment_envelope() -> None:
    backend = FixtureBackend()
    now = datetime.now(UTC)
    results = [
        await inspect_workloads(
            KubernetesRequest(**base(), resource="pods"), reader=backend
        ),
        await query_metric(
            MetricRequest(**base(), query_name="api_error_rate"), reader=backend
        ),
        await read_logs(
            LogRequest(
                **base(),
                service="agent-api",
                start=now - timedelta(minutes=5),
                end=now,
                limit=20,
            ),
            reader=backend,
        ),
        await inspect_queues(QueueRequest(**base()), reader=backend),
        await inspect_deployment(
            DeploymentRequest(**base(), source="jira_integration"), reader=backend
        ),
    ]
    assert all(
        item.schema_version == "1.0" and item.environment == "dev" for item in results
    )
    assert all(item.correlation_id == "corr-devops" for item in results)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_logs_are_bounded_and_secrets_are_redacted() -> None:
    now = datetime.now(UTC)
    result = await read_logs(
        LogRequest(
            **base(),
            service="agent-api",
            start=now - timedelta(minutes=5),
            end=now,
            limit=2,
        ),
        reader=UnsafeLogs(),
    )
    rendered = str(result.data)
    assert "top-secret" not in rendered and "hidden-value" not in rendered
    assert result.data["returned"] == 2


@pytest.mark.unit
def test_arbitrary_queries_services_and_time_ranges_are_rejected() -> None:
    now = datetime.now(UTC)
    with pytest.raises(PermissionError):
        import asyncio

        asyncio.run(
            query_metric(
                MetricRequest(**base(), query_name="up or vector(1)"),
                reader=FixtureBackend(),
            )
        )
    with pytest.raises(ValidationError):
        LogRequest(
            **base(), service="postgres", start=now - timedelta(minutes=5), end=now
        )
    with pytest.raises(ValidationError):
        LogRequest(
            **base(), service="agent-api", start=now - timedelta(hours=2), end=now
        )


@pytest.mark.unit
def test_fixture_backend_is_forbidden_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from devops_mcp.backends import get_backend

    monkeypatch.setenv("APP_ENVIRONMENT", "prod")
    monkeypatch.setenv("DEVOPS_BACKEND_MODE", "fixture")
    with pytest.raises(RuntimeError, match="forbidden"):
        get_backend()
