from pathlib import Path

TF_ROOT = Path(__file__).parents[2] / "infra" / "terraform" / "environment"


def _terraform() -> str:
    return "\n".join(path.read_text() for path in TF_ROOT.glob("*.tf"))


def test_external_secrets_roles_are_namespace_and_service_account_scoped() -> None:
    iam = (TF_ROOT / "secrets.tf").read_text()
    assert "sts:AssumeRoleWithWebIdentity" in iam
    assert "system:serviceaccount:${each.key}:external-secrets" in iam
    assert "StringEquals" in iam
    assert "secretsmanager:GetSecretValue" in iam
    assert "secretsmanager:DescribeSecret" in iam
    assert "resources = values(aws_secretsmanager_secret.environment)[*].arn" not in iam


def test_self_managed_cluster_publishes_only_public_oidc_material() -> None:
    oidc = (TF_ROOT / "oidc.tf").read_text()
    assert 'aws_s3_bucket" "cluster_oidc"' in oidc
    assert 'aws_iam_openid_connect_provider" "kubernetes"' in oidc
    assert "/.well-known/openid-configuration" in oidc
    assert "/openid/v1/jwks" in oidc
    assert "s3:GetObject" in oidc
    assert "s3:PutObject" not in oidc
    assert "private" not in oidc.lower()


def test_bedrock_permission_is_model_and_region_scoped() -> None:
    bedrock = (TF_ROOT / "bedrock.tf").read_text()
    assert "bedrock:InvokeModel" in bedrock
    assert "bedrock:InvokeModelWithResponseStream" in bedrock
    assert "foundation-model/${var.bedrock_model_id}" in bedrock
    assert 'Resource = "*"' not in bedrock


def test_ses_permission_is_configuration_set_scoped() -> None:
    email = (TF_ROOT / "email.tf").read_text()
    assert "ses:SendEmail" in email
    assert "ses:SendRawEmail" in email
    assert "ses:ConfigurationSetName" in email
    assert "workforce-risk-${each.key}" in email


def test_application_roles_are_environment_specific() -> None:
    terraform = _terraform()
    assert 'aws_iam_role" "application"' in terraform
    assert "for_each = local.environments" in terraform
    assert "system:serviceaccount:${each.key}:agent-api" in terraform
    assert "system:serviceaccount:${each.key}:workforce-risk-mcp" in terraform
    assert "aws_s3_bucket.reports[each.key].arn" in terraform
    assert "aws_sqs_queue.notifications[each.key].arn" in terraform


def test_no_wildcard_secret_or_storage_permissions() -> None:
    terraform = _terraform()
    forbidden = [
        'actions   = ["secretsmanager:*"]',
        'actions   = ["s3:*"]',
        'actions   = ["sqs:*"]',
        'actions   = ["bedrock:*"]',
    ]
    for statement in forbidden:
        assert statement not in terraform


def test_github_dev_deploy_role_uses_checksum_bundle_and_ssm_only() -> None:
    deployment = (TF_ROOT / "deployment.tf").read_text()
    assert 'aws_s3_bucket" "deployment_artifacts"' in deployment
    assert 'sse_algorithm     = "aws:kms"' in deployment
    # Require the dedicated four-flag public-access-block resource.
    assert "block_public_access" not in deployment
    assert "aws_s3_bucket_public_access_block" in deployment
    assert "ssm:SendCommand" in deployment
    assert "aws_instance.control_plane.arn" in deployment
    assert "document/AWS-RunShellScript" in deployment
    assert "data.aws_iam_role.github_dev_deploy" in deployment
    assert "aws_iam_role.control_plane.id" in deployment
    assert '"s3:GetObject"' in deployment
    assert '"kms:Decrypt"' in deployment
