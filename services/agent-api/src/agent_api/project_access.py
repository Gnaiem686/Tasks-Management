from __future__ import annotations

import os
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from agent_api.auth.principal import AuthenticatedPrincipal
from agent_api.auth.roles import ApplicationRole


class ProjectAccessDenied(PermissionError):
    pass


class ConfiguredProject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,19}$")
    name: str = Field(min_length=1, max_length=100)
    mutation_enabled: bool = False


def configured_projects() -> tuple[ConfiguredProject, ...]:
    raw = os.getenv(
        "ALLOWED_JIRA_PROJECTS",
        "WFD:Workforce Real Data,WRD:Workforce Risk Demo",
    )
    projects: list[ConfiguredProject] = []
    seen: set[str] = set()
    for entry in raw.split(","):
        key, separator, name = entry.strip().partition(":")
        if not separator or key in seen:
            raise RuntimeError("ALLOWED_JIRA_PROJECTS is invalid")
        seen.add(key)
        projects.append(ConfiguredProject(key=key, name=name.strip()))
    if not projects:
        raise RuntimeError("ALLOWED_JIRA_PROJECTS must not be empty")
    return tuple(projects)


def require_configured_project(project_key: str) -> ConfiguredProject:
    for project in configured_projects():
        if project.key == project_key:
            return project
    raise ProjectAccessDenied("project is not configured")


def anonymous_read_principal(project_key: str) -> AuthenticatedPrincipal:
    require_configured_project(project_key)
    if os.getenv("ALLOW_ANONYMOUS_READ", "false").casefold() != "true":
        raise ProjectAccessDenied("anonymous reads are disabled")
    raw_environment = os.getenv("APP_ENVIRONMENT", "dev")
    if raw_environment not in {"dev", "prod", "test"}:
        raise RuntimeError("APP_ENVIRONMENT must be dev, prod, or test")
    environment = cast(Literal["dev", "prod", "test"], raw_environment)
    return AuthenticatedPrincipal(
        actor_id="anonymous-demo-viewer",
        display_label="Public demo viewer",
        role=ApplicationRole.VIEWER,
        environment=environment,
        project_scopes=(project_key,),
    )
