from workforce_risk.simulation.candidates import CandidateEvidence
from workforce_risk.simulation.service import (
    ReassignmentSimulation,
    ScoreFamilies,
    simulate_reassignment,
)


def run_reassignment_simulation(
    *,
    task_id: str,
    current_assignee_id: str,
    candidates: tuple[CandidateEvidence, ...],
    selected_employee_id: str,
    current_scores: ScoreFamilies,
) -> ReassignmentSimulation:
    """Pure domain delegation; performs no persistence or Jira mutation."""
    return simulate_reassignment(
        task_id=task_id,
        current_assignee_id=current_assignee_id,
        candidates=candidates,
        selected_employee_id=selected_employee_id,
        current_scores=current_scores,
    )
