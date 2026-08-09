from __future__ import annotations

import pytest

from scripts.jira.guards import ScenarioScopeError, validate_scenario_scope
from scripts.jira.rest_cleanup import GuardedRestCleanup


def test_only_wrd_dev_scope_is_allowed() -> None:
    validate_scenario_scope(environment="dev", project_key="WRD")

    with pytest.raises(ScenarioScopeError, match="project"):
        validate_scenario_scope(environment="dev", project_key="OTHER")


@pytest.mark.parametrize("environment", ["prod", "production", "test"])
def test_every_non_dev_environment_is_rejected(environment: str) -> None:
    with pytest.raises(ScenarioScopeError, match="environment"):
        validate_scenario_scope(environment=environment, project_key="WRD")


def test_cleanup_requires_matching_ownership_tag() -> None:
    from scripts.jira.scenario import owned_issue_keys

    issues = {
        "WRD-1": {"labels": ["workforce-scenario:seven-person:v1"]},
        "WRD-2": {"labels": ["unrelated"]},
        "OTHER-1": {"labels": ["workforce-scenario:seven-person:v1"]},
    }

    assert owned_issue_keys(
        issues,
        project_key="WRD",
        ownership_tag="workforce-scenario:seven-person:v1",
    ) == ("WRD-1",)


@pytest.mark.asyncio
async def test_live_cleanup_deletes_only_mcp_discovered_owned_wrd_issues() -> None:
    class SearchTransport:
        async def call_tool(
            self,
            name: str,
            arguments: dict[str, object],
            *,
            correlation_id: str,
        ) -> dict[str, object]:
            return {
                "issues": [
                    {
                        "key": "WRD-2",
                        "fields": {
                            "labels": ["workforce-scenario:seven-person:v1"]
                        },
                    }
                ]
            }

    class DeleteClient:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def delete_issue(self, issue_key: str) -> None:
            self.deleted.append(issue_key)

    deletes = DeleteClient()
    result = await GuardedRestCleanup(SearchTransport(), deletes).cleanup(
        environment="dev",
        project_key="WRD",
        ownership_tag="workforce-scenario:seven-person:v1",
        correlation_id="cleanup-test",
    )

    assert result.deleted == 1
    assert deletes.deleted == ["WRD-2"]
