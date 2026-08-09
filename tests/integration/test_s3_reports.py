from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from workforce_persistence.database import Database
from workforce_persistence.models import ReportMetadata
from workforce_persistence.report_repository import ReportRepository
from workforce_risk.reports.generator import DailyRiskReport, ReportRiskSummary
from workforce_risk_mcp.tools.reports import ImmutableReportStore

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://workforce:workforce-local-only@127.0.0.1:5432/workforce",
)


class S3:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.objects: dict[str, bytes] = {}

    def put_object(self, **kwargs: object) -> dict[str, str]:
        if self.fail:
            raise TimeoutError("private S3 diagnostic")
        self.objects[str(kwargs["Key"])] = bytes(kwargs["Body"])  # type: ignore[arg-type]
        return {"VersionId": "version-1"}

    def generate_presigned_url(
        self, operation: str, Params: dict[str, object], ExpiresIn: int
    ) -> str:
        return f"https://signed.example/{Params['Key']}?version={Params['VersionId']}"


def report(report_id: str) -> DailyRiskReport:
    return DailyRiskReport(
        report_id=report_id,
        environment="test",
        generated_at=datetime.now(UTC),
        scope="WRD",
        generator_version="v1",
        risks=(
            ReportRiskSummary(
                subject_id="EMP-002",
                score_family="employee_overload",
                score=88,
                risk_level="critical",
                confidence="high",
                scoring_model_version="v1",
                evidence_references=("jira:WRD-1",),
            ),
        ),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_report_metadata_is_idempotent_and_exact_version_is_authorized() -> None:
    database = Database(DATABASE_URL)
    report_id = f"report-{uuid.uuid4()}"
    value = report(report_id)
    s3 = S3()
    store = ImmutableReportStore(client=s3, bucket="reports-test", environment="test")
    try:
        async with database.transaction() as session:
            repository = ReportRepository(session)
            first = await repository.create_pending(
                environment="test",
                report_type="daily",
                idempotency_key=report_id,
                created_at=datetime.now(UTC),
            )
            repeated = await repository.create_pending(
                environment="test",
                report_type="daily",
                idempotency_key=report_id,
                created_at=datetime.now(UTC),
            )
            assert first.id == repeated.id
            key, version, checksum = await store.upload(value)
            await repository.mark_stored(
                first.id, object_key=key, object_version=version, checksum=checksum
            )
        async with database.transaction() as session:
            record = await session.scalar(
                select(ReportMetadata).where(ReportMetadata.id == first.id)
            )
            assert record is not None and record.status == "stored"
            url = await store.authorized_download_url(
                object_key=str(record.object_key),
                object_version=str(record.object_version),
            )
            assert "version=version-1" in url
    finally:
        await database.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_upload_leaves_report_pending() -> None:
    database = Database(DATABASE_URL)
    report_id = f"failed-{uuid.uuid4()}"
    try:
        async with database.transaction() as session:
            record = await ReportRepository(session).create_pending(
                environment="test",
                report_type="daily",
                idempotency_key=report_id,
                created_at=datetime.now(UTC),
            )
        with pytest.raises(TimeoutError):
            await ImmutableReportStore(
                client=S3(fail=True), bucket="reports-test", environment="test"
            ).upload(report(report_id))
        async with database.transaction() as session:
            stored = await session.get(ReportMetadata, record.id)
            assert stored is not None and stored.status == "pending"
    finally:
        await database.close()
