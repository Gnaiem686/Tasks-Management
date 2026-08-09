from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from scripts.jira.guards import validate_scenario_scope
from scripts.jira.scenario import OperationResult, ScenarioDefinition


class ProfileSeedRepository(Protocol):
    async def get(self, *, environment: str, employee_id: str) -> object | None: ...

    async def create(
        self,
        *,
        environment: str,
        employee_id: str,
        role: str,
        seniority: str,
        weekly_capacity_hours: float,
        mentoring_available: bool,
        jira_account_id: str | None,
        skills: tuple[tuple[str, int], ...],
        allocations: tuple[tuple[str, float], ...],
        capacity_overrides: tuple[tuple[datetime, datetime, float, str], ...],
        actor_id: str,
        correlation_id: str,
        created_at: datetime,
    ) -> object: ...


async def seed_profiles(
    repository: ProfileSeedRepository,
    scenario: ScenarioDefinition,
    *,
    account_ids: dict[str, str],
) -> OperationResult:
    validate_scenario_scope(
        environment=scenario.environment,
        project_key=scenario.project_key,
    )
    required_refs = {
        profile.jira_account_ref
        for profile in scenario.profiles
        if profile.jira_account_ref is not None
    }
    if set(account_ids) != required_refs:
        raise ValueError(
            "exactly the two approved Jira account references are required"
        )
    created = 0
    unchanged = 0
    created_at = datetime.combine(scenario.anchor_date, datetime.min.time(), UTC)
    for profile in scenario.profiles:
        existing = await repository.get(
            environment=scenario.environment,
            employee_id=profile.employee_id,
        )
        if existing is not None:
            unchanged += 1
            continue
        account_id = (
            None
            if profile.jira_account_ref is None
            else account_ids[profile.jira_account_ref]
        )
        await repository.create(
            environment=scenario.environment,
            employee_id=profile.employee_id,
            role=profile.role,
            seniority=profile.seniority,
            weekly_capacity_hours=profile.capacity_hours,
            mentoring_available=profile.mentoring_available,
            jira_account_id=account_id,
            skills=tuple(sorted(profile.skills.items())),
            allocations=((scenario.project_key, profile.allocation),),
            capacity_overrides=(),
            actor_id="scenario-seeder",
            correlation_id=f"scenario-profile-seed-{scenario.scenario_id}",
            created_at=created_at,
        )
        created += 1
    return OperationResult(created=created, unchanged=unchanged)
