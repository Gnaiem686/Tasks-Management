from workforce_observability.context import (
    CorrelationContext,
    from_http_headers,
    from_mcp_metadata,
    from_sqs_attributes,
)


def test_http_to_mcp_to_sqs_preserves_one_correlation_id() -> None:
    incoming = from_http_headers({"x-correlation-id": "corr-end-to-end"})
    mcp = from_mcp_metadata(incoming.mcp_metadata())
    worker = from_sqs_attributes(mcp.sqs_attributes())

    assert incoming == CorrelationContext("corr-end-to-end")
    assert mcp == incoming
    assert worker == incoming


def test_missing_http_correlation_id_creates_safe_identifier() -> None:
    context = from_http_headers({})

    assert context.value
    assert len(context.value) <= 64
