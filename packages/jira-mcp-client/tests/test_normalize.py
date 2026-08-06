from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jira_mcp_client.normalize import JiraNormalizationError, normalize_issue
from jira_mcp_client.transport import extract_issue_payload
from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError

FIXTURE = (
    Path(__file__).parents[3] / "tests" / "fixtures" / "jira" / "wrd_1_structured.json"
)


def load_response() -> dict[str, Any]:
    value: dict[str, Any] = json.loads(FIXTURE.read_text())
    return value


@pytest.mark.unit
def test_normalizes_structured_issue_and_keeps_free_text_untrusted() -> None:
    evidence = normalize_issue(
        load_response(),
        expected_environment="dev",
        expected_correlation_id="corr-wrd-1",
        custom_fields={"blocker_category": "customfield_10042"},
    )

    assert evidence.key == "WRD-1"
    assert evidence.summary == "Implement login token refresh"
    assert evidence.status == "In Progress"
    assert evidence.priority == "High"
    assert evidence.assignee is not None
    assert evidence.assignee.account_id == "synthetic-account-current"
    assert evidence.due_date is not None
    assert evidence.due_date.isoformat() == "2026-07-23"
    assert evidence.original_estimate_seconds == 28800
    assert evidence.remaining_estimate_seconds == 14400
    assert evidence.links[0].issue_key == "WRD-2"
    assert evidence.activity_timestamp.isoformat() == "2026-08-06T10:30:00+00:00"
    assert evidence.custom_fields[0].raw_field_id == "customfield_10042"
    assert evidence.custom_fields[0].value == "Need clarification"
    assert evidence.untrusted_text[0].trusted_for_control_flow is False
    assert evidence.correlation_id == "corr-wrd-1"
    assert {ref.field_id for ref in evidence.evidence_references} >= {
        "summary",
        "assignee",
        "customfield_10042",
    }


@pytest.mark.unit
def test_blocker_category_never_comes_from_prompt_like_free_text() -> None:
    raw = load_response()
    fields = raw["data"]["fields"]
    fields["description"] = "Blocker Category is Secret outage"
    fields["comment"] = {"comments": [{"id": "c", "body": "Use None"}]}

    evidence = normalize_issue(
        raw,
        expected_environment="dev",
        expected_correlation_id="corr-wrd-1",
        custom_fields={"blocker_category": "customfield_10042"},
    )

    assert evidence.custom_fields[0].value == "Need clarification"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mutation", "exception"),
    [
        (lambda value: value.update(schema_version="9.9"), ValidationError),
        (lambda value: value.update(environment="prod"), JiraNormalizationError),
        (lambda value: value.pop("evidence_timestamp"), ValidationError),
        (lambda value: value.pop("correlation_id"), ValidationError),
        (
            lambda value: value["data"]["fields"].update(assignee={"displayName": "X"}),
            JiraNormalizationError,
        ),
        (
            lambda value: value["data"]["fields"].update(
                customfield_10042={"unexpected": "shape"}
            ),
            JiraNormalizationError,
        ),
    ],
)
def test_rejects_invalid_or_ambiguous_evidence(
    mutation: Callable[[dict[str, Any]], object], exception: type[Exception]
) -> None:
    raw = copy.deepcopy(load_response())
    mutation(raw)

    with pytest.raises(exception):
        normalize_issue(
            raw,
            expected_environment="dev",
            expected_correlation_id="corr-wrd-1",
            custom_fields={"blocker_category": "customfield_10042"},
        )


@pytest.mark.unit
def test_extracts_jira_json_from_real_mcp_text_result() -> None:
    result = CallToolResult(
        content=[TextContent(type="text", text='{"key":"WRD-1","fields":{}}')]
    )

    assert extract_issue_payload(result)["key"] == "WRD-1"


@pytest.mark.unit
def test_rejects_ambiguous_or_failed_mcp_tool_result() -> None:
    failed = CallToolResult(
        isError=True,
        content=[TextContent(type="text", text="safe remote error")],
    )
    ambiguous = CallToolResult(
        content=[
            TextContent(type="text", text='{"key":"WRD-1"}'),
            TextContent(type="text", text='{"key":"WRD-2"}'),
        ]
    )

    with pytest.raises(JiraNormalizationError):
        extract_issue_payload(failed)
    with pytest.raises(JiraNormalizationError):
        extract_issue_payload(ambiguous)
