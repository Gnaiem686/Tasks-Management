from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

CORRELATION_HEADER = "x-correlation-id"
MCP_CORRELATION_KEY = "correlation_id"
SQS_CORRELATION_KEY = "correlation_id"


@dataclass(frozen=True)
class CorrelationContext:
    value: str

    def mcp_metadata(self) -> dict[str, str]:
        return {MCP_CORRELATION_KEY: self.value}

    def sqs_attributes(self) -> dict[str, dict[str, str]]:
        return {
            SQS_CORRELATION_KEY: {
                "DataType": "String",
                "StringValue": self.value,
            }
        }


def from_http_headers(headers: dict[str, str]) -> CorrelationContext:
    value = headers.get(CORRELATION_HEADER) or uuid4().hex
    return CorrelationContext(_validate(value))


def from_mcp_metadata(metadata: dict[str, str]) -> CorrelationContext:
    return CorrelationContext(_validate(metadata[MCP_CORRELATION_KEY]))


def from_sqs_attributes(
    attributes: dict[str, dict[str, str]],
) -> CorrelationContext:
    return CorrelationContext(_validate(attributes[SQS_CORRELATION_KEY]["StringValue"]))


def _validate(value: str) -> str:
    if (
        not value
        or len(value) > 64
        or any(not (char.isalnum() or char in "-_") for char in value)
    ):
        raise ValueError("invalid correlation ID")
    return value
