from __future__ import annotations

from pathlib import Path


def test_scenario_tooling_is_not_a_langgraph_or_kubernetes_workload() -> None:
    script_text = "\n".join(
        path.read_text()
        for path in sorted(Path("scripts/jira").glob("*.py"))
        + sorted(Path("scripts/scenario").glob("*.py"))
    ).lower()
    manifest_paths = (
        list(Path("deploy").rglob("*simulation*")) if Path("deploy").exists() else []
    )

    assert "langgraph" not in script_text
    assert "kubernetes" not in script_text
    assert manifest_paths == []


def test_scenario_workflow_has_minimal_permissions_and_concurrency() -> None:
    workflow = Path(".github/workflows/run-scenario.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "concurrency:" in workflow
    assert "contents: read" in workflow
    assert "id-token: write" not in workflow
    assert "kubectl" not in workflow
    assert "terraform" not in workflow
