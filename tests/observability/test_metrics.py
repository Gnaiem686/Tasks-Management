from workforce_observability.metrics import MetricRegistry


def test_required_workflow_metrics_are_exposed_with_bounded_labels() -> None:
    registry = MetricRegistry()
    registry.increment(
        "workforce_mcp_requests_total",
        environment="dev",
        service="agent-api",
        workflow="investigation",
        outcome="success",
        dependency="jira",
    )

    exposition = registry.render()

    assert "workforce_mcp_requests_total" in exposition
    assert 'environment="dev"' in exposition
    assert 'dependency="jira"' in exposition


def test_metric_registry_rejects_identifiers_and_unbounded_labels() -> None:
    registry = MetricRegistry()

    for forbidden in (
        "task_id",
        "employee_id",
        "proposal_id",
        "correlation_id",
        "error",
    ):
        try:
            registry.increment(
                "workforce_mcp_requests_total",
                environment="dev",
                **{forbidden: "unsafe"},
            )
        except ValueError as exc:
            assert "label" in str(exc)
        else:
            raise AssertionError(f"forbidden label {forbidden} was accepted")


def test_metric_registry_rejects_unknown_metric_names() -> None:
    registry = MetricRegistry()

    try:
        registry.increment("employee_123_risk", environment="dev")
    except ValueError as exc:
        assert "metric" in str(exc)
    else:
        raise AssertionError("unregistered metric was accepted")
