locals {
  alertmanager_oidc_provider_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.cluster_oidc_hostpath}"
}

resource "aws_sns_topic" "platform_alerts" {
  name              = "${var.project_name}-platform-alerts"
  kms_master_key_id = "alias/aws/sns"

  tags = {
    Purpose = "platform-health-alerts"
  }
}

resource "aws_sns_topic_subscription" "platform_alert_email" {
  topic_arn = aws_sns_topic.platform_alerts.arn
  protocol  = "email"
  endpoint  = var.platform_alert_email
}

data "aws_iam_policy_document" "alertmanager_sns_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.alertmanager_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.cluster_oidc_hostpath}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.cluster_oidc_hostpath}:sub"
      values   = ["system:serviceaccount:monitoring:workforce-alertmanager"]
    }
  }
}

resource "aws_iam_role" "alertmanager_sns" {
  name               = "${var.project_name}-alertmanager-sns"
  assume_role_policy = data.aws_iam_policy_document.alertmanager_sns_assume.json
}

data "aws_iam_policy_document" "alertmanager_sns_publish" {
  statement {
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.platform_alerts.arn]
  }
}

resource "aws_iam_role_policy" "alertmanager_sns_publish" {
  name   = "platform-alert-publish"
  role   = aws_iam_role.alertmanager_sns.id
  policy = data.aws_iam_policy_document.alertmanager_sns_publish.json
}
