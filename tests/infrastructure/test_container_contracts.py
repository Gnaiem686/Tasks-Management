from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
SERVICES = (
    "agent-api",
    "workforce-risk-mcp",
    "devops-mcp",
    "notification-worker",
)


def dockerfile(service: str) -> str:
    return (ROOT / "services" / service / "Dockerfile").read_text()


def test_every_workload_uses_pinned_multistage_non_root_image() -> None:
    for service in SERVICES:
        text = dockerfile(service)
        from_lines = [line for line in text.splitlines() if line.startswith("FROM ")]
        assert len(from_lines) >= 2
        assert all("@sha256:" in line for line in from_lines)
        assert re.search(r"^USER 10001:10001$", text, re.MULTILINE)
        assert "HEALTHCHECK" in text
        assert "STOPSIGNAL SIGTERM" in text
        assert "org.opencontainers.image.source" in text
        assert "COPY .env" not in text


def test_agent_image_packages_the_tested_ui_assets() -> None:
    text = dockerfile("agent-api")

    assert "services/agent-api/src/agent_api/web" in text
    assert "scripts/validation/verify_ui_assets.py" in text


def test_workforce_mcp_image_packages_database_migrations() -> None:
    text = dockerfile("workforce-risk-mcp")

    assert "packages/persistence/alembic.ini" in text
    assert "packages/persistence/migrations" in text


def test_compose_runs_complete_local_stack_with_safe_runtime_boundaries() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    services = compose["services"]

    assert {
        "postgres",
        "localstack",
        "workforce-risk-mcp",
        "devops-mcp",
        "notification-worker",
        "agent-api",
    } <= services.keys()
    for name in SERVICES:
        config = services[name]
        assert config["read_only"] is True
        assert config["init"] is True
        assert config["restart"] == "unless-stopped"
        assert config["tmpfs"]
        assert "healthcheck" in config
        assert "secrets" not in config
    assert (
        services["agent-api"]["depends_on"]["workforce-risk-mcp"]["condition"]
        == "service_healthy"
    )
    assert (
        services["workforce-risk-mcp"]["depends_on"]["postgres"]["condition"]
        == "service_healthy"
    )


def test_compose_does_not_embed_production_credentials_or_jira_tokens() -> None:
    text = (ROOT / "compose.yaml").read_text().lower()

    for forbidden in (
        "atlassian_mcp_token=",
        "jira_api_token=",
        "aws_secret_access_key=",
        "prod_database_url=",
    ):
        assert forbidden not in text
    assert "app_environment: dev" in text
