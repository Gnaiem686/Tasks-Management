from __future__ import annotations

import uuid
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from workforce_risk.models import ConfidenceLevel
from workforce_risk.proposals.models import StoredSimulation

from workforce_persistence.models import ReassignmentSimulation


class SimulationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def persist(self, simulation: StoredSimulation) -> StoredSimulation:
        existing = await self.get(
            environment=simulation.environment,
            simulation_id=simulation.simulation_id,
        )
        if existing is not None:
            if existing != simulation:
                raise ValueError("simulation ID already has different immutable data")
            return existing
        self._session.add(
            ReassignmentSimulation(
                id=uuid.uuid4(),
                environment=simulation.environment,
                created_at=simulation.simulated_at,
                simulation_id=simulation.simulation_id,
                project_key=simulation.project_key,
                task_key=simulation.task_id,
                current_assignee=simulation.current_assignee_id,
                proposed_assignee=simulation.proposed_assignee_id,
                candidate_ids=list(simulation.candidate_ids),
                confidence=simulation.confidence.value,
                evidence_fingerprint=simulation.evidence_fingerprint,
                scoring_versions=list(simulation.scoring_model_versions),
                safe_payload=simulation.safe_payload,
            )
        )
        await self._session.flush()
        return simulation

    async def get(
        self, *, environment: str, simulation_id: str
    ) -> StoredSimulation | None:
        record = await self._session.scalar(
            select(ReassignmentSimulation).where(
                ReassignmentSimulation.environment == environment,
                ReassignmentSimulation.simulation_id == simulation_id,
            )
        )
        if record is None:
            return None
        return StoredSimulation(
            simulation_id=record.simulation_id,
            environment=cast(Literal["dev", "prod", "test"], record.environment),
            project_key=record.project_key,
            task_id=record.task_key,
            current_assignee_id=record.current_assignee,
            proposed_assignee_id=record.proposed_assignee,
            candidate_ids=tuple(record.candidate_ids),
            confidence=ConfidenceLevel(record.confidence),
            evidence_fingerprint=record.evidence_fingerprint,
            scoring_model_versions=tuple(record.scoring_versions),
            simulated_at=record.created_at,
            safe_payload=record.safe_payload,
        )
