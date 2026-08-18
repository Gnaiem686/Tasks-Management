from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from workforce_persistence.database import Database
from workforce_persistence.models import ApiKeyPrincipal
from workforce_risk.models import RiskResult

from agent_api.auth.api_keys import (
    ApiKeyAuthenticationError,
    ApiKeyRecord,
    ApiKeyService,
)
from agent_api.auth.principal import AuthenticatedPrincipal
from agent_api.auth.roles import ApplicationRole
from agent_api.dependencies import (
    EmployeeEvidenceProvider,
    SingleIssueJiraEvidenceProvider,
    WorkforceScoringClient,
    get_evidence_provider,
    get_scoring_client,
)
from agent_api.graph.agents.operations_diagnostic import OperationsDiagnosticAgent
from agent_api.graph.agents.project_delivery import ProjectDeliveryAgent
from agent_api.graph.agents.reassignment_planning import ReassignmentPlanningAgent
from agent_api.graph.agents.workforce_analysis import WorkforceAnalysisAgent
from agent_api.graph.handoffs import SpecialistRouter
from agent_api.graph.intents import Intent
from agent_api.graph.state import (
    EntityReferences,
    InvestigationResponse,
    VerifiedAgentContext,
)
from agent_api.graph.workflow import InvestigationWorkflow
from agent_api.llm.factory import get_explanation_provider
from agent_api.llm.protocol import ExplanationProvider
from agent_api.task_queries import JiraTaskQueryTool, TaskQueryResult

router = APIRouter(prefix="/api/v1")


_AUTH_CACHE: dict[str, tuple[datetime, AuthenticatedPrincipal]] = {}


def _cache_key(authorization: str | None) -> str | None:
    if not authorization:
        return None
    return hashlib.sha256(authorization.encode()).hexdigest()


def _eligible_cached_read(request: Request) -> bool:
    path = request.url.path
    return (
        request.method == "GET"
        and any(part in path for part in ("/alerts", "/reports", "/overload-risk"))
    ) or (request.method == "POST" and path.endswith("/investigations"))


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1_000)
    context: EntityReferences


class EmployeeOverloadTool:
    def __init__(
        self,
        evidence: EmployeeEvidenceProvider,
        scoring: WorkforceScoringClient,
    ) -> None:
        self._evidence = evidence
        self._scoring = scoring

    async def investigate(
        self,
        intent: Intent,
        references: EntityReferences,
        correlation_id: str,
    ) -> RiskResult:
        if intent is not Intent.EXPLAIN_EMPLOYEE_OVERLOAD:
            raise ValueError("the requested deterministic domain tool is unavailable")
        if references.employee_id is None:
            raise ValueError("employee_id is required for overload investigation")
        bundle = await self._evidence.get_employee_overload(
            references.employee_id, references.project_key, correlation_id
        )
        raw = await self._scoring.score(bundle.input, correlation_id)
        return RiskResult.model_validate(raw)


class EvidenceBackedTaskQueryTool:
    def __init__(self, evidence: EmployeeEvidenceProvider) -> None:
        self._evidence = evidence

    async def query(
        self,
        question: str,
        references: EntityReferences,
        correlation_id: str,
    ) -> TaskQueryResult:
        if not isinstance(self._evidence, SingleIssueJiraEvidenceProvider):
            raise ValueError("Jira task queries require Jira evidence mode")
        timezone = ZoneInfo(os.getenv("BUSINESS_TIMEZONE", "Asia/Jerusalem"))
        tool = JiraTaskQueryTool(
            self._evidence.jira_client,
            today=lambda: datetime.now(timezone).date(),
        )
        return await tool.query(question, references, correlation_id)


