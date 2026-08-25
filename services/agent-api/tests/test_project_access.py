from __future__ import annotations

import pytest
from agent_api.project_access import (
    ProjectAccessDenied,
    anonymous_read_principal,
    configured_projects,
    require_configured_project,
)


def test_configured_projects_parse_safe_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ALLOWED_JIRA_PROJECTS",
        "WFD:Workforce Real Data,WRD:Workforce Risk Demo",
    )

    projects = configured_projects()

    assert [(item.key, item.name) for item in projects] == [
        ("WFD", "Workforce Real Data"),
        ("WRD", "Workforce Risk Demo"),
    ]
    assert all(not item.mutation_enabled for item in projects)


def test_unknown_project_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_JIRA_PROJECTS", "WFD:Workforce Real Data")

    with pytest.raises(ProjectAccessDenied):
        require_configured_project("OTHER")


def test_anonymous_principal_is_read_only_and_project_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOWED_JIRA_PROJECTS", "WFD:Workforce Real Data")
    monkeypatch.setenv("ALLOW_ANONYMOUS_READ", "true")
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")

    principal = anonymous_read_principal("WFD")

    assert principal.actor_id == "anonymous-demo-viewer"
    assert principal.role.value == "viewer"
    assert principal.project_scopes == ("WFD",)


def test_anonymous_principal_requires_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOWED_JIRA_PROJECTS", "WFD:Workforce Real Data")
    monkeypatch.delenv("ALLOW_ANONYMOUS_READ", raising=False)

    with pytest.raises(ProjectAccessDenied, match="disabled"):
        anonymous_read_principal("WFD")
