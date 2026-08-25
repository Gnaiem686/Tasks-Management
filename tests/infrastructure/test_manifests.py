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


def test_migration_bootstraps_only_the_scoped_initial_manager_digest() -> None:
    docs = _documents(K8S / "base" / "workloads.yaml")
    migration = next(doc for doc in docs if doc["kind"] == "Job")
    command = migration["spec"]["template"]["spec"]["containers"][0]["command"]

    assert "alembic upgrade head" in " ".join(command)
    assert "workforce_persistence.bootstrap" in " ".join(command)


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


def test_mcp_deployments_bind_to_pod_network_with_collision_safe_ports() -> None:
    docs = _documents(K8S / "base" / "workloads.yaml")
    deployments = {
        doc["metadata"]["name"]: doc for doc in docs if doc["kind"] == "Deployment"
    }
    expected = {
        "workforce-risk-mcp": (
            "WORKFORCE_MCP_HOST",
            "WORKFORCE_MCP_LISTEN_PORT",
            "8001",
        ),
        "devops-mcp": ("DEVOPS_MCP_HOST", "DEVOPS_MCP_LISTEN_PORT", "8002"),
    }
    for name, (host_name, port_name, port) in expected.items():
        env = {
            item["name"]: item["value"]
            for item in deployments[name]["spec"]["template"]["spec"]["containers"][0][
                "env"
            ]
        }
        assert env[host_name] == "0.0.0.0"
        assert env[port_name] == port


def test_aws_workloads_use_projected_web_identity_not_static_credentials() -> None:
    manifest = (K8S / "base" / "workloads.yaml").read_text()
    assert "AWS_WEB_IDENTITY_TOKEN_FILE" in manifest
    assert "WORKFORCE_APPLICATION_ROLE_ARN" in manifest
    assert "audience: sts.amazonaws.com" in manifest
    assert "serviceAccountToken:" in manifest
    assert "AWS_ACCESS_KEY_ID" not in manifest
    assert "AWS_SECRET_ACCESS_KEY" not in manifest


def test_external_secrets_service_account_uses_its_workload_role_directly() -> None:
    docs = _documents(K8S / "base" / "workloads.yaml")
    account = next(
        doc
        for doc in docs
        if doc["kind"] == "ServiceAccount"
        and doc["metadata"]["name"] == "external-secrets"
    )
    assert account["metadata"]["annotations"] == {
        "eks.amazonaws.com/role-arn": "WORKFORCE_EXTERNAL_SECRETS_ROLE_ARN"
    }

    for environment in ("dev", "prod"):
        documents = _documents(K8S / "overlays" / environment / "environment.yaml")
        store = next(doc for doc in documents if doc["kind"] == "SecretStore")
        provider = store["spec"]["provider"]["aws"]
        assert "role" not in provider


def test_scan_cronjob_is_non_overlapping_and_bounded() -> None:
    docs = _documents(K8S / "base" / "workloads.yaml")
    cronjob = next(doc for doc in docs if doc["kind"] == "CronJob")
    assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"
    assert cronjob["spec"]["startingDeadlineSeconds"] > 0
    assert cronjob["spec"]["successfulJobsHistoryLimit"] >= 1
    assert cronjob["spec"]["failedJobsHistoryLimit"] >= 1
    assert cronjob["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] > 0
    command = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][
        0
    ]["command"]
    assert command == ["python", "-m", "agent_api.scheduled_scan"]


def test_environment_overlays_use_terraform_secret_names() -> None:
    for environment in ("dev", "prod"):
        rendered = (K8S / "overlays" / environment / "secret-paths.yaml").read_text()
        for secret in ("database", "jira-mcp", "api-key-pepper", "initial-api-key"):
            assert f"workforce-risk/{environment}/{secret}" in rendered


