from __future__ import annotations

from agent_api.llm.schemas import (
    ExplanationRequest,
    ExplanationResponse,
    Recommendation,
)


class DeterministicFallbackProvider:
    async def explain(self, request: ExplanationRequest) -> ExplanationResponse:
        risk = request.risk
        if risk.score is None:
            summary = (
                "There is insufficient structured evidence to calculate this risk."
            )
        else:
            summary = (
                f"The deterministic {risk.scoring_model_version} result is "
                f"{risk.score}/100 ({risk.level.value if risk.level else 'unknown'})."
            )
        causes = tuple(
            f"{factor.name} contributed {factor.contribution_points:.1f} points."
            for factor in sorted(
                risk.factors, key=lambda item: item.contribution_points, reverse=True
            )[:3]
        )
        uncertainties = tuple(f"Missing: {name}" for name in risk.missing_evidence)
        return ExplanationResponse(
            summary=summary,
            root_causes=causes,
            recommendations=(
                Recommendation(
                    action="review",
                    reason="Review the cited structured evidence before deciding.",
                ),
            ),
            citations=risk.evidence_references,
            score=risk.score,
            risk_level=risk.level.value if risk.level else None,
            uncertainties=uncertainties,
            source="deterministic_fallback",
            correlation_id=request.correlation_id,
        )
