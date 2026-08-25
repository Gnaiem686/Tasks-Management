from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]


def config(environment: str) -> dict[str, str]:
    documents = yaml.safe_load_all(
        (
            ROOT / "infra/kubernetes/overlays" / environment / "environment.yaml"
        ).read_text()
    )
    return next(item["data"] for item in documents if item["kind"] == "ConfigMap")


@pytest.mark.infrastructure
def test_dev_public_dashboard_is_bedrock_only_and_read_only() -> None:
    values = config("dev")
    assert values["ALLOW_ANONYMOUS_READ"] == "true"
    assert values["ALLOW_JIRA_MUTATIONS"] == "false"
    assert values["JIRA_MUTATION_ENABLED"] == "false"
    assert values["BEDROCK_ONLY_CHAT"] == "true"
    assert "WFD:Workforce Real Data" in values["ALLOWED_JIRA_PROJECTS"]
    assert "WRD:Workforce Risk Demo" in values["ALLOWED_JIRA_PROJECTS"]


@pytest.mark.infrastructure
def test_prod_matches_dev_functional_configuration() -> None:
    dev = config("dev")
    prod = config("prod")
    shared_keys = {
        "AWS_REGION",
        "BEDROCK_MODEL_ID",
        "BEDROCK_ONLY_CHAT",
        "ALLOW_ANONYMOUS_READ",
        "ALLOW_JIRA_MUTATIONS",
        "ALLOWED_JIRA_PROJECTS",
        "EVIDENCE_MODE",
        "JIRA_PROJECT_KEY",
        "JIRA_CLOUD_ID",
        "JIRA_EMPLOYEE_ISSUE_MAP",
        "WORKFORCE_CAPACITY_MAP",
        "SCAN_EMPLOYEE_IDS",
        "JIRA_MUTATION_ENABLED",
        "REPORT_BUCKET",
        "NOTIFICATION_QUEUE",
        "DAILY_SCAN_SCHEDULE",
    }

    assert prod["APP_ENVIRONMENT"] == "prod"
    assert dev["APP_ENVIRONMENT"] == "dev"
    assert {key: prod[key] for key in shared_keys} == {
        key: dev[key] for key in shared_keys
    }
