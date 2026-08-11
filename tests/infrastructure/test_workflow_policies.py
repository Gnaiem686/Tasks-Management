from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text()


def _workflow(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.load(_text(name), Loader=yaml.BaseLoader))


def test_ci_is_reusable_and_targets_integration_and_production() -> None:
    workflow = _workflow("ci.yml")
    assert "workflow_call" in workflow["on"]
    assert workflow["on"]["pull_request"]["branches"] == ["dev", "main"]
    assert workflow["on"]["push"]["branches"] == ["main"]


def test_dev_deployment_is_guarded_and_serialized() -> None:
    workflow = _workflow("deploy-dev.yml")
    text = _text("deploy-dev.yml")
    assert workflow["concurrency"]["group"] == "deploy-dev"
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    assert "vars.DEPLOYMENTS_ENABLED == 'true'" in text
    assert workflow["jobs"]["deploy"]["environment"] == "dev"
    assert workflow["permissions"]["id-token"] == "write"
    assert workflow["permissions"]["contents"] == "read"


def test_dev_deployment_runs_after_reusable_ci_on_dev_pushes() -> None:
    workflow = _workflow("deploy-dev.yml")
    assert workflow["on"]["push"]["branches"] == ["dev"]
    assert workflow["jobs"]["quality"]["uses"] == "./.github/workflows/ci.yml"
    assert workflow["jobs"]["deploy"]["needs"] == "quality"


def test_dev_deployment_persists_promotion_evidence() -> None:
    text = _text("deploy-dev.yml")
    assert "artifacts/deployment/image-digests.json" in text
    assert "artifacts/deployment/release.json" in text
    assert "dev-release-${{ github.run_id }}" in text


def test_dev_ssm_payload_runs_explicitly_under_bash() -> None:
    text = _text("deploy-dev.yml")
    assert '"bash -lc " + ($script | @sh)' in text
    assert '"set -Eeuo pipefail",' not in text


def test_dev_deploys_through_checksum_verified_s3_and_ssm() -> None:
    text = _text("deploy-dev.yml")
    assert "aws s3 cp" in text
    assert "sha256sum" in text
    assert "aws ssm send-command" in text
    assert "aws ssm wait command-executed" in text
    assert "AWS-RunShellScript" in text
    assert "kubeconfig" not in text.lower()
    assert "kubectl config" not in text


def test_dev_build_promotes_only_resolved_image_digests() -> None:
    text = _text("deploy-dev.yml")
    for image in (
        "agent-api",
        "workforce-risk-mcp",
        "devops-mcp",
        "notification-worker",
    ):
        assert image in text
    assert "docker inspect" in text
    assert 'reference="$repository@$digest"' in text
    assert "sha256:" in text
    assert "kustomize edit set image" in text
    assert "kubectl set image" not in text
    assert ":latest" not in text
    assert 'repository="$ECR_REGISTRY/workforce-risk/$service"' in text
    assert '--repository-name "workforce-risk/$service"' in text
    assert "DEV_APPLICATION_ROLE_ARN" in text
    assert "DEV_EXTERNAL_SECRETS_ROLE_ARN" in text
    assert "WORKFORCE_APPLICATION_ROLE_ARN" in text
    assert "WORKFORCE_EXTERNAL_SECRETS_ROLE_ARN" in text


def test_dev_release_stops_on_migration_and_rollout_failure() -> None:
    text = _text("deploy-dev.yml")
    deploy_script = (ROOT / "scripts" / "deployment" / "deploy_release.sh").read_text()
    release_path = text + deploy_script
    assert "set -Eeuo pipefail" in text
    assert "database-migration" in release_path
    assert "--for=condition=complete" in release_path
    assert "condition=complete" in release_path
    assert "rollout status" in release_path
    assert "alembic downgrade" not in release_path
    assert "database rollback" not in release_path.lower()


def test_dev_release_bootstraps_namespace_before_server_side_validation() -> None:
    deploy_script = (ROOT / "scripts" / "deployment" / "deploy_release.sh").read_text()
    namespace_bootstrap = 'kubectl create namespace "$RELEASE_NAMESPACE"'
    foundation_validation = (
        "kubectl apply --server-side --dry-run=server "
        '-f "$RELEASE_DIRECTORY/foundation.yaml"'
    )

    assert namespace_bootstrap in deploy_script
    assert "--dry-run=client -o yaml" in deploy_script
    assert deploy_script.index(namespace_bootstrap) < deploy_script.index(
        foundation_validation
    )


def test_dev_release_removes_terminal_migration_before_dry_run_replacement() -> None:
    deploy_script = (ROOT / "scripts" / "deployment" / "deploy_release.sh").read_text()
    delete_job = (
        'kubectl -n "$RELEASE_NAMESPACE" delete job/database-migration --wait=true'
    )
    migration_validation = (
        "kubectl apply --server-side --dry-run=server "
        '-f "$RELEASE_DIRECTORY/migration.yaml"'
    )

    assert deploy_script.index(delete_job) < deploy_script.index(migration_validation)


def test_dev_smoke_and_release_record_cover_required_evidence() -> None:
    smoke = (ROOT / "scripts" / "validation" / "smoke_dev.sh").read_text()
    release = (ROOT / "scripts" / "validation" / "record_release.sh").read_text()
    for check in (
        "embedded-ui",
        "api-key-authentication",
        "agent-api",
        "workforce-risk-mcp",
        "devops-mcp",
        "postgresql",
        "s3-report",
        "notification-queue",
        "jira-read",
        "seven-person-dataset",
        "overload-detection",
        "simulation-no-mutation",
        "prometheus-target",
    ):
        assert check in smoke
    for field in (
        "git_commit",
        "image_digests",
        "manifest_version",
        "scoring_version",
        "migration_version",
        "deployment_actor",
        "dev_validation",
    ):
        assert field in release


def test_workflow_publishes_summaries_and_retains_artifacts() -> None:
    text = _text("deploy-dev.yml")
    assert "GITHUB_STEP_SUMMARY" in text
    assert "junit" in text.lower()
    assert "codecov/codecov-action@" in text
    assert "actions/upload-artifact@" in text
    for artifact in ("security", "sbom", "terraform", "kubernetes", "deployment"):
        assert artifact in text
    assert "if: always()" in text


def test_ci_retains_coverage_when_codecov_is_not_onboarded() -> None:
    text = _text("ci.yml")
    assert "--cov-report=xml:artifacts/tests/coverage.xml" in text
    assert "fail_ci_if_error: false" in text
    assert "artifacts/tests/coverage.xml" in text


def test_ci_blocks_network_without_breaking_asyncio_event_loops() -> None:
    text = _text("ci.yml")
    assert "--disable-socket" in text
    assert "--allow-unix-socket" in text


def test_terraform_plan_and_apply_are_separate_and_serialized() -> None:
    plan = _text("terraform-plan.yml")
    apply = _text("terraform-apply.yml")
    assert 'terraform -chdir="$root" plan' in plan
    assert "terraform apply" not in plan
    assert ' apply "$GITHUB_WORKSPACE/' in apply
    assert "environment: infrastructure-apply" in apply
    assert "vars.DEPLOYMENTS_ENABLED == 'true'" in apply
    assert "concurrency:" in apply
    assert "cancel-in-progress: false" in apply
    assert "id-token: write" in plan
    assert "id-token: write" in apply
