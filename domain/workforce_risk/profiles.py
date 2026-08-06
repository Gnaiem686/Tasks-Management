from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Seniority(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


class SkillProficiency(IntEnum):
    AWARE = 1
    BEGINNER = 2
    INTERMEDIATE = 3
    ADVANCED = 4
    EXPERT = 5


class DocumentedSkill(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=128)
    proficiency: SkillProficiency


class ProjectAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,63}$")
    fraction: float = Field(gt=0, le=1)


class CapacityOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    capacity_hours: float = Field(ge=0, le=168)
    reason: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_window(self) -> CapacityOverride:
        if self.ends_at <= self.starts_at:
            raise ValueError("capacity override must end after it starts")
        return self


class WorkforceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_id: str = Field(pattern=r"^EMP-00[1-7]$")
    environment: Literal["dev", "prod", "test"]
    role: str = Field(min_length=1, max_length=128)
    seniority: Seniority
    documented_skills: tuple[DocumentedSkill, ...]
    weekly_capacity_hours: float = Field(gt=0, le=168)
    project_allocations: tuple[ProjectAllocation, ...]
    mentoring_available: bool
    capacity_overrides: tuple[CapacityOverride, ...] = ()
    jira_account_id: str | None = Field(default=None, min_length=1, max_length=256)
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_profile(self) -> WorkforceProfile:
        skill_names = [skill.name.casefold() for skill in self.documented_skills]
        if len(skill_names) != len(set(skill_names)):
            raise ValueError("documented skills must be unique")
        project_keys = [item.project_key for item in self.project_allocations]
        if len(project_keys) != len(set(project_keys)):
            raise ValueError("project allocations must be unique")
        if sum(item.fraction for item in self.project_allocations) > 1 + 1e-9:
            raise ValueError("project allocations must not exceed 1.0")
        windows = sorted(self.capacity_overrides, key=lambda item: item.starts_at)
        for previous, current in zip(windows, windows[1:], strict=False):
            if current.starts_at < previous.ends_at:
                raise ValueError("capacity override windows must not overlap")
        return self

    def effective_capacity(self, at: datetime) -> float:
        for override in self.capacity_overrides:
            if override.starts_at <= at < override.ends_at:
                return override.capacity_hours
        return self.weekly_capacity_hours


def validate_profile_set(
    profiles: list[WorkforceProfile],
    *,
    environment: Literal["dev", "prod", "test"],
    jira_mapping_employee_ids: set[str],
) -> None:
    expected_ids = {f"EMP-{number:03d}" for number in range(1, 8)}
    employee_ids = [profile.employee_id for profile in profiles]
    if len(profiles) != 7 or set(employee_ids) != expected_ids:
        raise ValueError("profile employee IDs must be exactly seven and unique")
    if any(profile.environment != environment for profile in profiles):
        raise ValueError("profile environment mismatch")
    mapped = [profile for profile in profiles if profile.jira_account_id is not None]
    if any(profile.employee_id not in jira_mapping_employee_ids for profile in mapped):
        raise ValueError("Jira account mapping is not allowed for this employee")
    account_ids = [profile.jira_account_id for profile in mapped]
    if len(account_ids) != len(set(account_ids)):
        raise ValueError("Jira account mappings must be unique")
