from __future__ import annotations

from copy import deepcopy
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from scripts.jira.guards import validate_scenario_scope
from scripts.jira.scenario import OperationResult, ScenarioDefinition


class ScenarioMetadataError(ValueError):
    pass


class ScenarioStore(Protocol):
    issues: dict[str, dict[str, object]]

    def seed(self, scenario: ScenarioDefinition) -> OperationResult: ...

    def advance(
        self, scenario: ScenarioDefinition, step_name: str
    ) -> OperationResult: ...

    def cleanup(self, scenario: ScenarioDefinition) -> OperationResult: ...


class VerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    valid: bool
    missing_external_ids: tuple[str, ...] = ()
    mismatched_external_ids: tuple[str, ...] = ()


class ScenarioCoordinator:
    REQUIRED_FIELDS = frozenset({"Blocker Category", "Labels"})

    def __init__(self, store: ScenarioStore) -> None:
        self._store = store

    def seed(
        self,
        scenario: ScenarioDefinition,
        *,
        available_fields: dict[str, str],
    ) -> OperationResult:
        self._guard(scenario)
        missing = sorted(self.REQUIRED_FIELDS - available_fields.keys())
        if missing:
            raise ScenarioMetadataError(
                "required Jira field is unavailable: " + ", ".join(missing)
            )
        return self._store.seed(scenario)

    def verify(self, scenario: ScenarioDefinition) -> VerificationResult:
        self._guard(scenario)
        missing: list[str] = []
        mismatched: list[str] = []
        for expected in scenario.issues:
            actual = self._store.issues.get(expected.external_id)
            desired = expected.model_dump(mode="json")
            current_step = getattr(self._store, "current_step", None)
            step = next(
                (item for item in scenario.steps if item.name == current_step), None
            )
            if step is not None:
                desired = deepcopy(desired)
                desired.update(step.issue_updates.get(expected.external_id, {}))
            if actual is None:
                missing.append(expected.external_id)
            elif actual != desired:
                mismatched.append(expected.external_id)
        return VerificationResult(
            valid=not missing and not mismatched,
            missing_external_ids=tuple(sorted(missing)),
            mismatched_external_ids=tuple(sorted(mismatched)),
        )

    def advance(self, scenario: ScenarioDefinition, step_name: str) -> OperationResult:
        self._guard(scenario)
        return self._store.advance(scenario, step_name)

    def cleanup(self, scenario: ScenarioDefinition) -> OperationResult:
        self._guard(scenario)
        return self._store.cleanup(scenario)

    @staticmethod
    def _guard(scenario: ScenarioDefinition) -> None:
        validate_scenario_scope(
            environment=scenario.environment,
            project_key=scenario.project_key,
        )
