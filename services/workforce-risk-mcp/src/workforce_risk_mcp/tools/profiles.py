from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from workforce_contracts.auth import (
    ApplicationRole,
    InternalAuthorizationError,
    InternalContextSigner,
    VerifiedInternalContext,
)
from workforce_risk.profiles import (
    CapacityOverride,
    DocumentedSkill,
    ProjectAllocation,
    Seniority,
)


class ProfileToolAuthorizationError(PermissionError):
    pass


class ProfileCapacityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_id: str = Field(pattern=r"^EMP-00[1-7]$")
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,63}$")
    expected_version: int = Field(ge=1)
    weekly_capacity_hours: float = Field(gt=0, le=168)


class ProfileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,63}$")
    employee_id: str = Field(pattern=r"^EMP-00[1-7]$")
    role: str = Field(min_length=1, max_length=128)
    seniority: Seniority
    documented_skills: tuple[DocumentedSkill, ...]
    weekly_capacity_hours: float = Field(gt=0, le=168)
    project_allocations: tuple[ProjectAllocation, ...]
    mentoring_available: bool
    capacity_overrides: tuple[CapacityOverride, ...] = ()
    jira_account_id: str | None = Field(default=None, min_length=1, max_length=256)


def authorize_profile_change(
    request: ProfileCapacityUpdate | ProfileCreateRequest,
    *,
    transport_context: str | None,
    secret: bytes,
    environment: Literal["dev", "prod", "test"],
    now: datetime,
) -> VerifiedInternalContext:
    try:
        return InternalContextSigner(secret, lifetime=timedelta(seconds=1)).verify(
            transport_context,
            expected_environment=environment,
            required_project=request.project_key,
            required_roles={ApplicationRole.ADMINISTRATOR},
            now=now,
        )
    except (InternalAuthorizationError, ValueError) as exc:
        raise ProfileToolAuthorizationError("profile change is not authorized") from exc
