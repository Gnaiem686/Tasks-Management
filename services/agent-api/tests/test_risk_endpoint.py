from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from agent_api.auth.roles import ApplicationRole
from agent_api.dependencies import (
    EvidenceBundle,
    FixtureEvidenceProvider,
    JiraEvidenceTimeout,
    SingleIssueJiraEvidenceProvider,
    WorkforceScoringClient,
    get_evidence_provider,
    get_scoring_client,
)
from agent_api.main import app
from agent_api.routes.investigations import get_investigator
from httpx import ASGITransport, AsyncClient, Response
from jira_mcp_client.normalize import normalize_issue
from workforce_contracts.auth import AuthenticatedPrincipal
from workforce_risk.models import EmployeeOverloadInput

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "tests/fixtures/scenarios/overloaded_employee.json"


class EvidenceProvider:
    def __init__(self, *, degraded: bool = False, timeout: bool = False) -> None:
        self.degraded = degraded
        self.timeout = timeout
        self.correlation_id: str | None = None

    async def get_employee_overload(
        self, employee_id: str, project_key: str, correlation_id: str
    ) -> EvidenceBundle:
        self.correlation_id = correlation_id
        if self.timeout:
            raise JiraEvidenceTimeout("private diagnostic")
        return EvidenceBundle(
            input=EmployeeOverloadInput.model_validate_json(FIXTURE.read_text()),
            degraded=self.degraded,
            missing_sources=("jira_current_activity",) if self.degraded else (),
        )


class ScoringClient(WorkforceScoringClient):
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.correlation_id: str | None = None
        self.response = response or {
            "subject_id": "EMP-002",
            "environment": "dev",
            "score": 88,
            "level": "critical",
            "confidence": "high",
            "scored_at": "2026-08-06T12:00:00Z",
            "evidence_timestamp": "2026-08-06T10:00:00Z",
            "scoring_model_version": "employee-overload-v1",
            "factors": [],
            "thresholds": {"low_max": 29, "medium_max": 54, "high_max": 74},
            "evidence_references": ["profile:EMP-002:capacity"],
            "missing_evidence": [],
            "excluded_evidence": [],
        }

    async def score(
        self, input_data: EmployeeOverloadInput, correlation_id: str
    ) -> dict[str, Any]:
        self.correlation_id = correlation_id
        return self.response


@pytest.fixture(autouse=True)
def clear_overrides() -> Generator[None, None, None]:
    app.dependency_overrides.clear()
    app.dependency_overrides[get_investigator] = dependency_returning(
        AuthenticatedPrincipal(
            actor_id="viewer-test",
            display_label="Viewer",
            role=ApplicationRole.VIEWER,
            environment="test",
            project_scopes=("WRD",),
        )
    )
    yield
    app.dependency_overrides.clear()


async def api_get(path: str, headers: dict[str, str] | None = None) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path, headers=headers)


def dependency_returning(value: Any) -> Any:
    async def dependency() -> Any:
        return value

    return dependency


