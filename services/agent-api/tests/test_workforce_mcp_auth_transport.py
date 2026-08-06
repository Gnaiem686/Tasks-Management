from __future__ import annotations

import asyncio
import os
import socket
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from agent_api.auth.internal_context import (
    InternalAuthorizationError,
    InternalContextSigner,
)
from agent_api.auth.principal import AuthenticatedPrincipal
from agent_api.auth.roles import ApplicationRole
from agent_api.clients.workforce_mcp import StreamableHttpProfileClient
from sqlalchemy import delete
from workforce_persistence.database import Database
from workforce_persistence.models import EmployeeProfile

NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)
SECRET = b"internal-context-test-secret-at-least-32-bytes"


def principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        actor_id="admin-001",
        display_label="Synthetic Administrator",
        role=ApplicationRole.ADMINISTRATOR,
        environment="dev",
        project_scopes=("WRD",),
    )


@pytest.mark.unit
def test_signed_internal_context_contains_verified_claims_but_no_raw_api_key() -> None:
    signer = InternalContextSigner(SECRET, lifetime=timedelta(seconds=60))

    token = signer.sign(principal(), correlation_id="corr-internal", now=NOW)
    verified = signer.verify(
        token,
        expected_environment="dev",
        required_project="WRD",
        required_roles={ApplicationRole.ADMINISTRATOR},
        now=NOW + timedelta(seconds=1),
    )

    assert verified.actor_id == "admin-001"
    assert verified.correlation_id == "corr-internal"
    assert "wrk_dev_" not in token
    assert "Bearer" not in token


@pytest.mark.unit
def test_missing_tampered_expired_and_cross_environment_contexts_fail() -> None:
    signer = InternalContextSigner(SECRET, lifetime=timedelta(seconds=10))
    token = signer.sign(principal(), correlation_id="corr-internal", now=NOW)

    for invalid in (None, "", f"{token[:-1]}x"):
        with pytest.raises(InternalAuthorizationError):
            signer.verify(
                invalid,
                expected_environment="dev",
                required_project="WRD",
                required_roles={ApplicationRole.ADMINISTRATOR},
                now=NOW,
            )
    with pytest.raises(InternalAuthorizationError, match="expired"):
        signer.verify(
            token,
            expected_environment="dev",
            required_project="WRD",
            required_roles={ApplicationRole.ADMINISTRATOR},
            now=NOW + timedelta(seconds=11),
        )
    with pytest.raises(InternalAuthorizationError, match="environment"):
        signer.verify(
            token,
            expected_environment="prod",
            required_project="WRD",
            required_roles={ApplicationRole.ADMINISTRATOR},
            now=NOW,
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_signed_context_crosses_real_streamable_http_transport() -> None:
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://workforce:workforce-local-only@127.0.0.1:5432/workforce",
    )
    database = Database(database_url)
    profile_id = uuid.uuid4()
    process: asyncio.subprocess.Process | None = None
    try:
        async with database.transaction() as session:
            await session.execute(
                delete(EmployeeProfile).where(
                    EmployeeProfile.environment == "test",
                    EmployeeProfile.employee_id == "EMP-007",
                )
            )
            session.add(
                EmployeeProfile(
                    id=profile_id,
                    environment="test",
                    created_at=NOW,
                    employee_id="EMP-007",
                    role="Synthetic Engineer",
                    seniority="mid",
                    weekly_capacity_hours=40,
                    mentoring_available=False,
                    version=1,
                )
            )
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        environment = {
            **os.environ,
            "APP_ENVIRONMENT": "test",
            "WORKFORCE_MCP_PORT": str(port),
            "DATABASE_URL": database_url,
            "INTERNAL_AUTH_SECRET": SECRET.decode(),
        }
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "workforce_risk_mcp.server",
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        client = StreamableHttpProfileClient(
            url=f"http://127.0.0.1:{port}/mcp", secret=SECRET
        )
        result = None
        for _ in range(30):
            try:
                result = await client.update_capacity(
                    employee_id="EMP-007",
                    project_key="WRD",
                    expected_version=1,
                    weekly_capacity_hours=36,
                    principal=principal().model_copy(update={"environment": "test"}),
                    correlation_id="corr-real-profile-transport",
                )
                break
            except Exception as exc:
                if process.returncode is not None:
                    raise AssertionError("Workforce MCP process stopped") from exc
                await asyncio.sleep(0.1)
        assert result is not None
        assert result["version"] == 2
        assert result["correlation_id"] == "corr-real-profile-transport"
    finally:
        if process is not None:
            process.terminate()
            await process.wait()
        await database.close()