async def get_investigator(
    request: Request,
    project_key: Annotated[str, Query(min_length=1)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedPrincipal:
    environment = cast(
        Literal["dev", "prod", "test"], os.getenv("APP_ENVIRONMENT", "dev")
    )
    database_url = os.getenv("DATABASE_URL")
    pepper = os.getenv("API_KEY_HMAC_PEPPER")
    if not database_url or not pepper:
        raise HTTPException(status_code=503, detail="authentication unavailable")
    database = Database(database_url)
    key = _cache_key(authorization)
    try:
        async with database.transaction() as session:
            rows = (await session.scalars(select(ApiKeyPrincipal))).all()
        records = tuple(
            ApiKeyRecord(
                actor_id=row.actor_id,
                display_label=row.display_label,
                key_digest=row.key_digest,
                role=ApplicationRole(row.role),
                environment=cast(Literal["dev", "prod", "test"], row.environment),
                project_scopes=tuple(row.project_scopes),
                created_at=row.created_at,
                expires_at=row.expires_at,
                revoked_at=row.revoked_at,
            )
            for row in rows
        )
        principal = ApiKeyService(pepper.encode()).authenticate(
            authorization,
            records=records,
            environment=environment,
            project_key=project_key,
            allowed_roles={
                ApplicationRole.VIEWER,
                ApplicationRole.MANAGER,
                ApplicationRole.ADMINISTRATOR,
            },
            now=datetime.now(UTC),
        )
        if key is not None:
            ttl = max(1, min(int(os.getenv("AUTH_CACHE_TTL_SECONDS", "30")), 60))
            _AUTH_CACHE[key] = (datetime.now(UTC) + timedelta(seconds=ttl), principal)
        return principal
    except ApiKeyAuthenticationError as exc:
        status = 403 if "role" in str(exc) or "scope" in str(exc) else 401
        raise HTTPException(status_code=status, detail="not authorized") from exc
    except Exception as exc:
        cached = None if key is None else _AUTH_CACHE.get(key)
        if (
            cached is not None
            and cached[0] > datetime.now(UTC)
            and cached[1].environment == environment
            and project_key in cached[1].project_scopes
            and _eligible_cached_read(request)
        ):
            return cached[1]
        raise HTTPException(
            status_code=503, detail="authentication unavailable"
        ) from exc
    finally:
        await database.close()


@router.post("/investigations")
async def investigate(
    payload: InvestigationRequest,
    response: Response,
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_investigator)],
    evidence: Annotated[EmployeeEvidenceProvider, Depends(get_evidence_provider)],
    scoring: Annotated[WorkforceScoringClient, Depends(get_scoring_client)],
    explainer: Annotated[ExplanationProvider, Depends(get_explanation_provider)],
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> InvestigationResponse:
    if payload.context.project_key != project_key:
        raise HTTPException(status_code=400, detail="project context mismatch")
    correlation_id = x_correlation_id or f"corr-{uuid4()}"
    verified = VerifiedAgentContext(
        subject_reference=principal.actor_id,
        roles=(principal.role,),
        environment=principal.environment,
        authorized_jira_sites=(os.getenv("JIRA_CLOUD_ID", "configured-jira-site"),),
        authorized_project_keys=principal.project_scopes,
        correlation_id=correlation_id,
    )
    core_tool = EmployeeOverloadTool(evidence, scoring)
    specialist_router = SpecialistRouter(
        core_tool=core_tool,
        specialists=(
            WorkforceAnalysisAgent(),
            ProjectDeliveryAgent(),
            ReassignmentPlanningAgent(),
            OperationsDiagnosticAgent(),
        ),
        context=verified,
    )
    workflow = InvestigationWorkflow(
        tool=specialist_router,
        task_query_tool=EvidenceBackedTaskQueryTool(evidence),
        explainer=explainer,
    )
    response.headers["X-Correlation-ID"] = correlation_id
    try:
        return await workflow.run(
            verified_context=verified,
            question=payload.question,
            references=payload.context,
        )
    except (TimeoutError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "INVESTIGATION_UNAVAILABLE",
                "correlation_id": correlation_id,
            },
        ) from exc