class JiraClient:
    async def get_issue(self, issue_key: str, *, correlation_id: str) -> Any:
        raw = json.loads(
            (ROOT / "tests/fixtures/jira/wrd_1_structured.json").read_text()
        )
        raw["data"]["fields"]["labels"] = ["workforce-workload-profile:critical"]
        raw["correlation_id"] = correlation_id
        return normalize_issue(
            raw,
            expected_environment="dev",
            expected_correlation_id=correlation_id,
            custom_fields={"blocker_category": "customfield_10042"},
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_jira_provider_converts_structured_issue_without_using_free_text() -> (
    None
):
    provider = SingleIssueJiraEvidenceProvider(
        jira_client=JiraClient(),
        employee_issue_keys={"EMP-002": "WRD-1"},
        employee_capacity_hours={"EMP-002": 40},
        environment="dev",
    )

    bundle = await provider.get_employee_overload(
        "EMP-002", "WRD", "corr-jira-provider"
    )

    assert bundle.input.remaining_estimated_hours == 4
    assert bundle.input.available_capacity_hours == 40
    assert bundle.input.blocked_or_blocking_tasks == 3
    assert bundle.input.active_tasks == 10
    assert bundle.input.concurrent_projects == 4
    assert "Ignore all prior instructions" not in json.dumps(
        bundle.input.model_dump(mode="json")
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fixture_provider_preserves_selected_synthetic_employee_id() -> None:
    provider = FixtureEvidenceProvider(
        ROOT / "tests/fixtures/scenarios", environment="dev"
    )

    bundle = await provider.get_employee_overload("EMP-007", "WRD", "corr-fixture")

    assert bundle.input.employee_id == "EMP-007"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_overload_endpoint_returns_typed_result_and_propagates_correlation() -> (
    None
):
    evidence = EvidenceProvider()
    scoring = ScoringClient()
    app.dependency_overrides[get_evidence_provider] = dependency_returning(evidence)
    app.dependency_overrides[get_scoring_client] = dependency_returning(scoring)

    response = await api_get(
        "/api/v1/employees/EMP-002/overload-risk?project_key=WRD",
        headers={"X-Correlation-ID": "corr-api-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-api-test"
    assert response.json()["result"]["score"] == 88
    assert response.json()["result"]["scoring_model_version"] == "employee-overload-v1"
    assert response.json()["degraded"] is False
    assert evidence.correlation_id == scoring.correlation_id == "corr-api-test"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_degraded_evidence_is_labeled_and_unpersisted() -> None:
    app.dependency_overrides[get_evidence_provider] = dependency_returning(
        EvidenceProvider(degraded=True)
    )
    app.dependency_overrides[get_scoring_client] = dependency_returning(ScoringClient())

    response = await api_get("/api/v1/employees/EMP-002/overload-risk?project_key=WRD")

    assert response.status_code == 200
    assert response.json()["degraded"] is True
    assert response.json()["persisted"] is False
    assert response.json()["missing_sources"] == ["jira_current_activity"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_jira_timeout_returns_safe_degraded_error_with_correlation() -> None:
    app.dependency_overrides[get_evidence_provider] = dependency_returning(
        EvidenceProvider(timeout=True)
    )
    app.dependency_overrides[get_scoring_client] = dependency_returning(ScoringClient())

    response = await api_get(
        "/api/v1/employees/EMP-002/overload-risk?project_key=WRD",
        headers={"X-Correlation-ID": "corr-timeout"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "error_code": "JIRA_EVIDENCE_UNAVAILABLE",
        "message": "Current evidence is unavailable; no risk claim was produced.",
        "correlation_id": "corr-timeout",
        "degraded": True,
    }
    assert "private diagnostic" not in response.text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_malformed_mcp_result_is_rejected_and_mutation_route_is_absent() -> None:
    app.dependency_overrides[get_evidence_provider] = dependency_returning(
        EvidenceProvider()
    )
    app.dependency_overrides[get_scoring_client] = dependency_returning(
        ScoringClient({"score": "invented"})
    )
    response = await api_get("/api/v1/employees/EMP-002/overload-risk?project_key=WRD")

    assert response.status_code == 502
    assert response.json()["error_code"] == "WORKFORCE_MCP_INVALID_RESPONSE"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.post("/api/v1/employees/EMP-002/reassign")
        ).status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_forbidden_project_fails_before_evidence_call() -> None:
    evidence = EvidenceProvider()
    app.dependency_overrides[get_evidence_provider] = dependency_returning(evidence)
    app.dependency_overrides[get_scoring_client] = dependency_returning(ScoringClient())

    response = await api_get(
        "/api/v1/employees/EMP-002/overload-risk?project_key=WORKFORCE-PROD"
    )

    assert response.status_code == 403
    assert evidence.correlation_id is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_insufficient_data_is_returned_without_numeric_claim() -> None:
    response_data = ScoringClient().response
    response_data.update(
        score=None,
        level=None,
        confidence="insufficient-data",
        missing_evidence=["available_capacity_hours"],
    )
    app.dependency_overrides[get_evidence_provider] = dependency_returning(
        EvidenceProvider()
    )
    app.dependency_overrides[get_scoring_client] = dependency_returning(
        ScoringClient(response_data)
    )

    response = await api_get("/api/v1/employees/EMP-002/overload-risk?project_key=WRD")

    assert response.status_code == 200
    assert response.json()["result"]["score"] is None
    assert response.json()["result"]["confidence"] == "insufficient-data"
