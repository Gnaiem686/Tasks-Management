from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
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
    WorkforceScoringClient,
    get_evidence_provider,
    get_scoring_client,
)
from agent_api.graph.intents import Intent
from agent_api.graph.state import (
    EntityReferences,
    InvestigationResponse,
    VerifiedAgentContext,
)
from agent_api.graph.workflow import InvestigationWorkflow
from agent_api.llm.fallback import DeterministicFallbackProvider

router = APIRouter(prefix="/api/v1")


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


async def get_investigator(
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
        return ApiKeyService(pepper.encode()).authenticate(
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
    except ApiKeyAuthenticationError as exc:
        status = 403 if "role" in str(exc) or "scope" in str(exc) else 401
        raise HTTPException(status_code=status, detail="not authorized") from exc
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
    workflow = InvestigationWorkflow(
        tool=EmployeeOverloadTool(evidence, scoring),
        explainer=DeterministicFallbackProvider(),
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
