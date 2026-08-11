from datetime import datetime

from workforce_risk.models import RiskResult, TaskFitInput
from workforce_risk.scoring.config import ScoringConfiguration
from workforce_risk.scoring.family import score_normalized_family


def score_task_fit(
    input_data: TaskFitInput, config: ScoringConfiguration, scored_at: datetime
) -> RiskResult:
    values = {name: getattr(input_data, name) for name in config.task_fit.factors}
    return score_normalized_family(
        subject_id=input_data.task_id,
        environment=input_data.environment,
        values=values,
        evidence_references=input_data.evidence_references,
        evidence_timestamp=input_data.evidence_timestamp,
        scored_at=scored_at,
        config=config.task_fit,
        thresholds=config.thresholds,
    )
