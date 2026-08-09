from pathlib import Path

import pytest
from workforce_contracts.config import (
    ConfigurationError,
    EnvironmentConfig,
    load_environment_config,
    validate_environment_isolation,
)

EMPLOYEE_IDS = [f"EMP-{index:03d}" for index in range(1, 8)]


def valid_config(environment: str = "dev") -> dict[str, object]:
    project = "WRD" if environment == "dev" else "WORKFORCE-PROD"
    return {
        "environment": environment,
        "jira": {
            "site_url": "https://example.atlassian.net",
            "allowed_project_keys": [project],
            "mutation_project_key": "WRD" if environment == "dev" else None,
            "allow_mutations": environment == "dev",
            "seed_project_keys": ["WRD"] if environment == "dev" else [],
            "cleanup_project_keys": ["WRD"] if environment == "dev" else [],
            "custom_fields": {
                "blocker_category": "customfield_10042",
            },
            "workforce_label_prefix": "workforce-employee:",
            "allowed_workforce_employee_ids": EMPLOYEE_IDS,
        },
        "aws": {
            "region": "us-east-1",
            "report_bucket": f"workforce-risk-{environment}-reports",
            "notification_queue": f"workforce-risk-{environment}-notifications",
        },
        "auth": {
            "api_key_hmac_pepper_ref": (
                f"secretsmanager://workforce-risk/{environment}/api-key-pepper"
            ),
            "allowed_roles": ["viewer", "manager", "administrator"],
        },
        "limits": {
            "request_bytes": 65536,
            "chat_requests_per_minute": 20,
            "scan_requests_per_hour": 4,
        },
        "scoring": {"version": "v1"},
    }


def test_rejects_unknown_environment() -> None:
    config = valid_config()
    config["environment"] = "staging"

    with pytest.raises(ConfigurationError, match="environment"):
        EnvironmentConfig.model_validate(config)


def test_rejects_production_mutations() -> None:
    config = valid_config("prod")
    config["jira"]["allow_mutations"] = True  # type: ignore[index]
    config["jira"]["mutation_project_key"] = "WORKFORCE-PROD"  # type: ignore[index]

    with pytest.raises(ConfigurationError, match="production mutations"):
        EnvironmentConfig.model_validate(config)


@pytest.mark.parametrize("operation", ["seed_project_keys", "cleanup_project_keys"])
def test_rejects_production_project_seed_or_cleanup(operation: str) -> None:
    config = valid_config("dev")
    config["jira"][operation] = ["WORKFORCE-PROD"]  # type: ignore[index]

    with pytest.raises(ConfigurationError, match="WORKFORCE-PROD"):
        EnvironmentConfig.model_validate(config)


@pytest.mark.parametrize("field", ["blocker_category"])
def test_rejects_missing_required_custom_field_mapping(field: str) -> None:
    config = valid_config()
    del config["jira"]["custom_fields"][field]  # type: ignore[index]

    with pytest.raises(ConfigurationError):
        EnvironmentConfig.model_validate(config)


def test_rejects_unsafe_workforce_label_prefix() -> None:
    config = valid_config()
    config["jira"]["workforce_label_prefix"] = "employee"  # type: ignore[index]

    with pytest.raises(ConfigurationError, match="workforce label prefix"):
        EnvironmentConfig.model_validate(config)


def test_rejects_literal_api_key_pepper() -> None:
    config = valid_config()
    config["auth"]["api_key_hmac_pepper_ref"] = "literal-secret"  # type: ignore[index]

    with pytest.raises(ConfigurationError, match="secret reference"):
        EnvironmentConfig.model_validate(config)


def test_rejects_overlapping_dev_and_prod_jira_scope() -> None:
    dev = EnvironmentConfig.model_validate(valid_config("dev"))
    prod_data = valid_config("prod")
    prod_data["jira"]["allowed_project_keys"] = ["WRD"]  # type: ignore[index]
    prod = EnvironmentConfig.model_validate(prod_data)

    with pytest.raises(ConfigurationError, match="overlap"):
        validate_environment_isolation(dev, prod)


def test_loads_checked_in_dev_configuration() -> None:
    path = Path(__file__).parents[3] / "config" / "environments" / "dev.yaml"

    config = load_environment_config(path)

    assert config.environment == "dev"
    assert config.jira.mutation_project_key == "WRD"
    assert config.jira.workforce_label_prefix == "workforce-employee:"
    assert config.jira.allowed_workforce_employee_ids == EMPLOYEE_IDS
