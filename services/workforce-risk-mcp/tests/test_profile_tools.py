from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from workforce_contracts.auth import (
    ApplicationRole,
    AuthenticatedPrincipal,
    InternalContextSigner,
)
from workforce_risk_mcp.tools.profiles import (
    ProfileCapacityUpdate,
    ProfileToolAuthorizationError,
    authorize_profile_change,
)

NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)
SECRET = b"profile-tool-test-secret-at-least-32-bytes"


def signed_context(role: ApplicationRole = ApplicationRole.ADMINISTRATOR) -> str:
    return InternalContextSigner(SECRET, lifetime=timedelta(seconds=60)).sign(
        AuthenticatedPrincipal(
            actor_id="synthetic-admin",
            display_label="Synthetic Administrator",
            role=role,
            environment="dev",
            project_scopes=("WRD",),
        ),
        correlation_id="corr-profile-tool",
        now=NOW,
    )


@pytest.mark.unit
def test_profile_change_uses_verified_transport_context() -> None:
    request = ProfileCapacityUpdate(
        employee_id="EMP-001",
        project_key="WRD",
        expected_version=1,
        weekly_capacity_hours=32,
    )

    context = authorize_profile_change(
        request,
        transport_context=signed_context(),
        secret=SECRET,
        environment="dev",
        now=NOW,
    )

    assert context.actor_id == "synthetic-admin"
    assert context.correlation_id == "corr-profile-tool"
    assert "actor_id" not in request.model_fields_set


@pytest.mark.unit
@pytest.mark.parametrize(
    "token",
    [None, "", "malformed"],
)
def test_profile_change_rejects_missing_or_malformed_transport_context(
    token: str | None,
) -> None:
    request = ProfileCapacityUpdate(
        employee_id="EMP-001",
        project_key="WRD",
        expected_version=1,
        weekly_capacity_hours=32,
    )

    with pytest.raises(ProfileToolAuthorizationError):
        authorize_profile_change(
            request,
            transport_context=token,
            secret=SECRET,
            environment="dev",
            now=NOW,
        )


@pytest.mark.unit
def test_profile_change_rejects_manager_role_and_cross_environment() -> None:
    request = ProfileCapacityUpdate(
        employee_id="EMP-001",
        project_key="WRD",
        expected_version=1,
        weekly_capacity_hours=32,
    )
    with pytest.raises(ProfileToolAuthorizationError):
        authorize_profile_change(
            request,
            transport_context=signed_context(ApplicationRole.MANAGER),
            secret=SECRET,
            environment="dev",
            now=NOW,
        )
    with pytest.raises(ProfileToolAuthorizationError):
        authorize_profile_change(
            request,
            transport_context=signed_context(),
            secret=SECRET,
            environment="prod",
            now=NOW,
        )
