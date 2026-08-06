from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class JiraMcpEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    environment: Literal["dev", "prod", "test"]
    correlation_id: str = Field(min_length=1)
    evidence_timestamp: AwareDatetime
    status: Literal["success", "error"]
    data: dict[str, Any] | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> JiraMcpEnvelope:
        if self.status == "success" and self.data is None:
            raise ValueError("successful MCP response requires data")
        if self.status == "error" and not self.error:
            raise ValueError("failed MCP response requires an error")
        return self


class JiraAccountRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    account_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    account_type: str | None = None
    active: bool | None = None


class JiraCustomFieldValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    logical_name: str
    raw_field_id: str
    value: str | int | float | bool | None


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: Literal["jira"] = "jira"
    issue_key: str
    field_id: str
    observed_at: AwareDatetime


class JiraIssueLink(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    relationship: str
    issue_key: str


class UntrustedTextEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_field: str
    text: str
    trusted_for_control_flow: Literal[False] = False


class JiraIssueEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    environment: Literal["dev", "prod", "test"]
    correlation_id: str
    evidence_timestamp: AwareDatetime
    key: str
    summary: str
    status: str
    priority: str | None
    assignee: JiraAccountRef | None
    due_date: date | None
    original_estimate_seconds: int | None
    remaining_estimate_seconds: int | None
    activity_timestamp: datetime
    links: tuple[JiraIssueLink, ...] = ()
    custom_fields: tuple[JiraCustomFieldValue, ...] = ()
    evidence_references: tuple[EvidenceRef, ...] = ()
    untrusted_text: tuple[UntrustedTextEvidence, ...] = ()
