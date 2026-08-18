from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from workforce_persistence.models import EvidenceSnapshot, RiskResultRecord
from workforce_risk.models import RiskResult

from agent_api.risk_evidence import RiskEvidenceDossier


class HistoricalRiskContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    risk: RiskResult
    dossier: RiskEvidenceDossier
    previous_dossier: RiskEvidenceDossier | None = None


class DatabaseHistoricalEvidenceReader:
    def __init__(
        self,
        database: Any,
        *,
        environment: Literal["dev", "prod", "test"],
        today: Callable[[], date],
    ) -> None:
        self._database = database
        self._environment = environment
        self._today = today

    async def get_at(
        self,
        question: str,
        employee_id: str,
        project_key: str,
        correlation_id: str,
    ) -> HistoricalRiskContext:
        requested = parse_historical_date(question, today=self._today())
        cutoff = requested or self._today()
        end = datetime.combine(cutoff + timedelta(days=1), time.min, tzinfo=UTC)
        async with self._database.transaction() as session:
            rows = (
                await session.execute(
                    select(EvidenceSnapshot, RiskResultRecord)
                    .join(
                        RiskResultRecord,
                        RiskResultRecord.snapshot_id == EvidenceSnapshot.id,
                    )
                    .where(
                        EvidenceSnapshot.environment == self._environment,
                        EvidenceSnapshot.subject_type == "employee",
                        EvidenceSnapshot.subject_id == employee_id,
                        EvidenceSnapshot.observed_at < end,
                        RiskResultRecord.score_family == "employee_overload",
                    )
                    .order_by(EvidenceSnapshot.observed_at.desc())
                    .limit(50)
                )
            ).all()
        contexts: list[HistoricalRiskContext] = []
        for snapshot, record in rows:
            raw_dossier = snapshot.evidence.get("risk_evidence_dossier")
            if not raw_dossier:
                continue
            dossier = RiskEvidenceDossier.model_validate(raw_dossier)
            if dossier.project_key != project_key or dossier.employee_id != employee_id:
                raise ValueError("historical evidence scope mismatch")
            risk = RiskResult.model_validate(
                {
                    "subject_id": employee_id,
                    "environment": cast(str, snapshot.environment),
                    "score": record.score,
                    "level": record.level,
                    "confidence": record.confidence,
                    "scored_at": record.created_at,
                    "evidence_timestamp": snapshot.observed_at,
                    "scoring_model_version": record.scoring_version,
                    "factors": record.factors,
                    "thresholds": record.thresholds,
                    "evidence_references": record.evidence_references,
                    "missing_evidence": record.missing_evidence,
                    "excluded_evidence": record.excluded_evidence,
                }
            )
            contexts.append(HistoricalRiskContext(risk=risk, dossier=dossier))
            if requested is not None:
                return contexts[0]
            if len(contexts) == 2:
                return contexts[0].model_copy(
                    update={"previous_dossier": contexts[1].dossier}
                )
        raise ValueError("historical evidence is unavailable for the requested date")


class RiskEvidenceComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    earlier_observed_at: datetime
    later_observed_at: datetime
    remaining_hours_change: float | None
    new_task_keys: tuple[str, ...]
    removed_task_keys: tuple[str, ...]
    new_blocker_task_keys: tuple[str, ...]
    resolved_blocker_task_keys: tuple[str, ...]


def parse_historical_date(question: str, *, today: date) -> date | None:
    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", question)
    if iso:
        return date.fromisoformat(iso.group(0))
    months = {
        name: number
        for number, name in enumerate(
            (
                "january",
                "february",
                "march",
                "april",
                "may",
                "june",
                "july",
                "august",
                "september",
                "october",
                "november",
                "december",
            ),
            start=1,
        )
    }
    match = re.search(
        r"\b(" + "|".join(months) + r")\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b",
        question.casefold(),
    )
    if not match:
        return None
    return date(
        int(match.group(3) or today.year),
        months[match.group(1)],
        int(match.group(2)),
    )


def compare_dossiers(
    earlier: RiskEvidenceDossier, later: RiskEvidenceDossier
) -> RiskEvidenceComparison:
    earlier_tasks = {task.key for task in earlier.tasks}
    later_tasks = {task.key for task in later.tasks}
    remaining_change = (
        None
        if earlier.total_remaining_hours is None or later.total_remaining_hours is None
        else later.total_remaining_hours - earlier.total_remaining_hours
    )
    return RiskEvidenceComparison(
        earlier_observed_at=earlier.observed_at,
        later_observed_at=later.observed_at,
        remaining_hours_change=remaining_change,
        new_task_keys=tuple(sorted(later_tasks - earlier_tasks)),
        removed_task_keys=tuple(sorted(earlier_tasks - later_tasks)),
        new_blocker_task_keys=tuple(
            sorted(set(later.blocked_task_keys) - set(earlier.blocked_task_keys))
        ),
        resolved_blocker_task_keys=tuple(
            sorted(set(earlier.blocked_task_keys) - set(later.blocked_task_keys))
        ),
    )
