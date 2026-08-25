from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from workforce_contracts.auth import AuthenticatedPrincipal, InternalContextSigner
from workforce_risk_mcp.tools.proposals import (
    ProposalDecisionRequest,
    authorize_proposal,
)

SECRET = b"proposal-internal-secret-material-32-bytes"
NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


def token(
    role: str = "manager", environment: str = "test", scopes: tuple[str, ...] = ("WRD",)
) -> str:
    principal = AuthenticatedPrincipal.model_validate(
        {
            "actor_id": "verified-manager",
            "display_label": "Manager",
            "role": role,
            "environment": environment,
            "project_scopes": scopes,
        }
    )
    return InternalContextSigner(SECRET, lifetime=timedelta(seconds=60)).sign(
        principal, correlation_id="corr-protected", now=NOW
    )


@pytest.mark.security
def test_protected_tool_rejects_missing_viewer_cross_environment_and_scope() -> None:
    for supplied in (
        None,
        token("viewer"),
        token(environment="dev"),
        token(scopes=("OTHER",)),
    ):
        with pytest.raises(PermissionError):
            authorize_proposal(
                transport_context=supplied,
                secret=SECRET,
                environment="test",
                project_key="WRD",
                now=NOW,
            )


@pytest.mark.security
def test_decision_schema_rejects_forged_actor_and_fingerprint_fields() -> None:
    with pytest.raises(ValidationError):
        ProposalDecisionRequest.model_validate(
            {
                "project_key": "WRD",
                "proposal_id": "proposal-1",
                "expected_version": 1,
                "decision": "approve",
                "idempotency_key": "approve-key-1",
                "decided_at": NOW,
                "actor_id": "forged-admin",
                "current_evidence_fingerprint": "a" * 64,
            }
        )
    verified = authorize_proposal(
        transport_context=token(),
        secret=SECRET,
        environment="test",
        project_key="WRD",
        now=NOW,
    )
    assert verified.actor_id == "verified-manager"
    assert "wrk_" not in verified.model_dump_json()
