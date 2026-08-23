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


def test_github_environment_deploy_roles_use_checksum_bundle_and_ssm_only() -> None:
    deployment = (TF_ROOT / "deployment.tf").read_text()
    assert 'aws_s3_bucket" "deployment_artifacts"' in deployment
    assert 'sse_algorithm     = "aws:kms"' in deployment
    # Require the dedicated four-flag public-access-block resource.
    assert "block_public_access" not in deployment
    assert "aws_s3_bucket_public_access_block" in deployment
    assert "ssm:SendCommand" in deployment
    assert "data.aws_instances.deployment_control_plane.ids" in deployment
    assert "document/AWS-RunShellScript" in deployment
    assert 'data "aws_iam_role" "github_deploy"' in deployment
    assert 'for_each = toset(["dev", "prod"])' in deployment
    assert "aws_iam_role.control_plane.id" in deployment
    assert '"s3:GetObject"' in deployment
    assert '"kms:Decrypt"' in deployment


def test_github_deploy_smoke_permissions_are_read_only_and_environment_scoped() -> None:
    deployment = (TF_ROOT / "deployment.tf").read_text()
    assert 'actions   = ["s3:ListBucket"]' in deployment
    assert "aws_s3_bucket.reports[each.key].arn" in deployment
    assert 'actions   = ["sqs:GetQueueAttributes"]' in deployment
    assert "aws_sqs_queue.notifications[each.key].arn" in deployment
    assert 'actions   = ["s3:PutObject"]' not in deployment
    assert 'actions   = ["sqs:SendMessage"]' not in deployment


def test_deploy_policy_resolves_running_control_plane_independently() -> None:
    deployment = (TF_ROOT / "deployment.tf").read_text()
    assert 'data "aws_instances" "deployment_control_plane"' in deployment
    assert 'values = ["${var.project_name}-shared-control-plane"]' in deployment
    assert 'values = ["running"]' in deployment
    assert "data.aws_instances.deployment_control_plane.ids" in deployment
    assert "aws_instance.control_plane.arn" not in deployment


def test_worker_nodes_can_pull_images_from_project_ecr_repositories() -> None:
    iam = (TF_ROOT / "iam.tf").read_text()
    terraform = _terraform()

    assert 'data "aws_caller_identity" "current"' in terraform
    assert 'data "aws_iam_policy_document" "worker_ecr_pull"' in iam
    assert '"ecr:GetAuthorizationToken"' in iam
    assert '"ecr:BatchCheckLayerAvailability"' in iam
    assert '"ecr:BatchGetImage"' in iam
    assert '"ecr:GetDownloadUrlForLayer"' in iam
    assert "repository/workforce-risk/" in iam
    assert 'resource "aws_iam_role_policy" "worker_ecr_pull"' in iam


def test_ebs_csi_role_is_bound_to_only_the_controller_service_account() -> None:
    ebs_csi = (TF_ROOT / "ebs_csi.tf").read_text()

    assert 'actions = ["sts:AssumeRoleWithWebIdentity"]' in ebs_csi
    assert "aws_iam_openid_connect_provider.kubernetes.arn" in ebs_csi
    assert 'test     = "StringEquals"' in ebs_csi
    assert "${local.cluster_oidc_hostpath}:aud" in ebs_csi
    assert "${local.cluster_oidc_hostpath}:sub" in ebs_csi
    assert 'values   = ["sts.amazonaws.com"]' in ebs_csi
    assert (
        'values   = ["system:serviceaccount:kube-system:ebs-csi-controller-sa"]'
        in ebs_csi
    )
    assert "system:serviceaccount:*" not in ebs_csi


def test_ebs_csi_role_uses_managed_driver_policy_and_sensitive_output() -> None:
    ebs_csi = (TF_ROOT / "ebs_csi.tf").read_text()
    outputs = (TF_ROOT / "outputs.tf").read_text()

    assert (
        'policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"'
        in ebs_csi
    )
    assert 'resource "aws_iam_role_policy_attachment" "ebs_csi_controller"' in ebs_csi
    assert 'output "ebs_csi_controller_role_arn"' in outputs
    assert "aws_iam_role.ebs_csi_controller.arn" in outputs
    assert "sensitive = true" in outputs
