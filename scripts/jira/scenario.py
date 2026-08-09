from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScenarioProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_id: str = Field(pattern=r"^EMP-00[1-7]$")
    role: str
    seniority: str
    skills: dict[str, int]
    capacity_hours: float = Field(gt=0)
    allocation: float = Field(gt=0, le=1)
    mentoring_available: bool
    jira_account_ref: str | None = None


class ScenarioIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    external_id: str
    summary: str
    workforce_employee_id: str = Field(pattern=r"^EMP-00[1-7]$")
    estimate_hours: float = Field(gt=0)
    remaining_hours: float = Field(ge=0)
    due_offset_days: int
    priority: str
    difficulty: int = Field(ge=1, le=5)
    required_skills: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    blocker_category: str | None = None
    senior_pairing_employee_id: str | None = Field(
        default=None, pattern=r"^EMP-00[1-7]$"
    )
    evidence_complete: bool = True
    labels: tuple[str, ...]


class ScenarioStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    issue_updates: dict[str, dict[str, object]] = Field(default_factory=dict)
    expected_findings: tuple[str, ...]


class ControlledWriteFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    issue_external_id: str
    current_account_ref: str
    target_account_ref: str


class ScenarioDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str
    scenario_id: str
    ownership_tag: str
    environment: str
    project_key: str
    anchor_date: date
    profiles: tuple[ScenarioProfile, ...]
    issues: tuple[ScenarioIssue, ...]
    steps: tuple[ScenarioStep, ...]
    controlled_write_fixture: ControlledWriteFixture

    @model_validator(mode="after")
    def validate_contract(self) -> ScenarioDefinition:
        expected = {f"EMP-{number:03d}" for number in range(1, 8)}
        if {profile.employee_id for profile in self.profiles} != expected:
            raise ValueError("profiles must contain exactly EMP-001 through EMP-007")
        if sum(profile.jira_account_ref is not None for profile in self.profiles) != 2:
            raise ValueError("exactly two profiles must have Jira account references")
        issue_ids = {issue.external_id for issue in self.issues}
        if len(issue_ids) != len(self.issues):
            raise ValueError("issue external IDs must be unique")
        if any(self.ownership_tag not in issue.labels for issue in self.issues):
            raise ValueError("every issue must carry the scenario ownership tag")
        for issue in self.issues:
            workforce_labels = tuple(
                label
                for label in issue.labels
                if label.startswith("workforce-employee:")
            )
            expected_label = f"workforce-employee:{issue.workforce_employee_id}"
            if workforce_labels != (expected_label,):
                raise ValueError(
                    "every issue must carry exactly its expected workforce label"
                )
        return self


class OperationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    created: int = 0
    changed: int = 0
    unchanged: int = 0
    deleted: int = 0


class InMemoryScenarioStore:
    """Deterministic adapter used to prove lifecycle behavior without a network."""

    def __init__(self) -> None:
        self.issues: dict[str, dict[str, object]] = {}
        self.current_step: str | None = None

    def seed(self, scenario: ScenarioDefinition) -> OperationResult:
        created = 0
        unchanged = 0
        for issue in scenario.issues:
            desired = issue.model_dump(mode="json")
            current = self.issues.get(issue.external_id)
            if current == desired:
                unchanged += 1
            else:
                if current is None:
                    created += 1
                self.issues[issue.external_id] = deepcopy(desired)
        return OperationResult(created=created, unchanged=unchanged)

    def advance(self, scenario: ScenarioDefinition, step_name: str) -> OperationResult:
        step = next((item for item in scenario.steps if item.name == step_name), None)
        if step is None:
            raise ValueError(f"unknown scenario step: {step_name}")
        changed = 0
        for external_id, updates in step.issue_updates.items():
            issue = self.issues.get(external_id)
            if issue is None:
                raise ValueError(f"scenario issue is not seeded: {external_id}")
            for field, value in updates.items():
                if issue.get(field) != value:
                    issue[field] = deepcopy(value)
                    changed += 1
        self.current_step = step_name
        return OperationResult(changed=changed)

    def cleanup(self, scenario: ScenarioDefinition) -> OperationResult:
        owned = [
            key
            for key, issue in self.issues.items()
            if _has_label(issue, scenario.ownership_tag)
        ]
        for key in owned:
            del self.issues[key]
        self.current_step = None
        return OperationResult(deleted=len(owned))


class FileScenarioStore(InMemoryScenarioStore):
    """Persistent deterministic adapter for CLI tests and offline rehearsal."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        if path.exists():
            raw = json.loads(path.read_text())
            self.issues = raw.get("issues", {})
            self.current_step = raw.get("current_step")

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"issues": self.issues, "current_step": self.current_step},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    def seed(self, scenario: ScenarioDefinition) -> OperationResult:
        result = super().seed(scenario)
        self._save()
        return result

    def advance(self, scenario: ScenarioDefinition, step_name: str) -> OperationResult:
        result = super().advance(scenario, step_name)
        self._save()
        return result

    def cleanup(self, scenario: ScenarioDefinition) -> OperationResult:
        result = super().cleanup(scenario)
        self._save()
        return result


def owned_issue_keys(
    issues: dict[str, dict[str, object]], *, project_key: str, ownership_tag: str
) -> tuple[str, ...]:
    prefix = f"{project_key}-"
    return tuple(
        sorted(
            key
            for key, issue in issues.items()
            if key.startswith(prefix) and _has_label(issue, ownership_tag)
        )
    )


def scenario_at_step(
    scenario: ScenarioDefinition, step_name: str
) -> ScenarioDefinition:
    step = next((item for item in scenario.steps if item.name == step_name), None)
    if step is None:
        raise ValueError(f"unknown scenario step: {step_name}")
    issues = tuple(
        issue.model_copy(update=step.issue_updates.get(issue.external_id, {}))
        for issue in scenario.issues
    )
    return scenario.model_copy(update={"issues": issues})


def _has_label(issue: dict[str, object], label: str) -> bool:
    labels = issue.get("labels")
    return isinstance(labels, (list, tuple)) and label in labels
