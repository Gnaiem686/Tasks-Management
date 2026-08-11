from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from workforce_risk.reports.generator import DailyRiskReport, ReportRiskSummary


def report(recommendation: str = "Pair with a senior reviewer") -> DailyRiskReport:
    return DailyRiskReport(
        report_id="report-20260809",
        environment="dev",
        generated_at=datetime(2026, 8, 9, 7, 30, tzinfo=UTC),
        scope="WRD",
        generator_version="report-v1",
        risks=(
            ReportRiskSummary(
                subject_id="EMP-002",
                score_family="employee_overload",
                score=88,
                risk_level="critical",
                confidence="high",
                scoring_model_version="employee-overload-v1",
                evidence_references=("jira:WRD-1:status",),
                recommendations=(recommendation,),
            ),
        ),
    )


@pytest.mark.unit
def test_report_has_exact_key_stable_checksum_and_required_content() -> None:
    value = report()
    assert value.object_key == "reports/dev/2026/08/09/report-20260809.json"
    assert value.checksum == report().checksum
    assert b'"score":88' in value.canonical_bytes()
    assert b'"scoring_model_version":"employee-overload-v1"' in value.canonical_bytes()


@pytest.mark.unit
def test_report_rejects_secrets_and_raw_comment_material() -> None:
    for prohibited in ("Bearer token-value", "raw_comment: private text", "password=x"):
        with pytest.raises(ValidationError, match="prohibited"):
            report(prohibited)
