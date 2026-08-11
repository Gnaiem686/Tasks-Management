from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from workforce_contracts.jira import (
    EvidenceRef,
    JiraAccountRef,
    JiraCustomFieldValue,
    JiraIssueEvidence,
    JiraIssueLink,
    JiraMcpEnvelope,
    UntrustedTextEvidence,
)


class JiraNormalizationError(ValueError):
    """The Jira response is unsafe or ambiguous to normalize."""


def _single_label_value(labels: list[str], prefix: str) -> str | None:
    values = [
        label.removeprefix(prefix) for label in labels if label.startswith(prefix)
    ]
    if len(values) > 1:
        label_name = prefix.rstrip(":").replace("-", " ")
        raise JiraNormalizationError(f"multiple {label_name} labels")
    return values[0] if values else None


def _structured_labels(fields: Mapping[str, Any]) -> dict[str, Any]:
    raw_labels = fields.get("labels", [])
    if not isinstance(raw_labels, list) or not all(
        isinstance(label, str) for label in raw_labels
    ):
        raise JiraNormalizationError("labels must be a list of strings")
    labels: list[str] = raw_labels
    employee_id = _single_label_value(labels, "workforce-employee:")
    if employee_id is not None and employee_id not in {
        f"EMP-{number:03d}" for number in range(1, 8)
    }:
        raise JiraNormalizationError("workforce employee label is not allowlisted")

    def hours(prefix: str) -> int | None:
        value = _single_label_value(labels, prefix)
        if value is None:
            return None
        try:
            parsed = float(value)
        except ValueError as exc:
            raise JiraNormalizationError(f"{prefix} must contain hours") from exc
        if parsed < 0:
            raise JiraNormalizationError(f"{prefix} cannot be negative")
        return round(parsed * 3600)

    difficulty_value = _single_label_value(labels, "workforce-difficulty:")
    difficulty = None
    if difficulty_value is not None:
        try:
            difficulty = int(difficulty_value)
        except ValueError as exc:
            raise JiraNormalizationError("difficulty label must be an integer") from exc
        if difficulty not in range(1, 6):
            raise JiraNormalizationError("difficulty label must be between 1 and 5")
    skills = tuple(
        sorted(
            label.removeprefix("workforce-skill:")
            for label in labels
            if label.startswith("workforce-skill:")
        )
    )
    complete = "workforce-evidence:complete" in labels
    incomplete = "workforce-evidence:incomplete" in labels
    if complete and incomplete:
        raise JiraNormalizationError("evidence completeness labels conflict")
    return {
        "employee_id": employee_id,
        "original_estimate_seconds": hours("workforce-estimate-hours:"),
        "remaining_estimate_seconds": hours("workforce-remaining-hours:"),
        "difficulty": difficulty,
        "skills": skills,
        "complete": True if complete else False if incomplete else None,
    }


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise JiraNormalizationError(f"{label} must be an object")
    return value


def _named(value: object, label: str) -> str:
    obj = _object(value, label)
    name = obj.get("name")
    if not isinstance(name, str) or not name:
        raise JiraNormalizationError(f"{label}.name must be a non-empty string")
    return name


def _untrusted(fields: Mapping[str, Any]) -> tuple[UntrustedTextEvidence, ...]:
    values: list[UntrustedTextEvidence] = []
    description = fields.get("description")
    if description is not None:
        text = description if isinstance(description, str) else json.dumps(description)
        values.append(UntrustedTextEvidence(source_field="description", text=text))
    comment_page = fields.get("comment")
    if isinstance(comment_page, Mapping):
        comments = comment_page.get("comments", [])
        if isinstance(comments, list):
            for comment in comments:
                if isinstance(comment, Mapping) and comment.get("body") is not None:
                    body = comment["body"]
                    text = body if isinstance(body, str) else json.dumps(body)
                    values.append(
                        UntrustedTextEvidence(source_field="comment", text=text)
                    )
    return tuple(values)


