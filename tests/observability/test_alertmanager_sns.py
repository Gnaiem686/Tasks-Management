from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[2]
EBS = ROOT / "infra" / "kubernetes" / "observability" / "ebs"


def _values() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        yaml.safe_load((EBS / "kube-prometheus-stack-values.yaml").read_text()),
    )


def test_alertmanager_routes_platform_alerts_to_sns() -> None:
    alertmanager = _values()["alertmanager"]
    config = alertmanager["config"]

    assert config["route"]["receiver"] == "workforce-platform-sns"
    assert config["route"]["group_by"] == ["environment", "owner", "severity"]
    receiver = next(
        item for item in config["receivers"] if item["name"] == "workforce-platform-sns"
    )
    sns = receiver["sns_configs"][0]
    assert sns == {
        "topic_arn": "WORKFORCE_PLATFORM_ALERT_TOPIC_ARN",
        "sigv4": {"region": "WORKFORCE_AWS_REGION"},
        "send_resolved": True,
    }


def test_alertmanager_uses_exact_oidc_role_and_service_account() -> None:
    alertmanager = _values()["alertmanager"]
    spec = alertmanager["alertmanagerSpec"]

    assert alertmanager["serviceAccount"] == {
        "create": True,
        "name": "workforce-alertmanager",
    }
    assert spec["serviceAccountName"] == "workforce-alertmanager"
    container = next(
        item for item in spec["containers"] if item["name"] == "alertmanager"
    )
    env = {item["name"]: item["value"] for item in container["env"]}
    assert env == {
        "AWS_ROLE_ARN": "WORKFORCE_ALERTMANAGER_SNS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE": "/var/run/secrets/aws/token",
    }
    assert container["volumeMounts"] == [
        {
            "name": "aws-web-identity",
            "mountPath": "/var/run/secrets/aws",
            "readOnly": True,
        }
    ]
    token = spec["volumes"][0]["projected"]["sources"][0]["serviceAccountToken"]
    assert token == {
        "audience": "sts.amazonaws.com",
        "expirationSeconds": 3600,
        "path": "token",
    }


def test_aws_monitoring_deploy_requires_and_substitutes_terraform_outputs() -> None:
    script = (
        ROOT / "scripts" / "observability" / "deploy_aws_monitoring.sh"
    ).read_text()

    assert 'require_value "PLATFORM_ALERT_TOPIC_ARN"' in script
    assert 'require_value "ALERTMANAGER_SNS_ROLE_ARN"' in script
    assert 'require_value "AWS_REGION"' in script
    assert "WORKFORCE_PLATFORM_ALERT_TOPIC_ARN" in script
    assert "WORKFORCE_ALERTMANAGER_SNS_ROLE_ARN" in script
    assert "WORKFORCE_AWS_REGION" in script
    assert "helm upgrade --install workforce-monitoring" in script
    assert "kube-prometheus-stack" in script
    assert (
        'kubectl apply -f "$PROJECT_ROOT/infra/kubernetes/observability/'
        'prometheus-rules.yaml"' in script
    )
