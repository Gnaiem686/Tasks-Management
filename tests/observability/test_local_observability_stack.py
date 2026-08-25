import json
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[2]
LOCAL = ROOT / "infra" / "observability" / "local"


def _compose() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load((ROOT / "compose.yaml").read_text()))


def test_local_compose_contains_complete_observability_stack() -> None:
    services = _compose()["services"]

    assert {
        "prometheus",
        "alertmanager",
        "grafana",
        "loki",
        "promtail",
        "blackbox-exporter",
        "node-exporter",
        "cadvisor",
    } <= services.keys()
    assert services["grafana"]["ports"] == ["127.0.0.1:3001:3000"]
    assert services["prometheus"]["ports"] == ["127.0.0.1:9090:9090"]
    assert services["loki"]["ports"] == ["127.0.0.1:3100:3100"]
    assert services["alertmanager"]["ports"] == ["127.0.0.1:9093:9093"]
    assert services["node-exporter"]["volumes"] == ["/:/host:ro"]


def test_prometheus_scrapes_application_and_local_platform_targets() -> None:
    config = yaml.safe_load((LOCAL / "prometheus" / "prometheus.yml").read_text())
    jobs = {item["job_name"]: item for item in config["scrape_configs"]}

    assert {
        "agent-api",
        "service-probes",
        "promtail",
        "cadvisor",
        "node-exporter",
    } <= jobs.keys()
    assert jobs["agent-api"]["metrics_path"] == "/metrics"
    assert jobs["agent-api"]["static_configs"][0]["targets"] == ["agent-api:8000"]
    assert config["alerting"]["alertmanagers"]
    assert config["rule_files"] == ["/etc/prometheus/rules/*.yml"]


def test_local_alert_rules_cover_required_failure_modes() -> None:
    groups = yaml.safe_load((LOCAL / "prometheus" / "alerts.yml").read_text())["groups"]
    alerts = {
        rule["alert"]: rule for group in groups for rule in group.get("rules", [])
    }

    assert {
        "WorkforceServiceDown",
        "WorkforceApiServerErrorSpike",
        "WorkforceApiHighLatency",
        "WorkforceBedrockFailure",
        "WorkforceToolTimeout",
        "WorkforceLogsMissing",
    } <= alerts.keys()
    assert (
        "promtail_custom_workforce_bedrock_log_failures_total"
        in alerts["WorkforceBedrockFailure"]["expr"]
    )
    assert (
        "promtail_custom_workforce_tool_timeouts_total"
        in alerts["WorkforceToolTimeout"]["expr"]
    )
    for rule in alerts.values():
        assert {"severity", "owner", "environment"} <= rule["labels"].keys()
        assert rule["annotations"]["summary"]


def test_grafana_provisions_prometheus_loki_and_health_dashboard() -> None:
    datasources = yaml.safe_load(
        (
            LOCAL / "grafana" / "provisioning" / "datasources" / "datasources.yml"
        ).read_text()
    )["datasources"]
    assert {item["type"] for item in datasources} == {"prometheus", "loki"}

    dashboard = json.loads(
        (LOCAL / "grafana" / "dashboards" / "workforce-system-health.json").read_text()
    )
    titles = {panel["title"] for panel in dashboard["panels"]}
    assert {
        "Service Probe Health",
        "Agent API Requests",
        "Agent API Server Errors",
        "Endpoint Probe Latency",
        "Bedrock Failures",
        "MCP and Tool Timeouts",
        "System CPU",
        "System Memory",
        "Recent Service Logs",
    } <= titles
    expressions = {
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "expr" in target
    }
    assert any(
        "promtail_custom_workforce_bedrock_log_failures_total" in expression
        for expression in expressions
    )
    assert any(
        "promtail_custom_workforce_tool_timeouts_total" in expression
        for expression in expressions
    )
    assert any(
        'container_cpu_usage_seconds_total{id="/"}' in expression
        and 'job="kubelet"' in expression
        for expression in expressions
    )
    assert any(
        'container_memory_working_set_bytes{id="/"}' in expression
        and 'job="kubelet"' in expression
        for expression in expressions
    )


def test_health_dashboard_handles_aws_kubernetes_empty_and_probe_series() -> None:
    dashboard = json.loads(
        (LOCAL / "grafana" / "dashboards" / "workforce-system-health.json").read_text()
    )
    panels = {panel["title"]: panel for panel in dashboard["panels"]}

    service_health = panels["Service Probe Health"]
    assert "count(probe_success)" in service_health["targets"][0]["expr"]
    assert service_health["fieldConfig"]["defaults"]["unit"] == "percent"

    for title in (
        "Agent API Server Errors",
        "Bedrock Failures",
        "MCP and Tool Timeouts",
    ):
        assert panels[title]["targets"][0]["expr"].endswith(" or vector(0)")

    assert 'job="kubelet"' in panels["System CPU"]["targets"][0]["expr"]
    assert 'id="/"' in panels["System CPU"]["targets"][0]["expr"]
    assert 'job="kubelet"' in panels["System Memory"]["targets"][0]["expr"]
    assert 'id="/"' in panels["System Memory"]["targets"][0]["expr"]

    logs = panels["Recent Service Logs"]["targets"][0]["expr"]
    assert logs == (
        '{environment=~"dev|prod",'
        'service_name=~"agent-api|workforce-risk-mcp|devops-mcp"} '
        '| line_format "{{.service_name}} | {{ __line__ }}"'
    )


def test_promtail_collects_only_this_compose_projects_logs_and_exports_metrics() -> (
    None
):
    config = yaml.safe_load((LOCAL / "promtail" / "promtail.yml").read_text())
    serialized = json.dumps(config)

    assert "com.docker.compose.project" in serialized
    assert "cicd-dev-promotion" in serialized
    assert "workforce_bedrock_log_failures_total" in serialized
    assert "workforce_tool_timeouts_total" in serialized
