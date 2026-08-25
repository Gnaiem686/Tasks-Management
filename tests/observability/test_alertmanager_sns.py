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


def test_monitoring_chart_pin_matches_the_deployed_cluster() -> None:
    versions = (EBS / "versions.env").read_text()

    assert "KUBE_PROMETHEUS_STACK_CHART_VERSION=88.5.3" in versions


def test_alertmanager_routes_platform_alerts_to_sns() -> None:
    alertmanager = _values()["alertmanager"]
    config = alertmanager["config"]

    assert config["route"]["receiver"] == "workforce-platform-sns"
    assert config["route"]["group_by"] == ["environment", "owner", "severity"]
    assert config["route"]["group_wait"] == "30s"
    assert config["route"]["group_interval"] == "5m"
    assert config["route"]["repeat_interval"] == "24h"
    receiver = next(
        item for item in config["receivers"] if item["name"] == "workforce-platform-sns"
    )
    sns = receiver["sns_configs"][0]
    assert sns == {
        "topic_arn": "WORKFORCE_PLATFORM_ALERT_TOPIC_ARN",
        "sigv4": {"region": "WORKFORCE_AWS_REGION"},
        "subject": "[Workforce Risk] Platform health alert",
        "send_resolved": True,
    }


def test_alertmanager_silences_permanent_informational_alerts() -> None:
    config = _values()["alertmanager"]["config"]

    null_receiver = next(item for item in config["receivers"] if item["name"] == "null")
    assert null_receiver == {"name": "null"}
    assert {
        "receiver": "null",
        "matchers": ['alertname=~"Watchdog|InfoInhibitor"'],
    } in config["route"]["routes"]


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


def test_aws_monitoring_scrapes_dev_and_prod_without_grafana_alertmanager_source() -> (
    None
):
    values = _values()
    targets = yaml.safe_load_all(
        (
            ROOT / "infra/kubernetes/observability/prometheus-scrape-targets.yaml"
        ).read_text()
    )
    resources = list(targets)
    service_monitor = next(
        item for item in resources if item["kind"] == "ServiceMonitor"
    )
    probes = [item for item in resources if item["kind"] == "Probe"]

    assert service_monitor["spec"]["namespaceSelector"]["matchNames"] == [
        "dev",
        "prod",
    ]
    rendered_targets = str(probes)
    for environment in ("dev", "prod"):
        assert f"agent-api.{environment}.svc.cluster.local" in rendered_targets
        assert f"workforce-risk-mcp.{environment}.svc.cluster.local" in rendered_targets
        assert f"devops-mcp.{environment}.svc.cluster.local" in rendered_targets
    assert values["grafana"]["sidecar"]["datasources"]["alertmanager"] == {
        "enabled": False
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
    assert (
        'kubectl apply -f "$PROJECT_ROOT/infra/kubernetes/observability/'
        'prometheus-scrape-targets.yaml"' in script
    )
    assert "statefulset/alertmanager-workforce-monitoring-kube-alertmanager" in script
