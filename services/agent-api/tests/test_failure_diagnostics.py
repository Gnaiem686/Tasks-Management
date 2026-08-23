from __future__ import annotations

import json
import logging

import pytest
from agent_api.failure_diagnostics import (
    FailureComponent,
    classify_failure,
    is_retryable_assistant_failure,
    log_assistant_event,
)
from agent_api.grounding import GroundingValidationError
from agent_api.main import http_error
from fastapi import HTTPException
from starlette.requests import Request


@pytest.mark.parametrize(
    ("error", "component", "expected"),
    [
        (TimeoutError("late"), "jira", "jira_mcp_timeout"),
        (PermissionError("401 unauthorized"), "jira", "jira_mcp_auth_error"),
        (RuntimeError("429 rate limit"), "jira", "jira_mcp_rate_limit"),
        (TimeoutError("late"), "bedrock", "bedrock_timeout"),
        (RuntimeError("ThrottlingException"), "bedrock", "bedrock_throttling"),
        (OSError("model invocation failed"), "bedrock", "bedrock_model_error"),
        (ValueError("malformed JSON"), "parse", "output_parse_error"),
        (
            GroundingValidationError("wrong issue"),
            "grounding",
            "grounding_validation_error",
        ),
        (AssertionError("bug"), "internal", "internal_exception"),
    ],
)
def test_classifies_assistant_failures(
    error: BaseException, component: FailureComponent, expected: str
) -> None:
    assert classify_failure(error, component=component) == expected


def test_structured_event_keeps_correlation_and_safe_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("assistant-test")
    with caplog.at_level(logging.INFO):
        log_assistant_event(
            logger,
            "jira_tool_finished",
            "corr-123",
            project_key="WFD",
            duration_ms=12,
            success=True,
        )
    record = caplog.records[-1]
    fields = vars(record)
    assert fields["correlation_id"] == "corr-123"
    assert fields["event"] == "jira_tool_finished"
    assert fields["project_key"] == "WFD"
    assert fields["duration_ms"] == 12
    assert fields["success"] is True


def test_nested_bedrock_timeout_is_retryable() -> None:
    cause = TimeoutError("late")
    wrapped = OSError("Bedrock explanation invocation failed")
    wrapped.__cause__ = cause

    code = classify_failure(wrapped, component="bedrock")

    assert code == "bedrock_timeout"
    assert is_retryable_assistant_failure(code) is True


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("bedrock_timeout", True),
        ("bedrock_throttling", True),
        ("bedrock_service_unavailable", True),
        ("bedrock_circuit_open", True),
        ("bedrock_model_error", False),
        ("grounding_validation_error", False),
        ("jira_mcp_auth_error", False),
        ("internal_exception", False),
    ],
)
def test_only_transient_bedrock_failures_persist(code: str, expected: bool) -> None:
    assert is_retryable_assistant_failure(code) is expected


@pytest.mark.asyncio
async def test_http_handler_preserves_safe_retryability_metadata() -> None:
    request = Request({"type": "http", "method": "POST", "path": "/chat"})
    request.state.correlation_id = "corr-outer"

    response = await http_error(
        request,
        HTTPException(
            status_code=503,
            detail={
                "error_code": "bedrock_timeout",
                "correlation_id": "corr-bedrock",
                "message": "The assistant could not produce a grounded answer.",
                "retryable": True,
                "unsafe_extra": "must not escape",
            },
        ),
    )
    payload = json.loads(bytes(response.body))

    assert payload == {
        "error_code": "bedrock_timeout",
        "message": "The assistant could not produce a grounded answer.",
        "correlation_id": "corr-bedrock",
        "retryable": True,
    }
