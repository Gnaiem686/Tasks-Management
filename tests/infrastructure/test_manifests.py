from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[2]
K8S = ROOT / "infra" / "kubernetes"


def _documents(path: Path) -> list[dict[str, Any]]:
    return [
        cast(dict[str, Any], doc) for doc in yaml.safe_load_all(path.read_text()) if doc
    ]


def _all_yaml() -> str:
    return "\n".join(path.read_text() for path in K8S.rglob("*.yaml"))


def test_base_has_required_workloads_and_foundations() -> None:
    docs = _documents(K8S / "base" / "workloads.yaml")
    kinds = {doc["kind"] for doc in docs}
    assert {
        "ConfigMap",
        "CronJob",
        "Deployment",
        "ExternalSecret",
        "Job",
        "NetworkPolicy",
        "PodDisruptionBudget",
        "Service",
        "ServiceAccount",
    } <= kinds


def test_deployments_have_probes_resources_and_distinct_service_accounts() -> None:
    docs = _documents(K8S / "base" / "workloads.yaml")
    deployments = [doc for doc in docs if doc["kind"] == "Deployment"]
    assert len(deployments) == 4
    accounts = set()
    for deployment in deployments:
        pod = deployment["spec"]["template"]["spec"]
        accounts.add(pod["serviceAccountName"])
        container = pod["containers"][0]
        assert {"startupProbe", "readinessProbe", "livenessProbe"} <= container.keys()
        assert {"requests", "limits"} <= container["resources"].keys()
        assert "@sha256:" in container["image"]
    assert len(accounts) == 4


def test_aws_workloads_use_projected_web_identity_not_static_credentials() -> None:
    manifest = (K8S / "base" / "workloads.yaml").read_text()
    assert "AWS_WEB_IDENTITY_TOKEN_FILE" in manifest
    assert "WORKFORCE_APPLICATION_ROLE_ARN" in manifest
    assert "audience: sts.amazonaws.com" in manifest
    assert "serviceAccountToken:" in manifest
    assert "AWS_ACCESS_KEY_ID" not in manifest
    assert "AWS_SECRET_ACCESS_KEY" not in manifest


def test_scan_cronjob_is_non_overlapping_and_bounded() -> None:
    docs = _documents(K8S / "base" / "workloads.yaml")
    cronjob = next(doc for doc in docs if doc["kind"] == "CronJob")
    assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"
    assert cronjob["spec"]["startingDeadlineSeconds"] > 0
    assert cronjob["spec"]["successfulJobsHistoryLimit"] >= 1
    assert cronjob["spec"]["failedJobsHistoryLimit"] >= 1
    assert cronjob["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] > 0
    command = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"][
        "containers"
    ][0]["command"]
    assert command == ["python", "-m", "agent_api.scheduled_scan"]


def test_environment_overlays_use_terraform_secret_names() -> None:
    for environment in ("dev", "prod"):
        rendered = (K8S / "overlays" / environment / "secret-paths.yaml").read_text()
        for secret in ("database", "jira-mcp", "api-key-pepper", "initial-api-key"):
            assert f"workforce-risk/{environment}/{secret}" in rendered


def test_overlays_are_isolated_and_use_separate_jira_scopes() -> None:
    dev = _documents(K8S / "overlays" / "dev" / "environment.yaml")
    prod = _documents(K8S / "overlays" / "prod" / "environment.yaml")
    dev_config = next(doc for doc in dev if doc["kind"] == "ConfigMap")
    prod_config = next(doc for doc in prod if doc["kind"] == "ConfigMap")
    assert dev_config["metadata"]["namespace"] == "dev"
    assert prod_config["metadata"]["namespace"] == "prod"
    assert dev_config["data"]["JIRA_PROJECT_KEY"] == "WRD"
    assert prod_config["data"]["JIRA_PROJECT_KEY"] == "WORKFORCE-PROD"
    assert prod_config["data"]["JIRA_MUTATION_ENABLED"] == "false"
    assert dev_config["data"]["REPORT_BUCKET"] != prod_config["data"]["REPORT_BUCKET"]
    assert (
        dev_config["data"]["NOTIFICATION_QUEUE"]
        != prod_config["data"]["NOTIFICATION_QUEUE"]
    )


def test_production_has_provisional_measured_hpa_contract() -> None:
    docs = _documents(K8S / "overlays" / "prod" / "environment.yaml")
    hpa = next(doc for doc in docs if doc["kind"] == "HorizontalPodAutoscaler")
    assert hpa["spec"]["scaleTargetRef"]["name"] == "agent-api"
    assert hpa["spec"]["minReplicas"] >= 2
    assert hpa["spec"]["maxReplicas"] > hpa["spec"]["minReplicas"]
    assert hpa["spec"]["metrics"][0]["resource"]["name"] == "cpu"
    assert "behavior" in hpa["spec"]


def test_no_simulator_or_kubernetes_scenario_credentials() -> None:
    manifest = _all_yaml().lower()
    forbidden = [
        "namespace: simulation",
        "scenario-controller",
        "jira_seed",
        "kubeconfig",
    ]
    for value in forbidden:
        assert value not in manifest


def test_validation_script_never_applies_prod_application_resources() -> None:
    script = (
        ROOT / "scripts" / "validation" / "validate_workload_manifests.sh"
    ).read_text()
    assert "kubectl apply" not in script
    assert "kustomize build" in script
    assert "kubeconform" in script
    assert "-exit-on-error" in script
    assert "mutable image" in script


def test_addon_script_requires_exact_pins_and_checks_health() -> None:
    script = (ROOT / "scripts" / "validation" / "verify_cluster_addons.sh").read_text()
    for component in (
        "CALICO_VERSION",
        "INGRESS_VERSION",
        "METRICS_SERVER_VERSION",
        "EXTERNAL_SECRETS_VERSION",
        "PROMETHEUS_STACK_VERSION",
        "LOKI_VERSION",
        "OTEL_COLLECTOR_VERSION",
    ):
        assert component in script
    assert "latest" in script
    assert "kubectl rollout status" in script
