from pathlib import Path

ROOT = Path(__file__).parents[2]
TF_ROOT = ROOT / "infra" / "terraform" / "environment"


def test_platform_alert_topic_is_encrypted_and_has_email_subscription() -> None:
    terraform = (TF_ROOT / "platform_alerts.tf").read_text()

    assert 'resource "aws_sns_topic" "platform_alerts"' in terraform
    assert 'kms_master_key_id = "alias/aws/sns"' in terraform
    assert 'resource "aws_sns_topic_subscription" "platform_alert_email"' in terraform
    assert 'protocol  = "email"' in terraform
    assert "endpoint  = var.platform_alert_email" in terraform


def test_alertmanager_role_is_bound_to_exact_monitoring_service_account() -> None:
    terraform = (TF_ROOT / "platform_alerts.tf").read_text()

    assert 'actions = ["sts:AssumeRoleWithWebIdentity"]' in terraform
    assert "identifiers = [local.alertmanager_oidc_provider_arn]" in terraform
    assert "aws_iam_openid_connect_provider.kubernetes.arn" not in terraform
    assert "${local.cluster_oidc_hostpath}:aud" in terraform
    assert "${local.cluster_oidc_hostpath}:sub" in terraform
    assert 'values   = ["sts.amazonaws.com"]' in terraform
    assert (
        'values   = ["system:serviceaccount:monitoring:workforce-alertmanager"]'
        in terraform
    )
    assert "system:serviceaccount:*" not in terraform


def test_alertmanager_role_can_only_publish_to_platform_topic() -> None:
    terraform = (TF_ROOT / "platform_alerts.tf").read_text()

    assert 'actions   = ["sns:Publish"]' in terraform
    assert "resources = [aws_sns_topic.platform_alerts.arn]" in terraform
    assert 'actions   = ["sns:*"]' not in terraform
    assert 'resources = ["*"]' not in terraform


def test_platform_alert_outputs_and_email_validation_are_explicit() -> None:
    variables = (TF_ROOT / "variables.tf").read_text()
    outputs = (TF_ROOT / "outputs.tf").read_text()

    assert 'variable "platform_alert_email"' in variables
    assert "can(regex(" in variables
    assert 'output "platform_alert_topic_arn"' in outputs
    assert 'output "alertmanager_sns_role_arn"' in outputs


def test_terraform_plan_receives_platform_alert_email_without_a_secret() -> None:
    workflow = (ROOT / ".github" / "workflows" / "terraform-plan.yml").read_text()

    assert "TF_VAR_platform_alert_email: ${{ vars.PLATFORM_ALERT_EMAIL }}" in workflow
    assert "secrets.PLATFORM_ALERT_EMAIL" not in workflow
