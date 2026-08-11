from datetime import UTC, datetime

from workforce_persistence.bootstrap import build_initial_principal


def test_initial_manager_principal_is_scoped_and_never_stores_raw_key() -> None:
    raw_key = "wrk_dev_example-bootstrap-key"
    principal = build_initial_principal(
        raw_key=raw_key,
        pepper="p" * 48,
        environment="dev",
        project_key="WRD",
        now=datetime(2026, 8, 11, tzinfo=UTC),
    )

    assert principal.environment == "dev"
    assert principal.role == "manager"
    assert principal.project_scopes == ["WRD"]
    assert principal.key_digest != raw_key
    assert raw_key not in repr(principal)

