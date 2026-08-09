from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict
from workforce_risk.models import RiskResult

from agent_api.graph.intents import Intent
from agent_api.graph.state import EntityReferences, VerifiedAgentContext


class SpecialistUnavailable(RuntimeError):
    pass


class DomainTool(Protocol):
    async def investigate(
        self,
        intent: Intent,
        references: EntityReferences,
        correlation_id: str,
    ) -> RiskResult: ...


class AgentHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1.0"
    specialist: str
    intent: Intent
    context: VerifiedAgentContext
    references: EntityReferences
    evidence_references: tuple[str, ...] = ()
    evidence_timestamp: AwareDatetime | None = None
    correlation_id: str


class HandoffTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    specialist: str
    intent: Intent
    correlation_id: str
    status: Literal["completed", "fallback", "unavailable"]


class SpecialistAgent(Protocol):
    name: str

    def supports(self, intent: Intent) -> bool: ...

    async def run(self, handoff: AgentHandoff, tool: DomainTool) -> RiskResult: ...


WRITE_ORIENTED_PREPARATION = {
    Intent.REASSIGNMENT_CANDIDATES,
    Intent.WHAT_IF_SIMULATION,
}


class SpecialistRouter:
    def __init__(
        self,
        *,
        core_tool: DomainTool,
        specialists: tuple[SpecialistAgent, ...],
        context: VerifiedAgentContext,
    ) -> None:
        self._core_tool = core_tool
        self._specialists = specialists
        self._context = context
        self.trace: list[HandoffTrace] = []

    async def investigate(
        self,
        intent: Intent,
        references: EntityReferences,
        correlation_id: str,
    ) -> RiskResult:
        specialist = next(
            (
                candidate
                for candidate in self._specialists
                if candidate.supports(intent)
            ),
            None,
        )
        if specialist is None:
            return await self._core_tool.investigate(intent, references, correlation_id)
        handoff = AgentHandoff(
            specialist=specialist.name,
            intent=intent,
            context=self._context,
            references=references,
            evidence_timestamp=None,
            correlation_id=correlation_id,
        )
        try:
            result = await specialist.run(handoff, self._core_tool)
        except SpecialistUnavailable:
            if intent in WRITE_ORIENTED_PREPARATION:
                self.trace.append(
                    HandoffTrace(
                        specialist=specialist.name,
                        intent=intent,
                        correlation_id=correlation_id,
                        status="unavailable",
                    )
                )
                raise
            result = await self._core_tool.investigate(
                intent, references, correlation_id
            )
            status: Literal["completed", "fallback", "unavailable"] = "fallback"
        else:
            status = "completed"
        self.trace.append(
            HandoffTrace(
                specialist=specialist.name,
                intent=intent,
                correlation_id=correlation_id,
                status=status,
            )
        )
        return result


def evidence_time(result: RiskResult) -> datetime:
    return result.evidence_timestamp
