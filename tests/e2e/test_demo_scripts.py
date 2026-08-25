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
    assert "deployed Agent API" in content
    assert "answer source" in content


def test_automatic_demo_advances_ordered_verified_stages_safely() -> None:
    content = script("auto_demo.sh")
    positions = [
        content.index(stage)
        for stage in (
            "balanced",
            "stalled",
            "blocked",
            "critical",
            "intervention",
            "recovery",
        )
    ]
    assert positions == sorted(positions)
    assert "DEMO_STAGE_SECONDS:-60" in content
    assert "readiness.sh" in content
    assert "advance_scenario.py" in content
    assert "verify_seed.py" in content
    assert "/api/v1/scans?project_key=WRD" in content
    assert 'run_scan "${stage}"' in content
    assert "--live-mcp" in content
    assert "trap" in content
    assert "INT TERM" in content
    assert "set -euo pipefail" in content
    assert "Scan failed" in content
    assert "correlation" in content
    assert "Scan timed out" in content