def _links(fields: Mapping[str, Any]) -> tuple[JiraIssueLink, ...]:
    raw_links = fields.get("issuelinks", [])
    if not isinstance(raw_links, list):
        raise JiraNormalizationError("issuelinks must be a list")
    links: list[JiraIssueLink] = []
    for raw_link in raw_links:
        link = _object(raw_link, "issue link")
        link_type = _object(link.get("type"), "issue link type")
        inward = "inwardIssue" in link
        target = _object(
            link.get("inwardIssue" if inward else "outwardIssue"), "linked issue"
        )
        relationship = link_type.get("inward" if inward else "outward")
        key = target.get("key")
        if not isinstance(relationship, str) or not isinstance(key, str):
            raise JiraNormalizationError("issue link requires relationship and key")
        links.append(JiraIssueLink(relationship=relationship, issue_key=key))
    return tuple(links)


def normalize_issue(
    raw: Mapping[str, Any],
    *,
    expected_environment: str,
    expected_correlation_id: str,
    custom_fields: Mapping[str, str],
) -> JiraIssueEvidence:
    envelope = JiraMcpEnvelope.model_validate(raw)
    if envelope.environment != expected_environment:
        raise JiraNormalizationError("MCP response environment mismatch")
    if envelope.correlation_id != expected_correlation_id:
        raise JiraNormalizationError("MCP response correlation ID mismatch")
    if envelope.status != "success" or envelope.data is None:
        raise JiraNormalizationError(envelope.error or "Jira MCP read failed")

    issue = _object(envelope.data, "issue")
    fields = _object(issue.get("fields"), "issue fields")
    key, summary, updated = (
        issue.get("key"),
        fields.get("summary"),
        fields.get("updated"),
    )
    if not all(isinstance(value, str) and value for value in (key, summary, updated)):
        raise JiraNormalizationError("issue key, summary, and updated are required")
    assert isinstance(key, str)
    assert isinstance(summary, str)
    assert isinstance(updated, str)

    assignee = None
    if fields.get("assignee") is not None:
        assignee_raw = _object(fields["assignee"], "assignee")
        try:
            assignee = JiraAccountRef(
                account_id=assignee_raw["accountId"],
                display_name=assignee_raw["displayName"],
                account_type=assignee_raw.get("accountType"),
                active=assignee_raw.get("active"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise JiraNormalizationError("assignee has an invalid shape") from exc

    normalized_custom: list[JiraCustomFieldValue] = []
    for logical_name, raw_id in custom_fields.items():
        raw_value = _object(fields.get(raw_id), raw_id)
        if "value" not in raw_value or isinstance(raw_value["value"], (dict, list)):
            raise JiraNormalizationError(f"{raw_id} has an unsupported shape")
        normalized_custom.append(
            JiraCustomFieldValue(
                logical_name=logical_name,
                raw_field_id=raw_id,
                value=raw_value["value"],
            )
        )

    structured_labels = _structured_labels(fields)
    field_ids = [
        "summary",
        "status",
        "priority",
        "assignee",
        "duedate",
        "updated",
        "labels",
    ]
    field_ids.extend(custom_fields.values())
    references = tuple(
        EvidenceRef(
            issue_key=key,
            field_id=field_id,
            observed_at=envelope.evidence_timestamp,
        )
        for field_id in field_ids
        if fields.get(field_id) is not None
    )
    return JiraIssueEvidence(
        environment=envelope.environment,
        correlation_id=envelope.correlation_id,
        evidence_timestamp=envelope.evidence_timestamp,
        key=key,
        summary=summary,
        status=_named(fields.get("status"), "status"),
        priority=_named(fields["priority"], "priority")
        if fields.get("priority")
        else None,
        assignee=assignee,
        due_date=fields.get("duedate"),
        original_estimate_seconds=(
            fields.get("timeoriginalestimate")
            if fields.get("timeoriginalestimate") is not None
            else structured_labels["original_estimate_seconds"]
        ),
        remaining_estimate_seconds=(
            fields.get("timeestimate")
            if fields.get("timeestimate") is not None
            else structured_labels["remaining_estimate_seconds"]
        ),
        workforce_employee_id=structured_labels["employee_id"],
        difficulty=structured_labels["difficulty"],
        required_skills=structured_labels["skills"],
        structured_evidence_complete=structured_labels["complete"],
        activity_timestamp=datetime.fromisoformat(updated.replace("Z", "+00:00")),
        links=_links(fields),
        custom_fields=tuple(normalized_custom),
        evidence_references=references,
        untrusted_text=_untrusted(fields),
    )
