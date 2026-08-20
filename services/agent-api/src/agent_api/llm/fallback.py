from __future__ import annotations

from agent_api.historical_evidence import compare_dossiers
from agent_api.llm.schemas import (
    ExplanationRequest,
    ExplanationResponse,
    Recommendation,
)


class DeterministicFallbackProvider:
    async def explain(self, request: ExplanationRequest) -> ExplanationResponse:
        risk = request.risk
        if risk is None:
            raise ValueError("deterministic fallback requires a risk result")
        if risk.score is None:
            summary = (
                "There is insufficient structured evidence to calculate this risk."
            )
        else:
            summary = (
                f"The deterministic {risk.scoring_model_version} result is "
                f"{risk.score}/100 ({risk.level.value if risk.level else 'unknown'})."
            )
        dossier = request.evidence_dossier
        if dossier is not None:
            details: list[str] = []
            previous = request.previous_evidence_dossier
            if request.workflow == "explain_history" and previous is None:
                details.append(
                    "I cannot determine whether the situation improved because "
                    "only one detailed risk snapshot is available. Run another "
                    "scan after the Jira situation changes to create a comparison."
                )
            if previous is not None:
                comparison = compare_dossiers(previous, dossier)
                if comparison.remaining_hours_change is not None:
                    direction = (
                        "decreased"
                        if comparison.remaining_hours_change < 0
                        else "increased"
                    )
                    details.append(
                        f"Remaining work {direction} by "
                        f"{abs(comparison.remaining_hours_change):.1f} hours between "
                        f"{comparison.earlier_observed_at.date().isoformat()} and "
                        f"{comparison.later_observed_at.date().isoformat()}."
                    )
                if comparison.resolved_blocker_task_keys:
                    details.append(
                        ", ".join(comparison.resolved_blocker_task_keys)
                        + " was unblocked."
                    )
            if dossier.total_remaining_hours is not None:
                details.append(
                    f"The employee has {dossier.total_remaining_hours:.1f} remaining "
                    f"hours against {dossier.available_capacity_hours:.1f} "
                    "available hours."
                )
            for task in dossier.tasks:
                facts = [f"{task.key} ({task.summary})"]
                if task.due_date is not None:
                    if task.key in dossier.overdue_task_keys:
                        facts.append(f"is overdue since {task.due_date.isoformat()}")
                    else:
                        facts.append(f"is due {task.due_date.isoformat()}")
                if task.remaining_hours is not None:
                    facts.append(f"has {task.remaining_hours:.1f} hours remaining")
                if task.blocker_category:
                    facts.append(f"is blocked by {task.blocker_category}")
                if task.dependencies:
                    facts.append("and has dependencies " + ", ".join(task.dependencies))
                details.append("; ".join(facts) + ".")
            summary = " ".join((summary, *details))
        causes = tuple(
            f"{factor.name} contributed {factor.contribution_points:.1f} points."
            for factor in sorted(
                risk.factors, key=lambda item: item.contribution_points, reverse=True
            )[:3]
        )
        uncertainties = tuple(f"Missing: {name}" for name in risk.missing_evidence)
        return ExplanationResponse(
            answer=summary,
            summary=summary,
            root_causes=causes,
            recommendations=(
                Recommendation(
                    action="review",
                    reason="Review the cited structured evidence before deciding.",
                ),
            ),
            citations=tuple(
                dict.fromkeys(
                    (
                        *risk.evidence_references,
                        *(dossier.evidence_references if dossier else ()),
                    )
                )
            ),
            score=risk.score,
            risk_level=risk.level.value if risk.level else None,
            uncertainties=uncertainties,
            source="deterministic_fallback",
            correlation_id=request.correlation_id,
        )
