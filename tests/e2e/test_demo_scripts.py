from pathlib import Path

ROOT = Path(__file__).parents[2]


def script(name: str) -> str:
    return (ROOT / "scripts" / "demo" / name).read_text()


def test_primary_demo_uses_guarded_external_jira_progression_and_scan() -> None:
    content = script("primary.sh")
    assert "advance_scenario.py" in content
    assert "--live-mcp" in content
    assert 'PROJECT_KEY="WRD"' in content
    assert "/api/v1/scans?project_key=${PROJECT_KEY}" in content
    assert "kubectl" not in content


def test_demo_readiness_requires_dev_only_credentials() -> None:
    content = script("readiness.sh")
    assert "ATLASSIAN_MCP_AUTHORIZATION" in content
    assert "DEV_MANAGER_API_KEY" in content
    assert "APP_ENVIRONMENT:-dev" in content
    assert '"prod"' in content
