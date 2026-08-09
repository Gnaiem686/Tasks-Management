from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from workforce_contracts.auth import AuthenticatedPrincipal

from agent_api.auth.roles import ApplicationRole
from agent_api.clients.workforce_mcp import StreamableHttpProposalClient
from agent_api.routes.investigations import get_investigator

router = APIRouter(prefix="/api/v1")


class ProposalClient(Protocol):
    async def get_proposal(
        self,
        *,
        request: dict[str, Any],
        principal: AuthenticatedPrincipal,
        correlation_id: str,
    ) -> dict[str, Any]: ...
    async def create_proposal(
        self,
        *,
        request: dict[str, Any],
        principal: AuthenticatedPrincipal,
        correlation_id: str,
    ) -> dict[str, Any]: ...
    async def decide_proposal(
        self,
        *,
        request: dict[str, Any],
        principal: AuthenticatedPrincipal,
        correlation_id: str,
    ) -> dict[str, Any]: ...


class ProposalCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    simulation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)
    expires_at: AwareDatetime


class ProposalDecisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


async def get_proposal_manager(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_investigator)],
) -> AuthenticatedPrincipal:
    if principal.role not in {ApplicationRole.MANAGER, ApplicationRole.ADMINISTRATOR}:
        raise HTTPException(status_code=403, detail="not authorized")
    return principal


def get_proposal_client() -> ProposalClient:
    secret = os.getenv("INTERNAL_AUTH_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="proposal service unavailable")
    return StreamableHttpProposalClient(
        url=os.getenv("WORKFORCE_MCP_URL", "http://127.0.0.1:8001/mcp"),
        secret=secret.encode(),
    )


@router.get("/proposals/{proposal_id}")
async def get_proposal_endpoint(
    proposal_id: str,
    response: Response,
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_proposal_manager)],
    client: Annotated[ProposalClient, Depends(get_proposal_client)],
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    correlation_id = x_correlation_id or f"corr-{uuid4()}"
    result = await client.get_proposal(
        request={"project_key": project_key, "proposal_id": proposal_id},
        principal=principal,
        correlation_id=correlation_id,
    )
    response.headers["X-Correlation-ID"] = correlation_id
    return result


@router.post("/proposals", status_code=201)
async def create_proposal_endpoint(
    payload: ProposalCreatePayload,
    response: Response,
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_proposal_manager)],
    client: Annotated[ProposalClient, Depends(get_proposal_client)],
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    correlation_id = x_correlation_id or f"corr-{uuid4()}"
    result = await client.create_proposal(
        request={
            "project_key": project_key,
            "simulation_id": payload.simulation_id,
            "idempotency_key": payload.idempotency_key,
            "expires_at": payload.expires_at.isoformat(),
            "requested_at": datetime.now(UTC).isoformat(),
        },
        principal=principal,
        correlation_id=correlation_id,
    )
    response.headers["X-Correlation-ID"] = correlation_id
    return result


async def _decide(
    *,
    proposal_id: str,
    decision: Literal["approve", "reject"],
    payload: ProposalDecisionPayload,
    project_key: str,
    principal: AuthenticatedPrincipal,
    client: ProposalClient,
    correlation_id: str,
) -> dict[str, Any]:
    return await client.decide_proposal(
        request={
            "project_key": project_key,
            "proposal_id": proposal_id,
            "expected_version": payload.expected_version,
            "decision": decision,
            "idempotency_key": payload.idempotency_key,
            "decided_at": datetime.now(UTC).isoformat(),
        },
        principal=principal,
        correlation_id=correlation_id,
    )


@router.post("/proposals/{proposal_id}/approve", status_code=202)
async def approve_proposal_endpoint(
    proposal_id: str,
    payload: ProposalDecisionPayload,
    response: Response,
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_proposal_manager)],
    client: Annotated[ProposalClient, Depends(get_proposal_client)],
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    correlation_id = x_correlation_id or f"corr-{uuid4()}"
    result = await _decide(
        proposal_id=proposal_id,
        decision="approve",
        payload=payload,
        project_key=project_key,
        principal=principal,
        client=client,
        correlation_id=correlation_id,
    )
    response.headers["X-Correlation-ID"] = correlation_id
    return result


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal_endpoint(
    proposal_id: str,
    payload: ProposalDecisionPayload,
    response: Response,
    project_key: Annotated[str, Query(min_length=1)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_proposal_manager)],
    client: Annotated[ProposalClient, Depends(get_proposal_client)],
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    correlation_id = x_correlation_id or f"corr-{uuid4()}"
    result = await _decide(
        proposal_id=proposal_id,
        decision="reject",
        payload=payload,
        project_key=project_key,
        principal=principal,
        client=client,
        correlation_id=correlation_id,
    )
    response.headers["X-Correlation-ID"] = correlation_id
    return result
