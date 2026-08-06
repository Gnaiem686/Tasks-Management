from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from agent_api.auth.internal_context import (
    InternalAuthorizationError,
    InternalContextSigner,
)
from agent_api.auth.principal import AuthenticatedPrincipal
from agent_api.auth.roles import ApplicationRole

NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)
SECRET = b"internal-context-test-secret-at-least-32-bytes"


def principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        actor_id="admin-001",
        display_label="Synthetic Administrator",
        role=ApplicationRole.ADMINISTRATOR,
        environment="dev",
        project_scopes=("WRD",),
    )


@pytest.mark.unit
def test_signed_internal_context_contains_verified_claims_but_no_raw_api_key() -> None:
    signer = InternalContextSigner(SECRET, lifetime=timedelta(seconds=60))

    token = signer.sign(principal(), correlation_id="corr-internal", now=NOW)
    verified = signer.verify(
        token,
        expected_environment="dev",
        required_project="WRD",
        required_roles={ApplicationRole.ADMINISTRATOR},
        now=NOW + timedelta(seconds=1),
    )

    assert verified.actor_id == "admin-001"
    assert verified.correlation_id == "corr-internal"
    assert "wrk_dev_" not in token
    assert "Bearer" not in token


@pytest.mark.unit
def test_missing_tampered_expired_and_cross_environment_contexts_fail() -> None:
    signer = InternalContextSigner(SECRET, lifetime=timedelta(seconds=10))
    token = signer.sign(principal(), correlation_id="corr-internal", now=NOW)

    for invalid in (None, "", f"{token[:-1]}x"):
        with pytest.raises(InternalAuthorizationError):
            signer.verify(
                invalid,
                expected_environment="dev",
                required_project="WRD",
                required_roles={ApplicationRole.ADMINISTRATOR},
                now=NOW,
            )
    with pytest.raises(InternalAuthorizationError, match="expired"):
        signer.verify(
            token,
            expected_environment="dev",
            required_project="WRD",
            required_roles={ApplicationRole.ADMINISTRATOR},
            now=NOW + timedelta(seconds=11),
        )
    with pytest.raises(InternalAuthorizationError, match="environment"):
        signer.verify(
            token,
            expected_environment="prod",
            required_project="WRD",
            required_roles={ApplicationRole.ADMINISTRATOR},
            now=NOW,
        )
