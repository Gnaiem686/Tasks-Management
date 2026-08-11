from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from agent_api.auth.api_keys import ApiKeyService
from agent_api.auth.roles import ApplicationRole
from workforce_persistence.database import Database
from workforce_persistence.models import ApiKeyPrincipal

from tests.integration.processes import (
    ProcessGroup,
    allocate_port,
    start_python_process,
)

ROOT = Path(__file__).parents[2]
DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://workforce:workforce-local-only@127.0.0.1:5432/workforce",
)
PEPPER = "integration-pepper-value-at-least-32-bytes"


async def create_test_key() -> str:
    now = datetime.now(UTC)
    raw, record = ApiKeyService(PEPPER.encode()).generate(
        actor_id=f"transport-viewer-{uuid.uuid4()}",
        display_label="Transport viewer",
        role=ApplicationRole.VIEWER,
        environment="dev",
        project_scopes=("WRD",),
        now=now,
        expires_at=now + timedelta(minutes=10),
    )
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            session.add(
                ApiKeyPrincipal(
                    id=uuid.uuid4(),
                    environment="dev",
                    created_at=now,
                    actor_id=record.actor_id,
                    display_label=record.display_label,
                    key_digest=record.key_digest,
                    role=record.role.value,
                    project_scopes=["WRD"],
                    expires_at=record.expires_at,
                )
            )
    finally:
        await database.close()
    return raw


@pytest.mark.integration
def test_agent_api_calls_separate_workforce_mcp_over_streamable_http() -> None:
    api_key = asyncio.run(create_test_key())
    workforce_port = allocate_port()
    agent_port = allocate_port()
    with ProcessGroup() as processes:
        workforce = processes.add(
            start_python_process(
                name="workforce-risk-mcp",
                port=workforce_port,
                module="workforce_risk_mcp.server",
                root=ROOT,
                environment={
                    "WORKFORCE_MCP_HOST": "127.0.0.1",
                    "WORKFORCE_MCP_PORT": str(workforce_port),
                    "APP_ENVIRONMENT": "dev",
                    "SCORING_CONFIG_PATH": str(ROOT / "config/scoring/v1.yaml"),
                },
            )
        )
        agent = processes.add(
            start_python_process(
                name="agent-api",
                port=agent_port,
                module="uvicorn",
                root=ROOT,
                arguments=(
                    "agent_api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(agent_port),
                ),
                environment={
                    "APP_ENVIRONMENT": "dev",
                    "EVIDENCE_MODE": "fixture",
                    "EVIDENCE_FIXTURE_DIR": str(ROOT / "tests/fixtures/scenarios"),
                    "WORKFORCE_MCP_URL": f"http://127.0.0.1:{workforce_port}/mcp",
                    "DATABASE_URL": DATABASE_URL,
                    "API_KEY_HMAC_PEPPER": PEPPER,
                },
            )
        )
        assert workforce.pid != agent.pid
        assert workforce.port != agent.port
        response = httpx.get(
            f"http://127.0.0.1:{agent_port}/api/v1/employees/EMP-002/overload-risk",
            params={"project_key": "WRD"},
            headers={
                "X-Correlation-ID": "corr-e2e-transport",
                "Authorization": f"Bearer {api_key}",
            },
            timeout=10,
        )

        assert response.status_code == 200, response.text
        assert response.headers["X-Correlation-ID"] == "corr-e2e-transport"
        payload = response.json()
        assert payload["schema_version"] == "1.0"
        assert payload["correlation_id"] == "corr-e2e-transport"
        assert payload["result"]["score"] == 88
        assert payload["result"]["level"] == "critical"
        assert payload["result"]["confidence"] == "high"
        assert payload["result"]["factors"]
        assert payload["result"]["evidence_references"]
        assert payload["result"]["scoring_model_version"] == "employee-overload-v1"
        transport_proof = {
            "agent_pid": agent.pid,
            "agent_port": agent.port,
            "workforce_mcp_pid": workforce.pid,
            "workforce_mcp_port": workforce.port,
            "transport": "streamable-http",
        }
        assert json.dumps(transport_proof)
