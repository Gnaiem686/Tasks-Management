from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field
from workforce_contracts.auth import ApplicationRole
from workforce_risk.models import RiskResult

from agent_api.graph.intents import Intent
from agent_api.llm.schemas import ExplanationResponse


class VerifiedAgentContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subject_reference: str = Field(min_length=1, max_length=128)
    roles: tuple[ApplicationRole, ...] = Field(min_length=1, max_length=3)
    environment: Literal["dev", "prod", "test"]
    authorized_jira_sites: tuple[str, ...] = Field(min_length=1, max_length=5)
    authorized_project_keys: tuple[str, ...] = Field(min_length=1, max_length=20)
    correlation_id: str = Field(min_length=1, max_length=128)


class EntityReferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    alert_id: str | None = Field(default=None, max_length=128)
    employee_id: str | None = Field(default=None, max_length=128)
    project_id: str | None = Field(default=None, max_length=128)
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,19}$")
    task_id: str | None = Field(default=None, max_length=128)
    risk_result_id: str | None = Field(default=None, max_length=128)
    proposal_id: str | None = Field(default=None, max_length=128)


class GraphState(TypedDict):
    verified_context: VerifiedAgentContext
    question: str
    references: EntityReferences
    steps_used: int
    tool_calls_used: int
    intent: NotRequired[Intent]
    risk: NotRequired[RiskResult]
    explanation: NotRequired[ExplanationResponse]
    capability_guidance: NotRequired[str]
    missing_sources: NotRequired[tuple[str, ...]]


class InvestigationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1.0"
    correlation_id: str
    intent: Intent
    risk: RiskResult | None = None
    explanation: ExplanationResponse | None = None
    capability_guidance: str | None = None
    missing_sources: tuple[str, ...] = ()
    steps_used: int
    tool_calls_used: int
