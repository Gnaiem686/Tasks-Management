from __future__ import annotations

from datetime import datetime

from workforce_risk.models import (
    ConfidenceLevel,
    EmployeeOverloadInput,
    FactorContribution,
    RiskLevel,
    RiskResult,
)
from workforce_risk.scoring.common import clamp, normalize_capped
from workforce_risk.scoring.config import ScoringConfiguration

FACTOR_INPUTS = {
    "overdue_work": "overdue_tasks",
    "blocked_work": "blocked_or_blocking_tasks",
    "priority_load": "urgent_high_priority_tasks",
    "due_soon_load": "due_soon_tasks",
    "active_task_count": "active_tasks",
    "concurrent_projects": "concurrent_projects",
    "stale_work": "stale_tasks",
}


def risk_level_for_score(score: int) -> RiskLevel:
    if not 0 <= score <= 100:
        raise ValueError("risk score must be between 0 and 100")
    if score <= 29:
        return RiskLevel.LOW
    if score <= 54:
        return RiskLevel.MEDIUM
    if score <= 74:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


def _confidence(coverage: float) -> ConfidenceLevel:
    if coverage >= 0.9:
        return ConfidenceLevel.HIGH
    if coverage >= 0.75:
        return ConfidenceLevel.MEDIUM
    if coverage >= 0.6:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.INSUFFICIENT_DATA


def _insufficient(
    input_data: EmployeeOverloadInput,
    config: ScoringConfiguration,
    scored_at: datetime,
    *,
    missing: tuple[str, ...] = (),
    excluded: tuple[str, ...] = (),
) -> RiskResult:
    return RiskResult(
        subject_id=input_data.employee_id,
        environment=input_data.environment,
        score=None,
        level=None,
        confidence=ConfidenceLevel.INSUFFICIENT_DATA,
        scored_at=scored_at,
        evidence_timestamp=input_data.evidence_timestamp,
        scoring_model_version=config.employee_overload.version,
        factors=(),
        thresholds=config.thresholds,
        evidence_references=(),
        missing_evidence=missing,
        excluded_evidence=excluded,
    )


def score_employee_overload(
    input_data: EmployeeOverloadInput,
    config: ScoringConfiguration,
    scored_at: datetime,
) -> RiskResult:
    missing_mandatory = tuple(
        name
        for name in ("remaining_estimated_hours", "available_capacity_hours")
        if getattr(input_data, name) is None
    )
    if missing_mandatory:
        return _insufficient(input_data, config, scored_at, missing=missing_mandatory)

    age_hours = (scored_at - input_data.evidence_timestamp).total_seconds() / 3600
    if age_hours > config.employee_overload.max_evidence_age_hours:
        return _insufficient(
            input_data, config, scored_at, excluded=("stale_evidence",)
        )

    remaining = input_data.remaining_estimated_hours
    capacity = input_data.available_capacity_hours
    assert remaining is not None and capacity is not None
    raw_values: dict[str, float | None] = {
        "utilization": remaining / capacity,
        **{
            factor: getattr(input_data, attribute)
            for factor, attribute in FACTOR_INPUTS.items()
        },
    }
    factors: list[FactorContribution] = []
    missing: list[str] = []
    coverage = 0.0
    for name, factor_config in config.employee_overload.factors.items():
        raw_value = raw_values.get(name)
        references = input_data.evidence_references.get(name, ())
        if raw_value is None or not references:
            missing.append(FACTOR_INPUTS.get(name, name))
            continue
        normalized = normalize_capped(float(raw_value), factor_config.normalization_cap)
        coverage += factor_config.weight
        factors.append(
            FactorContribution(
                name=name,
                raw_value=float(raw_value),
                normalized_value=normalized,
                weight=factor_config.weight,
                direction=factor_config.direction,
                contribution_points=normalized * factor_config.weight * 100,
                evidence_references=references,
            )
        )

    confidence = _confidence(coverage)
    if confidence is ConfidenceLevel.INSUFFICIENT_DATA:
        return _insufficient(input_data, config, scored_at, missing=tuple(missing))
    raw_score = sum(factor.contribution_points for factor in factors)
    score = round(clamp(raw_score, 0, 100))
    references = tuple(
        sorted(
            {
                reference
                for factor in factors
                for reference in factor.evidence_references
            }
        )
    )
    return RiskResult(
        subject_id=input_data.employee_id,
        environment=input_data.environment,
        score=score,
        level=risk_level_for_score(score),
        confidence=confidence,
        scored_at=scored_at,
        evidence_timestamp=input_data.evidence_timestamp,
        scoring_model_version=config.employee_overload.version,
        factors=tuple(factors),
        thresholds=config.thresholds,
        evidence_references=references,
        missing_evidence=tuple(missing),
        excluded_evidence=(),
    )
