from agent_api.auth.roles import ApplicationRole
from agent_api.graph.state import VerifiedAgentContext


def test_verified_context_rejects_raw_credentials_and_bounds_references() -> None:
    assert "authorization" not in VerifiedAgentContext.model_fields
    assert "api_key" not in VerifiedAgentContext.model_fields
    context = VerifiedAgentContext(
        subject_reference="manager-safe-id",
        roles=(ApplicationRole.VIEWER,),
        environment="dev",
        authorized_jira_sites=("site-safe-id",),
        authorized_project_keys=("WRD",),
        correlation_id="corr-auth",
    )
    assert "wrk_dev_" not in context.model_dump_json()
