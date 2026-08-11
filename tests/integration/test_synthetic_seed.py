from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.jira.mcp_scenario import (
    RovoScenarioSeeder,
    RovoScenarioVerifier,
    linked_issue_pairs,
)
from scripts.jira.profile_seed import seed_profiles
from scripts.jira.runner import ScenarioCoordinator, ScenarioMetadataError
from scripts.jira.scenario import InMemoryScenarioStore, ScenarioDefinition
from scripts.scenario.evaluate_results import evaluate_agent_result

FIXTURE = Path("tests/fixtures/scenarios/seven_employee_team.json")


def load_scenario() -> ScenarioDefinition:
    return ScenarioDefinition.model_validate_json(FIXTURE.read_text())


def test_fixture_defines_complete_seven_employee_team() -> None:
    scenario = load_scenario()

    assert scenario.project_key == "WRD"
    assert {profile.employee_id for profile in scenario.profiles} == {
        f"EMP-{number:03d}" for number in range(1, 8)
    }
    mapped_profiles = [
        profile for profile in scenario.profiles if profile.jira_account_ref is not None
    ]
    assert len(mapped_profiles) == 2
    assert all(
        profile.skills and profile.capacity_hours > 0 for profile in scenario.profiles
    )
    assert {step.name for step in scenario.steps} == {
        "balanced",
        "overload_and_blocker",
        "weak_fit",
        "paired_fit",
        "overloaded_candidate",
        "insufficient_data",
        "stale_proposal",
        "primary_demo",
        "backup_demo",
    }


def test_seed_and_scenario_advance_are_idempotent() -> None:
    scenario = load_scenario()
    store = InMemoryScenarioStore()

    first_seed = store.seed(scenario)
    second_seed = store.seed(scenario)
    first_advance = store.advance(scenario, "overload_and_blocker")
    second_advance = store.advance(scenario, "overload_and_blocker")

    assert first_seed.created == len(scenario.issues)
    assert second_seed.created == 0
    assert second_seed.unchanged == len(scenario.issues)
    assert first_advance.changed > 0
    assert second_advance.changed == 0
    assert store.current_step == "overload_and_blocker"


def test_general_issues_use_workforce_ids_and_write_fixture_uses_accounts() -> None:
    raw = json.loads(FIXTURE.read_text())

    for issue in raw["issues"]:
        workforce_labels = [
            label
            for label in issue["labels"]
            if label.startswith("workforce-employee:")
        ]
        assert workforce_labels == [
            f"workforce-employee:{issue['workforce_employee_id']}"
        ]
    assert all("jira_account_ref" not in issue for issue in raw["issues"])
    assert raw["controlled_write_fixture"] == {
        "issue_external_id": "primary-risk-task",
        "current_account_ref": "current_assignee",
        "target_account_ref": "target_assignee",
    }


def test_coordinator_validates_required_jira_fields_before_seeding() -> None:
    scenario = load_scenario()
    store = InMemoryScenarioStore()
    coordinator = ScenarioCoordinator(store)

    with pytest.raises(ScenarioMetadataError, match="Labels"):
        coordinator.seed(
            scenario,
            available_fields={"Blocker Category": "customfield_10042"},
        )


def test_coordinator_verifies_seed_and_removes_only_owned_records() -> None:
    scenario = load_scenario()
    store = InMemoryScenarioStore()
    coordinator = ScenarioCoordinator(store)
    fields = {
        "Blocker Category": "customfield_10042",
        "Labels": "labels",
    }

    coordinator.seed(scenario, available_fields=fields)
    assert coordinator.verify(scenario).valid is True
    store.issues["unrelated"] = {"labels": ["manual"]}

    result = coordinator.cleanup(scenario)

    assert result.deleted == len(scenario.issues)
    assert store.issues == {"unrelated": {"labels": ["manual"]}}


