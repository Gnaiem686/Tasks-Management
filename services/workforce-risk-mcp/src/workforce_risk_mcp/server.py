from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from jira_mcp_client.mutation import JiraAssigneeMutationClient
from jira_mcp_client.transport import StreamableHttpJiraMcpTransport
from mcp.server.fastmcp import Context, FastMCP
from workforce_persistence.database import Database
from workforce_persistence.execution_repository import (
    DatabaseExecutionStore,
    DatabaseReconciliationStore,
)
from workforce_persistence.proposal_repository import ProposalRepository
from workforce_persistence.repositories import (
    CommentEvidenceRepository,
    ProfileRepository,
    SnapshotRepository,
)
from workforce_risk.comments.classifier import CommentClassifier, load_patterns
from workforce_risk.proposals.execution import ReassignmentExecutionService
from workforce_risk.proposals.reconciliation import ReconciliationService

from workforce_risk_mcp.tools.comment_evidence import (
    NormalizeCommentRequest,
    normalize_comment_evidence,
)
from workforce_risk_mcp.tools.evidence import PersistEvidenceRequest, persist_evidence
from workforce_risk_mcp.tools.execution import (
    ExecuteProposalRequest,
    execute_reassignment,
)
from workforce_risk_mcp.tools.profiles import (
    ProfileCapacityUpdate,
    ProfileCreateRequest,
    authorize_profile_change,
)
from workforce_risk_mcp.tools.proposals import (
    FreshnessProvider,
    ProposalCreateRequest,
    ProposalDecisionRequest,
    ProposalGetRequest,
    authorize_proposal,
    create_proposal,
    decide_proposal,
    get_proposal,
)
from workforce_risk_mcp.tools.reconciliation import (
    ReconcileProposalRequest,
    reconcile_proposal,
)
from workforce_risk_mcp.tools.score_overload import (
    ScoreOverloadRequest,
    score_overload,
)
from workforce_risk_mcp.tools.scoring import (
    ScoreProjectDeliveryRequest,
    ScoreTaskFitRequest,
    score_project_delivery_tool,
    score_task_fit_tool,
)

