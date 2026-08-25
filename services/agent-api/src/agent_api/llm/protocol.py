from __future__ import annotations

from typing import Protocol

from agent_api.llm.schemas import ExplanationRequest, ExplanationResponse


class ExplanationProvider(Protocol):
    async def explain(self, request: ExplanationRequest) -> ExplanationResponse: ...
