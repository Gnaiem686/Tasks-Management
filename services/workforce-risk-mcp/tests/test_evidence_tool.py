from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

import pytest
from workforce_risk.evidence.fingerprint import EvidenceFingerprintInput
from workforce_risk.evidence.snapshot import VersionedEvidenceSnapshot
from workforce_risk_mcp.tools.evidence import PersistEvidenceRequest, persist_evidence

NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


class Repository:
    def __init__(self) -> None:
        self.received: VersionedEvidenceSnapshot | None = None

    async def persist(
        self,
        snapshot: VersionedEvidenceSnapshot,
        *,
        subject_type: str,
        service_environment: str | None = None,
    ) -> UUID:
        self.received = snapshot
        assert subject_type == "task"
        assert service_environment == "dev"
        return UUID("00000000-0000-0000-0000-000000000123")


def request(
    environment: Literal["dev", "prod", "test"] = "dev",
) -> PersistEvidenceRequest:
    return PersistEvidenceRequest.model_validate(
        {
            "schema_version": "1.0",
            "environment": environment,
            "correlation_id": "corr-evidence-tool",
            "subject_type": "task",
            "snapshot": {
                "evidence": EvidenceFingerprintInput(
                    schema_version="1.0",
                    environment=environment,
                    subject_id="WRD-10",
                    task_state="In Progress",
                    employee_workloads={"EMP-001": 20},
                    due_date=date(2026, 8, 15),
                    scoring_versions=("task-fit-v1",),
                    evidence_timestamp=NOW,
                ).model_dump(mode="json"),
                "risk_results": [],
            },
        }
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evidence_tool_persists_typed_snapshot_and_returns_fingerprint() -> None:
    repository = Repository()
    response = await persist_evidence(
        request(), repository=repository, service_environment="dev"
    )
    assert response.snapshot_id.endswith("0123")
    assert repository.received is not None
    assert response.fingerprint == repository.received.fingerprint
    assert response.correlation_id == "corr-evidence-tool"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evidence_tool_rejects_environment_mismatch() -> None:
    with pytest.raises(ValueError, match="environment"):
        await persist_evidence(
            request("dev"), repository=Repository(), service_environment="prod"
        )