HOST = os.getenv("WORKFORCE_MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("WORKFORCE_MCP_PORT", "8001"))
ENVIRONMENT = os.getenv("APP_ENVIRONMENT", "dev")
CONFIG_PATH = Path(os.getenv("SCORING_CONFIG_PATH", "config/scoring/v1.yaml"))
COMMENT_CONFIG_PATH = Path(os.getenv("COMMENT_PATTERN_PATH", "config/comments/v1.yaml"))


class FailClosedFreshnessProvider:
    async def fingerprint_for_proposal(self, proposal_id: str) -> str:
        raise RuntimeError("targeted Jira freshness provider is not configured")


def get_proposal_freshness_provider() -> FreshnessProvider:
    return FailClosedFreshnessProvider()


mcp = FastMCP(
    "Workforce Risk MCP",
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


@mcp.tool(name="score_employee_overload")
def score_employee_overload_tool(request: dict[str, Any]) -> dict[str, Any]:
    """Calculate an auditable employee-overload score from structured evidence."""
    validated = ScoreOverloadRequest.model_validate(request)
    response = score_overload(
        validated,
        config_path=CONFIG_PATH,
        service_environment=ENVIRONMENT,
    )
    return response.model_dump(mode="json")


@mcp.tool(name="score_task_fit")
def score_task_fit_mcp_tool(request: dict[str, Any]) -> dict[str, Any]:
    """Calculate an auditable task-fit score from structured evidence."""
    response = score_task_fit_tool(
        ScoreTaskFitRequest.model_validate(request),
        config_path=CONFIG_PATH,
        service_environment=ENVIRONMENT,
    )
    return response.model_dump(mode="json")


@mcp.tool(name="score_project_delivery")
def score_project_delivery_mcp_tool(request: dict[str, Any]) -> dict[str, Any]:
    """Calculate an auditable project-delivery score from structured evidence."""
    response = score_project_delivery_tool(
        ScoreProjectDeliveryRequest.model_validate(request),
        config_path=CONFIG_PATH,
        service_environment=ENVIRONMENT,
    )
    return response.model_dump(mode="json")


@mcp.tool(name="persist_evidence_snapshot")
async def persist_evidence_snapshot_tool(request: dict[str, Any]) -> dict[str, Any]:
    """Persist immutable structured evidence and deterministic results atomically."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("snapshot persistence is not configured")
    database = Database(database_url)
    try:
        async with database.transaction() as session:
            response = await persist_evidence(
                PersistEvidenceRequest.model_validate(request),
                repository=SnapshotRepository(session),
                service_environment=ENVIRONMENT,
            )
            return response.model_dump(mode="json")
    finally:
        await database.close()


@mcp.tool(name="normalize_comment_evidence")
async def normalize_comment_evidence_tool(request: dict[str, Any]) -> dict[str, Any]:
    """Persist only conservative normalized metadata; discard the raw body."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("comment evidence persistence is not configured")
    classifier = CommentClassifier(
        load_patterns(COMMENT_CONFIG_PATH),
        employee_accounts=json.loads(os.getenv("WORKFORCE_JIRA_ACCOUNT_MAP", "{}")),
        manager_accounts=set(json.loads(os.getenv("JIRA_MANAGER_ACCOUNTS", "[]"))),
        reviewer_accounts=set(json.loads(os.getenv("JIRA_REVIEWER_ACCOUNTS", "[]"))),
        automation_accounts=set(
            json.loads(os.getenv("JIRA_AUTOMATION_ACCOUNTS", "[]"))
        ),
    )
    database = Database(database_url)
    try:
        async with database.transaction() as session:
            response = await normalize_comment_evidence(
                NormalizeCommentRequest.model_validate(request),
                classifier=classifier,
                repository=CommentEvidenceRepository(session),
                service_environment=ENVIRONMENT,
            )
            return response.model_dump(mode="json")
    finally:
        await database.close()


@mcp.tool(name="update_profile_capacity")
async def update_profile_capacity_tool(
    request: dict[str, Any], ctx: Context[Any, Any, Any]
) -> dict[str, Any]:
    """Update authoritative capacity after independent transport authorization."""
    validated = ProfileCapacityUpdate.model_validate(request)
    http_request = ctx.request_context.request
    transport_context = None
    if http_request is not None and hasattr(http_request, "headers"):
        transport_context = http_request.headers.get("X-Workforce-Authorization")
    secret = os.getenv("INTERNAL_AUTH_SECRET")
    database_url = os.getenv("DATABASE_URL")
    if not secret or not database_url:
        raise RuntimeError("protected profile service is not configured")
    verified = authorize_profile_change(
        validated,
        transport_context=transport_context,
        secret=secret.encode(),
        environment=cast(Literal["dev", "prod", "test"], ENVIRONMENT),
        now=datetime.now(UTC),
    )
    database = Database(database_url)
    try:
        async with database.transaction() as session:
            updated = await ProfileRepository(session).update_capacity_audited(
                environment=ENVIRONMENT,
                employee_id=validated.employee_id,
                expected_version=validated.expected_version,
                capacity_hours=validated.weekly_capacity_hours,
                actor_id=verified.actor_id,
                correlation_id=verified.correlation_id,
            )
            if updated is None:
                raise ValueError("profile not found or version conflict")
            return {
                "schema_version": "1.0",
                "environment": updated.environment,
                "correlation_id": verified.correlation_id,
                "employee_id": updated.employee_id,
                "weekly_capacity_hours": updated.weekly_capacity_hours,
                "version": updated.version,
            }
    finally:
        await database.close()


@mcp.tool(name="create_profile")
async def create_profile_tool(
    request: dict[str, Any], ctx: Context[Any, Any, Any]
) -> dict[str, Any]:
    """Create an authoritative profile after transport authorization."""
    validated = ProfileCreateRequest.model_validate(request)
    http_request = ctx.request_context.request
    transport_context = None
    if http_request is not None and hasattr(http_request, "headers"):
        transport_context = http_request.headers.get("X-Workforce-Authorization")
    secret = os.getenv("INTERNAL_AUTH_SECRET")
    database_url = os.getenv("DATABASE_URL")
    if not secret or not database_url:
        raise RuntimeError("protected profile service is not configured")
    verified = authorize_profile_change(
        validated,
        transport_context=transport_context,
        secret=secret.encode(),
        environment=cast(Literal["dev", "prod", "test"], ENVIRONMENT),
        now=datetime.now(UTC),
    )
    database = Database(database_url)
    try:
        async with database.transaction() as session:
            created = await ProfileRepository(session).create(
                environment=ENVIRONMENT,
                employee_id=validated.employee_id,
                role=validated.role,
                seniority=validated.seniority.value,
                weekly_capacity_hours=validated.weekly_capacity_hours,
                mentoring_available=validated.mentoring_available,
                jira_account_id=validated.jira_account_id,
                skills=tuple(
                    (skill.name, int(skill.proficiency))
                    for skill in validated.documented_skills
                ),
                allocations=tuple(
                    (allocation.project_key, allocation.fraction)
                    for allocation in validated.project_allocations
                ),
                capacity_overrides=tuple(
                    (
                        override.starts_at,
                        override.ends_at,
                        override.capacity_hours,
                        override.reason,
                    )
                    for override in validated.capacity_overrides
                ),
                actor_id=verified.actor_id,
                correlation_id=verified.correlation_id,
                created_at=datetime.now(UTC),
            )
            return {
                "schema_version": "1.0",
                "environment": created.environment,
                "correlation_id": verified.correlation_id,
                "employee_id": created.employee_id,
                "role": created.role,
                "seniority": created.seniority,
                "weekly_capacity_hours": created.weekly_capacity_hours,
                "mentoring_available": created.mentoring_available,
                "jira_account_id": created.jira_account_id,
                "version": created.version,
            }
    finally:
        await database.close()


def _transport_context(ctx: Context[Any, Any, Any]) -> str | None:
    request = ctx.request_context.request
    if request is not None and hasattr(request, "headers"):
        value = request.headers.get("X-Workforce-Authorization")
        return value if isinstance(value, str) else None
    return None


@mcp.tool(name="create_reassignment_proposal")
async def create_reassignment_proposal_tool(
    request: dict[str, Any], ctx: Context[Any, Any, Any]
) -> dict[str, Any]:
    validated = ProposalCreateRequest.model_validate(request)
    secret = os.getenv("INTERNAL_AUTH_SECRET")
    database_url = os.getenv("DATABASE_URL")
    if not secret or not database_url:
        raise RuntimeError("protected proposal service is not configured")
    verified = authorize_proposal(
        transport_context=_transport_context(ctx),
        secret=secret.encode(),
        environment=cast(Literal["dev", "prod", "test"], ENVIRONMENT),
        project_key=validated.project_key,
        now=datetime.now(UTC),
    )
    database = Database(database_url)
    try:
        async with database.transaction() as session:
            result = await create_proposal(
                validated,
                context=verified,
                repository=ProposalRepository(session),
            )
            return asdict(result)
    finally:
        await database.close()


@mcp.tool(name="decide_reassignment_proposal")
async def decide_reassignment_proposal_tool(
    request: dict[str, Any], ctx: Context[Any, Any, Any]
) -> dict[str, Any]:
    validated = ProposalDecisionRequest.model_validate(request)
    secret = os.getenv("INTERNAL_AUTH_SECRET")
    database_url = os.getenv("DATABASE_URL")
    if not secret or not database_url:
        raise RuntimeError("protected proposal service is not configured")
    verified = authorize_proposal(
        transport_context=_transport_context(ctx),
        secret=secret.encode(),
        environment=cast(Literal["dev", "prod", "test"], ENVIRONMENT),
        project_key=validated.project_key,
        now=datetime.now(UTC),
    )
    database = Database(database_url)
    try:
        async with database.transaction() as session:
            result = await decide_proposal(
                validated,
                context=verified,
                repository=ProposalRepository(session),
                freshness=get_proposal_freshness_provider(),
            )
            return asdict(result)
    finally:
        await database.close()


@mcp.tool(name="get_reassignment_proposal")
async def get_reassignment_proposal_tool(
    request: dict[str, Any], ctx: Context[Any, Any, Any]
) -> dict[str, Any]:
    validated = ProposalGetRequest.model_validate(request)
    secret = os.getenv("INTERNAL_AUTH_SECRET")
    database_url = os.getenv("DATABASE_URL")
    if not secret or not database_url:
        raise RuntimeError("protected proposal service is not configured")
    verified = authorize_proposal(
        transport_context=_transport_context(ctx),
        secret=secret.encode(),
        environment=cast(Literal["dev", "prod", "test"], ENVIRONMENT),
        project_key=validated.project_key,
        now=datetime.now(UTC),
    )
    database = Database(database_url)
    try:
        async with database.transaction() as session:
            return asdict(
                await get_proposal(
                    validated,
                    context=verified,
                    repository=ProposalRepository(session),
                )
            )
    finally:
        await database.close()


@mcp.tool(name="execute_reassignment")
async def execute_reassignment_tool(
    request: dict[str, Any], ctx: Context[Any, Any, Any]
) -> dict[str, Any]:
    """Execute the sole approved Jira mutation after proposal safeguards pass."""
    validated = ExecuteProposalRequest.model_validate(request)
    secret = os.getenv("INTERNAL_AUTH_SECRET")
    database_url = os.getenv("DATABASE_URL")
    jira_authorization = os.getenv("JIRA_MCP_AUTH_HEADER")
    jira_url = os.getenv("ATLASSIAN_MCP_URL", "https://mcp.atlassian.com/v1/mcp")
    jira_cloud_id = os.getenv("JIRA_CLOUD_ID")
    mutation_enabled = os.getenv("JIRA_MUTATION_ENABLED", "false").lower() == "true"
    if (
        not secret
        or not database_url
        or not jira_authorization
        or not jira_cloud_id
        or not mutation_enabled
        or ENVIRONMENT != "dev"
    ):
        raise RuntimeError("Jira reassignment execution is not configured")
    verified = authorize_proposal(
        transport_context=_transport_context(ctx),
        secret=secret.encode(),
        environment="dev",
        project_key=validated.project_key,
        now=datetime.now(UTC),
    )
    database = Database(database_url)
    try:
        transport = StreamableHttpJiraMcpTransport(
            url=jira_url,
            cloud_id=jira_cloud_id,
            environment="dev",
            authorization_header=jira_authorization,
        )
        service = ReassignmentExecutionService(
            store=DatabaseExecutionStore(database, environment="dev"),
            mutator=JiraAssigneeMutationClient(
                transport=transport,
                environment="dev",
                allowed_project_keys=set(verified.project_scopes),
            ),
        )
        result = await execute_reassignment(
            validated,
            service=service,
            correlation_id=verified.correlation_id,
        )
        return result.model_dump(mode="json")
    finally:
        await database.close()


@mcp.tool(name="reconcile_uncertain_reassignment")
async def reconcile_uncertain_reassignment_tool(
    request: dict[str, Any], ctx: Context[Any, Any, Any]
) -> dict[str, Any]:
    """Allow an authorized manager to resolve uncertainty from a fresh Jira read."""
    validated = ReconcileProposalRequest.model_validate(request)
    secret = os.getenv("INTERNAL_AUTH_SECRET")
    database_url = os.getenv("DATABASE_URL")
    jira_authorization = os.getenv("JIRA_MCP_AUTH_HEADER")
    jira_cloud_id = os.getenv("JIRA_CLOUD_ID")
    if not secret or not database_url or not jira_authorization or not jira_cloud_id:
        raise RuntimeError("Jira reconciliation is not configured")
    verified = authorize_proposal(
        transport_context=_transport_context(ctx),
        secret=secret.encode(),
        environment=cast(Literal["dev", "prod", "test"], ENVIRONMENT),
        project_key=validated.project_key,
        now=datetime.now(UTC),
    )
    database = Database(database_url)
    try:
        reader = JiraAssigneeMutationClient(
            transport=StreamableHttpJiraMcpTransport(
                url=os.getenv("ATLASSIAN_MCP_URL", "https://mcp.atlassian.com/v1/mcp"),
                cloud_id=jira_cloud_id,
                environment=ENVIRONMENT,
                authorization_header=jira_authorization,
            ),
            environment=ENVIRONMENT,
            allowed_project_keys=set(verified.project_scopes),
        )
        result = await reconcile_proposal(
            validated,
            service=ReconciliationService(
                store=DatabaseReconciliationStore(database, environment=ENVIRONMENT),
                reader=reader,
            ),
            worker_id=f"manager:{verified.actor_id}",
        )
        return {
            "schema_version": "1.0",
            "environment": ENVIRONMENT,
            "correlation_id": verified.correlation_id,
            "result": None if result is None else result.model_dump(mode="json"),
        }
    finally:
        await database.close()


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