def test_command_workflow_seeds_advances_verifies_and_resets(tmp_path: Path) -> None:
    state = tmp_path / "scenario-state.json"
    common = [
        "--scenario",
        str(FIXTURE),
        "--state-file",
        str(state),
    ]

    seed = subprocess.run(
        [sys.executable, "scripts/jira/seed_dev.py", *common],
        check=True,
        capture_output=True,
        text=True,
    )
    advance = subprocess.run(
        [
            sys.executable,
            "scripts/jira/advance_scenario.py",
            *common,
            "--step",
            "overload_and_blocker",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    reset = subprocess.run(
        [sys.executable, "scripts/jira/reset_dev.py", *common],
        check=True,
        capture_output=True,
        text=True,
    )
    verify = subprocess.run(
        [sys.executable, "scripts/jira/verify_seed.py", *common],
        check=True,
        capture_output=True,
        text=True,
    )

    assert '"created": 8' in seed.stdout
    assert '"changed": 2' in advance.stdout
    assert '"current_step": "balanced"' in reset.stdout
    assert '"valid": true' in verify.stdout


def test_evaluator_compares_observed_findings_without_sending_expectations() -> None:
    scenario = load_scenario()
    request, result = evaluate_agent_result(
        scenario,
        step_name="overload_and_blocker",
        agent_result={
            "findings": ["employee_overload", "blocked_work"],
            "scores": [{"score": 82, "confidence": "high"}],
            "evidence_references": ["WRD-1"],
        },
    )

    assert request == {"project_key": "WRD", "scenario_step": "overload_and_blocker"}
    assert "expected_findings" not in request
    assert result.passed is True
    assert result.missing_findings == ()


@pytest.mark.asyncio
async def test_real_mcp_seeder_uses_search_then_create_without_rest() -> None:
    scenario = load_scenario()

    class RecordingTransport:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        async def call_tool(
            self,
            name: str,
            arguments: dict[str, object],
            *,
            correlation_id: str,
        ) -> dict[str, object]:
            self.calls.append((name, arguments))
            if name == "searchJiraIssuesUsingJql":
                return {"issues": []}
            if name == "createJiraIssue":
                return {"key": f"WRD-{len(self.calls)}"}
            return {"status": "ok"}

    transport = RecordingTransport()
    result = await RovoScenarioSeeder(transport).seed(
        scenario,
        correlation_id="scenario-test",
        blocker_field_id="customfield_10042",
    )

    assert result.created == len(scenario.issues)
    assert {name for name, _ in transport.calls} <= {
        "searchJiraIssuesUsingJql",
        "createJiraIssue",
        "createIssueLink",
    }
    first_create = next(
        args for name, args in transport.calls if name == "createJiraIssue"
    )
    fields = first_create["additional_fields"]
    assert isinstance(fields, dict)
    assert "workforce-employee:EMP-001" in fields["labels"]
    assert fields["customfield_10042"] is None


@pytest.mark.asyncio
async def test_mcp_verifier_fails_when_owned_issue_is_missing() -> None:
    scenario = load_scenario()

    class EmptyTransport:
        async def call_tool(
            self,
            name: str,
            arguments: dict[str, object],
            *,
            correlation_id: str,
        ) -> dict[str, object]:
            return {"issues": []}

    result = await RovoScenarioVerifier(EmptyTransport()).verify(
        scenario,
        correlation_id="verify-test",
        blocker_field_id="customfield_10042",
    )

    assert result.valid is False
    assert result.missing_external_ids == tuple(
        sorted(issue.external_id for issue in scenario.issues)
    )


@pytest.mark.asyncio
async def test_profile_seed_is_idempotent_and_maps_exactly_two_accounts() -> None:
    scenario = load_scenario()

    class FakeProfiles:
        def __init__(self) -> None:
            self.records: dict[str, dict[str, object]] = {}

        async def get(self, *, environment: str, employee_id: str) -> object | None:
            return self.records.get(employee_id)

        async def create(self, **values: object) -> object:
            self.records[str(values["employee_id"])] = values
            return values

    repository = FakeProfiles()
    mappings = {
        "current_assignee": "synthetic-account-current",
        "target_assignee": "synthetic-account-target",
    }

    first = await seed_profiles(repository, scenario, account_ids=mappings)
    second = await seed_profiles(repository, scenario, account_ids=mappings)

    assert first.created == 7
    assert second.created == 0
    assert second.unchanged == 7
    stored_accounts = {
        record["jira_account_id"] for record in repository.records.values()
    }
    assert stored_accounts == {
        None,
        "synthetic-account-current",
        "synthetic-account-target",
    }


def test_existing_dependency_links_are_normalized_for_idempotency() -> None:
    issue = {
        "key": "WRD-2",
        "fields": {
            "issuelinks": [
                {
                    "type": {"name": "Blocks"},
                    "inwardIssue": {"key": "WRD-3"},
                }
            ]
        },
    }

    assert linked_issue_pairs(issue) == {frozenset({"WRD-2", "WRD-3"})}
