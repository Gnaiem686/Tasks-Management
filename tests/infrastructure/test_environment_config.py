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
def test_prod_does_not_enable_anonymous_read() -> None:
    values = config("prod")
    assert values["ALLOW_ANONYMOUS_READ"] == "false"
    assert values["ALLOW_JIRA_MUTATIONS"] == "false"
