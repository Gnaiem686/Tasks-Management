from __future__ import annotations

from typing import Protocol

from pydantic import ConfigDict

from devops_mcp.schemas import DiagnosticEnvelope, DiagnosticRequest, envelope

NAMED_QUERIES = {
    "api_error_rate": (
        'sum(rate(http_requests_total{status_class="5xx",'
        'environment="$environment"}[5m]))'
    ),
    "api_latency_p95": (
        "histogram_quantile(0.95,sum by (le)(rate("
        'http_request_duration_seconds_bucket{environment="$environment"}[5m])))'
    ),
    "scan_freshness": (
        "time()-max(workforce_scan_last_completed_timestamp_seconds"
        '{environment="$environment"})'
    ),
    "queue_backlog": (
        'workforce_notification_queue_visible_messages{environment="$environment"}'
    ),
    "jira_read_success": (
        'sum(rate(jira_mcp_requests_total{outcome="success",'
        'environment="$environment"}[5m]))'
    ),
    "proposal_verification": (
        'sum(rate(workforce_proposal_verifications_total{outcome="verified",'
        'environment="$environment"}[5m]))'
    ),
}


class MetricRequest(DiagnosticRequest):
    model_config = ConfigDict(extra="forbid")
    query_name: str


class PrometheusReader(Protocol):
    async def query(self, expression: str, *, timeout_seconds: float) -> float: ...


async def query_metric(
    request: MetricRequest, *, reader: PrometheusReader
) -> DiagnosticEnvelope:
    template = NAMED_QUERIES.get(request.query_name)
    if template is None:
        raise PermissionError("Prometheus query is not allowlisted")
    expression = template.replace("$environment", request.environment)
    value = await reader.query(expression, timeout_seconds=5)
    return envelope(request, data={"query_name": request.query_name, "value": value})
