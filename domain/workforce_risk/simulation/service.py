from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, model_validator

from workforce_risk.models import RiskResult
from workforce_risk.simulation.candidates import (
    CandidateEvidence,
    select_candidates,
)


class ScoreFamilies(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    employee_overload: RiskResult
    task_fit: RiskResult
    project_delivery: RiskResult


class ReassignmentSimulation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_id: str
    current_assignee_id: str
    proposed_assignee_id: str
    current: ScoreFamilies
    proposed: ScoreFamilies
    candidate_ids: tuple[str, ...]
    evidence_fingerprint: str

    @model_validator(mode="after")
    def same_scoring_rules(self) -> ReassignmentSimulation:
        current = self.current
        proposed = self.proposed
        pairs = (
            (current.employee_overload, proposed.employee_overload),
            (current.task_fit, proposed.task_fit),
            (current.project_delivery, proposed.project_delivery),
        )
        if any(a.scoring_model_version != b.scoring_model_version for a, b in pairs):
            raise ValueError("what-if states must use identical scoring versions")
        if self.proposed_assignee_id not in self.candidate_ids:
            raise ValueError("proposed assignee is not a selected candidate")
        return self


def simulate_reassignment(
    *,
    task_id: str,
    current_assignee_id: str,
    candidates: tuple[CandidateEvidence, ...],
    selected_employee_id: str,
    current_scores: ScoreFamilies,
) -> ReassignmentSimulation:
    assessments = select_candidates(candidates)
    eligible_ids = tuple(item.employee_id for item in assessments if item.eligible)
    selected = next(
        (
            item
            for item in candidates
            if item.profile.employee_id == selected_employee_id
        ),
        None,
    )
    if selected is None or selected_employee_id not in eligible_ids:
        raise ValueError("selected employee is not an eligible candidate")
    proposed = ScoreFamilies(
        employee_overload=selected.overload_risk,
        task_fit=selected.task_fit_risk,
        project_delivery=selected.predicted_project_risk,
    )
    material = {
        "task_id": task_id,
        "current_assignee_id": current_assignee_id,
        "proposed_assignee_id": selected_employee_id,
        "candidate_ids": eligible_ids,
        "current": current_scores.model_dump(mode="json"),
        "proposed": proposed.model_dump(mode="json"),
    }
    fingerprint = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ReassignmentSimulation(
        task_id=task_id,
        current_assignee_id=current_assignee_id,
        proposed_assignee_id=selected_employee_id,
        current=current_scores,
        proposed=proposed,
        candidate_ids=eligible_ids,
        evidence_fingerprint=fingerprint,
    )