def test_overlays_are_isolated_and_use_the_same_validated_jira_scope() -> None:
    dev = _documents(K8S / "overlays" / "dev" / "environment.yaml")
    prod = _documents(K8S / "overlays" / "prod" / "environment.yaml")
    dev_config = next(doc for doc in dev if doc["kind"] == "ConfigMap")
    prod_config = next(doc for doc in prod if doc["kind"] == "ConfigMap")
    assert dev_config["metadata"]["namespace"] == "dev"
    assert prod_config["metadata"]["namespace"] == "prod"
    assert dev_config["data"]["JIRA_PROJECT_KEY"] == "WRD"
    assert (
        prod_config["data"]["JIRA_PROJECT_KEY"]
        == dev_config["data"]["JIRA_PROJECT_KEY"]
    )
    assert prod_config["data"]["JIRA_MUTATION_ENABLED"] == "false"
    assert dev_config["data"]["REPORT_BUCKET"] == "WORKFORCE_REPORT_BUCKET"
    assert prod_config["data"]["REPORT_BUCKET"] == "WORKFORCE_REPORT_BUCKET"
    assert dev_config["data"]["NOTIFICATION_QUEUE"] == (
        "WORKFORCE_NOTIFICATION_QUEUE_URL"
    )
    assert prod_config["data"]["NOTIFICATION_QUEUE"] == (
        "WORKFORCE_NOTIFICATION_QUEUE_URL"
    )

    dev_workflow = (ROOT / ".github" / "workflows" / "deploy-dev.yml").read_text()
    prod_workflow = (ROOT / ".github" / "workflows" / "promote-prod.yml").read_text()
    assert "DEV_REPORT_BUCKET" in dev_workflow
    assert "DEV_NOTIFICATION_QUEUE_URL" in dev_workflow
    assert "PROD_REPORT_BUCKET" in prod_workflow
    assert "PROD_NOTIFICATION_QUEUE_URL" in prod_workflow


def test_dev_ingress_accepts_the_aws_load_balancer_hostname() -> None:
    dev_kustomization = (K8S / "overlays" / "dev" / "kustomization.yaml").read_text()
    dev_ingress_patch = (K8S / "overlays" / "dev" / "ingress-patch.yaml").read_text()
    prod_ingress_patch = (K8S / "overlays" / "prod" / "ingress-patch.yaml").read_text()

    assert "op: remove" in dev_ingress_patch
    assert "/spec/rules/0/host" in dev_ingress_patch
    assert "target:" in dev_kustomization
    assert "host:" in prod_ingress_patch


def test_dev_runtime_uses_release_supplied_aws_resources_and_bedrock() -> None:
    dev_environment = (K8S / "overlays" / "dev" / "environment.yaml").read_text()
    workflow = (ROOT / ".github" / "workflows" / "deploy-dev.yml").read_text()

    assert "WORKFORCE_REPORT_BUCKET" in dev_environment
    assert "WORKFORCE_NOTIFICATION_QUEUE_URL" in dev_environment
    assert "BEDROCK_MODEL_ID: amazon.nova-lite-v1:0" in dev_environment
    assert "EVIDENCE_MODE: jira" in dev_environment
    assert 'JIRA_EMPLOYEE_ISSUE_MAP: \'{"EMP-001":"WRD-2"' in dev_environment
    assert 'WORKFORCE_CAPACITY_MAP: \'{"EMP-001":40' in dev_environment
    assert "SCAN_EMPLOYEE_IDS: EMP-001,EMP-002,EMP-006" in dev_environment
    workloads = (ROOT / "infra/kubernetes/base/workloads.yaml").read_text()
    assert "name: JIRA_MCP_AUTHORIZATION" in workloads
    assert "key: ATLASSIAN_MCP_CREDENTIAL" in workloads
    assert "WORKFORCE_REPORT_BUCKET" in workflow
    assert "WORKFORCE_NOTIFICATION_QUEUE_URL" in workflow


def test_application_network_policy_allows_private_postgres_only() -> None:
    docs = _documents(K8S / "base" / "workloads.yaml")
    policy = next(
        doc
        for doc in docs
        if doc["kind"] == "NetworkPolicy"
        and doc["metadata"]["name"] == "allow-application"
    )
    egress = policy["spec"]["egress"]

    postgres_rules = [
        rule
        for rule in egress
        if {"protocol": "TCP", "port": 5432} in rule.get("ports", [])
    ]
    assert postgres_rules == [
        {
            "to": [{"ipBlock": {"cidr": "10.40.0.0/16"}}],
            "ports": [{"protocol": "TCP", "port": 5432}],
        }
    ]


def test_production_has_provisional_measured_hpa_contract() -> None:
    docs = _documents(K8S / "overlays" / "prod" / "environment.yaml")
    hpa = next(doc for doc in docs if doc["kind"] == "HorizontalPodAutoscaler")
    assert hpa["spec"]["scaleTargetRef"]["name"] == "agent-api"
    assert hpa["spec"]["minReplicas"] >= 2
    assert hpa["spec"]["maxReplicas"] > hpa["spec"]["minReplicas"]
    assert hpa["spec"]["metrics"][0]["resource"]["name"] == "cpu"
    assert "behavior" in hpa["spec"]


def test_agent_api_replicas_are_owned_by_the_production_hpa() -> None:
    docs = _documents(K8S / "base" / "workloads.yaml")
    agent_api = next(
        doc
        for doc in docs
        if doc["kind"] == "Deployment" and doc["metadata"]["name"] == "agent-api"
    )

    assert "replicas" not in agent_api["spec"]


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
