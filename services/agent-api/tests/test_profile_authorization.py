from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from agent_api.auth.api_keys import (
    ApiKeyAuthenticationError,
    ApiKeyRecord,
    ApiKeyService,
)
from agent_api.auth.roles import ApplicationRole

NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)
PEPPER = b"synthetic-test-pepper-at-least-32-bytes"


def active_record(
    service: ApiKeyService, **changes: object
) -> tuple[str, ApiKeyRecord]:
    raw_key, record = service.generate(
        actor_id="manager-001",
        display_label="Synthetic Manager",
        role=ApplicationRole.ADMINISTRATOR,
        environment="dev",
        project_scopes=("WRD",),
        now=NOW,
        expires_at=NOW + timedelta(days=30),
    )
    return raw_key, record.model_copy(update=changes)


@pytest.mark.unit
def test_key_is_shown_once_and_only_hmac_digest_is_stored() -> None:
    service = ApiKeyService(PEPPER)
    raw_key, record = active_record(service)

    assert raw_key.startswith("wrk_dev_")
    assert raw_key not in record.model_dump_json()
    assert record.key_digest != raw_key
    assert len(record.key_digest) == 64


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"expires_at": NOW - timedelta(seconds=1)}, "expired"),
        ({"revoked_at": NOW}, "revoked"),
        ({"environment": "prod"}, "environment"),
        ({"project_scopes": ("OTHER",)}, "project"),
        ({"role": ApplicationRole.VIEWER}, "role"),
    ],
)
def test_invalid_scope_or_state_fails_closed(
    mutation: dict[str, object], message: str
) -> None:
    service = ApiKeyService(PEPPER)
    raw_key, record = active_record(service, **mutation)

    with pytest.raises(ApiKeyAuthenticationError, match=message):
        service.authenticate(
            f"Bearer {raw_key}",
            records=(record,),
            environment="dev",
            project_key="WRD",
            allowed_roles={ApplicationRole.ADMINISTRATOR},
            now=NOW,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic abc", "Bearer", "Bearer malformed", "Bearer unknown-key"],
)
def test_missing_malformed_and_unknown_keys_are_rejected(
    authorization: str | None,
) -> None:
    service = ApiKeyService(PEPPER)
    _, record = active_record(service)

    with pytest.raises(ApiKeyAuthenticationError):
        service.authenticate(
            authorization,
            records=(record,),
            environment="dev",
            project_key="WRD",
            allowed_roles={ApplicationRole.ADMINISTRATOR},
            now=NOW,
        )


@pytest.mark.unit
def test_authenticated_principal_comes_from_record_not_request_identity() -> None:
    service = ApiKeyService(PEPPER)
    raw_key, record = active_record(service)

    principal = service.authenticate(
        f"Bearer {raw_key}",
        records=(record,),
        environment="dev",
        project_key="WRD",
        allowed_roles={ApplicationRole.ADMINISTRATOR},
        now=NOW,
    )

    assert principal.actor_id == "manager-001"
    assert principal.display_label == "Synthetic Manager"
