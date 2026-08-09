from pathlib import Path

TF_ROOT = Path(__file__).parents[2] / "infra" / "terraform" / "environment"


def _terraform() -> str:
    return "\n".join(path.read_text() for path in TF_ROOT.glob("*.tf"))


def test_external_secrets_roles_are_namespace_and_service_account_scoped() -> None:
    iam = (TF_ROOT / "secrets.tf").read_text()
    assert "sts:AssumeRoleWithWebIdentity" in iam
    assert 'system:serviceaccount:${each.key}:external-secrets' in iam
    assert 'StringEquals' in iam
    assert "secretsmanager:GetSecretValue" in iam
    assert "secretsmanager:DescribeSecret" in iam
    assert "resources = values(aws_secretsmanager_secret.environment)[*].arn" not in iam


def test_bedrock_permission_is_model_and_region_scoped() -> None:
    bedrock = (TF_ROOT / "bedrock.tf").read_text()
    assert 'bedrock:InvokeModel' in bedrock
    assert 'bedrock:InvokeModelWithResponseStream' in bedrock
    assert 'foundation-model/${var.bedrock_model_id}' in bedrock
    assert "Resource = \"*\"" not in bedrock


def test_ses_permission_is_configuration_set_scoped() -> None:
    email = (TF_ROOT / "email.tf").read_text()
    assert "ses:SendEmail" in email
    assert "ses:SendRawEmail" in email
    assert "ses:ConfigurationSetName" in email
    assert 'workforce-risk-${each.key}' in email


def test_application_roles_are_environment_specific() -> None:
    terraform = _terraform()
    assert 'aws_iam_role" "application"' in terraform
    assert 'for_each = local.environments' in terraform
    assert 'system:serviceaccount:${each.key}:agent-api' in terraform
    assert 'aws_s3_bucket.reports[each.key].arn' in terraform
    assert 'aws_sqs_queue.notifications[each.key].arn' in terraform


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
