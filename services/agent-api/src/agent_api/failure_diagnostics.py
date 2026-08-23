from __future__ import annotations

import logging
from typing import Literal

from agent_api.grounding import GroundingValidationError

FailureComponent = Literal["jira", "bedrock", "parse", "grounding", "internal"]

_RETRYABLE_ASSISTANT_FAILURES = frozenset(
    {
        "bedrock_timeout",
        "bedrock_throttling",
        "bedrock_service_unavailable",
        "bedrock_circuit_open",
    }
)


def _error_chain(error: BaseException) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return tuple(chain)


def is_retryable_assistant_failure(failure_code: str) -> bool:
    return failure_code in _RETRYABLE_ASSISTANT_FAILURES


def classify_failure(error: BaseException, *, component: FailureComponent) -> str:
    chain = _error_chain(error)
    message = " | ".join(f"{type(item).__name__}: {item}" for item in chain).casefold()
    if component == "jira":
        if isinstance(error, TimeoutError):
            return "jira_mcp_timeout"
        if isinstance(error, PermissionError) or any(
            marker in message for marker in ("401", "403", "unauthorized", "forbidden")
        ):
            return "jira_mcp_auth_error"
        if "429" in message or "rate limit" in message or "throttl" in message:
            return "jira_mcp_rate_limit"
    if component == "bedrock":
        if any(isinstance(item, TimeoutError) for item in chain) or any(
            marker in message for marker in ("timed out", "timeout")
        ):
            return "bedrock_timeout"
        if "throttl" in message or "429" in message:
            return "bedrock_throttling"
        if "circuit is open" in message:
            return "bedrock_circuit_open"
        if any(
            marker in message
            for marker in (
                "serviceunavailable",
                "service unavailable",
                "internalserverexception",
                "bad gateway",
                "gateway timeout",
                "status code: 500",
                "status code: 502",
                "status code: 503",
                "status code: 504",
            )
        ):
            return "bedrock_service_unavailable"
        return "bedrock_model_error"
    if component == "parse":
        return "output_parse_error"
    if component == "grounding" or isinstance(error, GroundingValidationError):
        return "grounding_validation_error"
    return "internal_exception"


def log_assistant_event(
    logger: logging.Logger,
    event: str,
    correlation_id: str,
    **safe_fields: object,
) -> None:
    logger.info(
        "assistant_event",
        extra={
            "event": event,
            "correlation_id": correlation_id,
            **safe_fields,
        },
    )
