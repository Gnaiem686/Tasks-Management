from __future__ import annotations

from typing import Literal

from agent_api.dashboard.models import DashboardSnapshot
from agent_api.evidence.models import (
    CandidateRankingResult,
    EvidenceCategory,
    MissingData,
    RankedCandidate,
    calculate_capacity,
)


def rank_reassignment_candidates(
    snapshot: DashboardSnapshot,
    *,
    source_employee_id: str,
) -> CandidateRankingResult:
    source = next(
        (item for item in snapshot.employees if item.employee_id == source_employee_id),
        None,
    )
    source_name = source.display_name.casefold() if source is not None else None
    required = {
        skill.lower()
        for task in snapshot.tasks
        if task.assignee_id == source_employee_id
        or (
            source_name is not None
            and (task.assignee_name or "").casefold() == source_name
        )
        for skill in task.required_skills
    }
    candidates: list[tuple[int, int, float, str, RankedCandidate]] = []
    missing_data: list[MissingData] = []
    for employee in snapshot.employees:
        if employee.employee_id == source_employee_id:
            continue
        capacity = calculate_capacity(
            employee.capacity_hours,
            employee.remaining_hours,
            employee_id=employee.employee_id,
        )
        documented = {skill.lower() for skill in employee.skills}
        matching = tuple(sorted(required & documented))
        missing = tuple(sorted(required - documented))
        eligible = (
            capacity is not None
            and capacity.capacity_headroom_hours > 0
            and not missing
        )
        role_folded = (employee.role or "").casefold()
        seniority = next(
            (
                level
                for level in ("lead", "senior", "mid", "junior")
                if level in role_folded
            ),
            None,
        )
        reasons = []
        if capacity is None:
            reasons.append("configured capacity is unavailable")
            missing_data.append(
                MissingData(
                    category=EvidenceCategory.CAPACITY_AND_WORKLOAD,
                    reason="configured candidate capacity is unavailable",
                    entity=f"employee:{employee.employee_id}",
                )
            )
        elif capacity.capacity_headroom_hours <= 0:
            reasons.append("no positive capacity headroom")
        if missing:
            reasons.append("missing required skills: " + ", ".join(missing))
        if required and not documented:
            missing_data.append(
                MissingData(
                    category=EvidenceCategory.SKILLS_AND_SENIORITY,
                    reason="documented candidate skills are unavailable",
                    entity=f"employee:{employee.employee_id}",
                )
            )
        if eligible:
            reasons.append("documented skills match and capacity headroom is positive")
        item = RankedCandidate(
            employee_id=employee.employee_id,
            display_name=employee.display_name,
            role=employee.role,
            seniority=seniority,
            rank=1,
            capacity_headroom_hours=(
                capacity.capacity_headroom_hours if capacity else None
            ),
            matching_skills=matching,
            missing_required_skills=missing,
            eligible=eligible,
            reasons=tuple(reasons),
        )
        candidates.append(
            (
                0 if eligible else 1,
                -len(matching),
                -(capacity.capacity_headroom_hours if capacity else -10_000),
                employee.employee_id,
                item,
            )
        )
    candidates.sort(key=lambda value: value[:4])
    ranked = tuple(
        item.model_copy(update={"rank": index})
        for index, (*_, item) in enumerate(candidates, start=1)
    )
    status: Literal["success", "insufficient_data", "no_candidates"]
    if any(item.eligible for item in ranked):
        status = "success"
    elif missing_data:
        status = "insufficient_data"
        ranked = ()
    else:
        status = "no_candidates"
    return CandidateRankingResult(
        status=status,
        candidates=ranked,
        missing_data=tuple(missing_data),
    )
