from __future__ import annotations

from collections import defaultdict
from threading import Lock

ALLOWED_LABELS = frozenset(
    {"environment", "service", "workflow", "outcome", "dependency"}
)
ALLOWED_METRICS = frozenset(
    {
        "workforce_http_requests_total",
        "workforce_http_request_duration_seconds",
        "workforce_mcp_requests_total",
        "workforce_scoring_runs_total",
        "workforce_scan_runs_total",
        "workforce_scan_last_completed_timestamp_seconds",
        "workforce_snapshot_age_seconds",
        "workforce_proposal_operations_total",
        "workforce_proposal_verifications_total",
        "workforce_notification_queue_delay_seconds",
        "workforce_notification_queue_visible_messages",
        "workforce_jira_mcp_requests_total",
        "workforce_bedrock_requests_total",
        "workforce_dependency_ready",
    }
)


class MetricRegistry:
    """Small metrics registry that refuses unbounded names and labels."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, tuple[tuple[str, str], ...]], float] = (
            defaultdict(float)
        )
        self._lock = Lock()

    def increment(self, metric: str, value: float = 1, **labels: str) -> None:
        self._observe(metric, value, labels, additive=True)

    def set(self, metric: str, value: float, **labels: str) -> None:
        self._observe(metric, value, labels, additive=False)

    def _observe(
        self,
        metric: str,
        value: float,
        labels: dict[str, str],
        *,
        additive: bool,
    ) -> None:
        if metric not in ALLOWED_METRICS:
            raise ValueError("metric is not registered")
        unknown = labels.keys() - ALLOWED_LABELS
        if unknown:
            raise ValueError(f"metric label is not allowlisted: {sorted(unknown)[0]}")
        key = metric, tuple(sorted(labels.items()))
        with self._lock:
            if additive:
                self._values[key] += value
            else:
                self._values[key] = value

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            values = sorted(self._values.items())
        for (metric, labels), value in values:
            encoded = ",".join(
                f'{key}="{_escape(label_value)}"' for key, label_value in labels
            )
            suffix = f"{{{encoded}}}" if encoded else ""
            lines.append(f"{metric}{suffix} {value:g}")
        return "\n".join(lines) + ("\n" if lines else "")

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
