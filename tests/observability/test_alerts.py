import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
OBSERVABILITY = ROOT / "infra" / "kubernetes" / "observability"


def test_operator_alerts_are_actionable_and_exclude_business_risk() -> None:
    manifest = yaml.safe_load((OBSERVABILITY / "prometheus-rules.yaml").read_text())
    rules = [rule for group in manifest["spec"]["groups"] for rule in group["rules"]]
    alerts = {rule["alert"]: rule for rule in rules}

    assert {
        "WorkforceScheduledScanMissed",
        "WorkforceNotificationQueueBacklog",
        "WorkforceUncertainJiraExecution",
        "WorkforceJiraCircuitOpen",
        "WorkforceNodeNotReady",
        "WorkforceUnavailableReplicas",
        "WorkforceCronJobFailed",
        "WorkforceIngressFailureRate",
        "WorkforceRdsConnectivityFailure",
        "WorkforceNotificationDlqNotEmpty",
    } <= alerts.keys()
    assert not any("Employee" in name or "ProjectRisk" in name for name in alerts)
    for rule in rules:
        assert {"severity", "owner", "runbook_url", "environment"} <= rule[
            "labels"
        ].keys()
        assert rule["annotations"]["summary"]


def test_alertmanager_groups_and_inhibits_dependency_fanout() -> None:
    config = yaml.safe_load((OBSERVABILITY / "alertmanager.yaml").read_text())

    assert "alertname" not in config["route"]["group_by"]
    assert "environment" in config["route"]["group_by"]
    assert config["inhibit_rules"]


def test_four_dashboards_are_valid_and_do_not_embed_workforce_identifiers() -> None:
    dashboard_dir = OBSERVABILITY / "grafana-dashboards"
    files = sorted(dashboard_dir.glob("*.json"))

    assert len(files) == 4
    for path in files:
        dashboard = json.loads(path.read_text())
        assert dashboard["title"]
        assert dashboard["panels"]
        serialized = json.dumps(dashboard).lower()
        for forbidden in ("employee_id", "task_id", "proposal_id", "correlation_id"):
            assert forbidden not in serialized


def test_logs_and_traces_define_environment_specific_controls() -> None:
    loki = yaml.safe_load((OBSERVABILITY / "loki.yaml").read_text())
    otel = yaml.safe_load((OBSERVABILITY / "otel.yaml").read_text())

    assert (
        loki["workforce_retention_policy"]["dev"]
        != loki["workforce_retention_policy"]["prod"]
    )
    policy = otel["workforce_sampling_policy"]
    assert policy["dev_percentage"] > policy["prod_percentage"]
    assert policy["always_retain_outcomes"] == ["failed", "uncertain"]
