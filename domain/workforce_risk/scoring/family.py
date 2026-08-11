from __future__ import annotations

from datetime import datetime
from typing import Literal

from workforce_risk.models import ConfidenceLevel, FactorContribution, RiskResult
from workforce_risk.scoring.common import clamp
from workforce_risk.scoring.confidence import confidence_for_coverage
from workforce_risk.scoring.config import ScoreFamilyConfiguration
from workforce_risk.scoring.overload import risk_level_for_score


def score_normalized_family(
    *,
    subject_id: str,
    environment: Literal["dev", "prod", "test"],
    values: dict[str, float | None],
    evidence_references: dict[str, tuple[str, ...]],
    evidence_timestamp: datetime,
    scored_at: datetime,
    config: ScoreFamilyConfiguration,
    thresholds: dict[str, int],
) -> RiskResult:
    if (
        scored_at - evidence_timestamp
    ).total_seconds() / 3600 > config.max_evidence_age_hours:
        return _insufficient(
            subject_id,
            environment,
            evidence_timestamp,
            scored_at,
            config,
            thresholds,
            (),
            ("stale_evidence",),
        )
    factors: list[FactorContribution] = []
    missing: list[str] = []
    coverage = 0.0
    for name, settings in config.factors.items():
        value = values.get(name)
        references = evidence_references.get(name, ())
        if value is None or not references:
            missing.append(name)
            continue
        risk_value = (
            1 - value if settings.direction in {"inverse_risk", "protective"} else value
        )
        coverage += settings.weight
        factors.append(
            FactorContribution(
                name=name,
                raw_value=value,
                normalized_value=risk_value,
                weight=settings.weight,
                direction=settings.direction,
                contribution_points=risk_value * settings.weight * 100,
                evidence_references=references,
            )
        )
    confidence = confidence_for_coverage(coverage)
    if confidence is ConfidenceLevel.INSUFFICIENT_DATA:
        return _insufficient(
            subject_id,
            environment,
            evidence_timestamp,
            scored_at,
            config,
            thresholds,
            tuple(missing),
            (),
        )
    score = round(clamp(sum(item.contribution_points for item in factors), 0, 100))
    references = tuple(
        sorted({ref for factor in factors for ref in factor.evidence_references})
    )
    return RiskResult(
        subject_id=subject_id,
        environment=environment,
        score=score,
        level=risk_level_for_score(score),
        confidence=confidence,
        scored_at=scored_at,
        evidence_timestamp=evidence_timestamp,
        scoring_model_version=config.version,
        factors=tuple(factors),
        thresholds=thresholds,
        evidence_references=references,
        missing_evidence=tuple(missing),
        excluded_evidence=(),
    )


def _insufficient(
    subject_id: str,
    environment: Literal["dev", "prod", "test"],
    evidence_timestamp: datetime,
    scored_at: datetime,
    config: ScoreFamilyConfiguration,
    thresholds: dict[str, int],
    missing: tuple[str, ...],
    excluded: tuple[str, ...],
) -> RiskResult:
    return RiskResult(
        subject_id=subject_id,
        environment=environment,
        score=None,
        level=None,
        confidence=ConfidenceLevel.INSUFFICIENT_DATA,
        scored_at=scored_at,
        evidence_timestamp=evidence_timestamp,
        scoring_model_version=config.version,
        factors=(),
        thresholds=thresholds,
        evidence_references=(),
        missing_evidence=missing,
        excluded_evidence=excluded,
    )
