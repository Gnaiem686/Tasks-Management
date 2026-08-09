resource "aws_secretsmanager_secret" "environment" {
  for_each                = local.secret_containers
  name                    = "${var.project_name}/${each.value.environment}/${each.value.type}"
  description             = "Container for ${each.value.environment} ${each.value.type}; value supplied securely outside Terraform"
  recovery_window_in_days = 30

  tags = {
    ApplicationEnvironment = each.value.environment
    SecretType             = each.value.type
  }
}

data "aws_iam_policy_document" "workload_assume" {
  for_each = local.environments
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.cluster_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.cluster_oidc_issuer_hostpath}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "ForAnyValue:StringEquals"
      variable = "${var.cluster_oidc_issuer_hostpath}:sub"
      values = [
        "system:serviceaccount:${each.key}:agent-api",
        "system:serviceaccount:${each.key}:notification-worker",
        "system:serviceaccount:${each.key}:report-worker",
      ]
    }
  }
}

resource "aws_iam_role" "application" {
  for_each           = local.environments
  name               = "${var.project_name}-${each.key}-application"
  assume_role_policy = data.aws_iam_policy_document.workload_assume[each.key].json
}

data "aws_iam_policy_document" "external_secrets_assume" {
  for_each = local.environments
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.cluster_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.cluster_oidc_issuer_hostpath}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.cluster_oidc_issuer_hostpath}:sub"
      values   = ["system:serviceaccount:${each.key}:external-secrets"]
    }
  }
}

resource "aws_iam_role" "external_secrets" {
  for_each           = local.environments
  name               = "${var.project_name}-${each.key}-external-secrets"
  assume_role_policy = data.aws_iam_policy_document.external_secrets_assume[each.key].json
}

data "aws_iam_policy_document" "external_secrets" {
  for_each = local.environments
  statement {
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      for key, secret in aws_secretsmanager_secret.environment : secret.arn
      if local.secret_containers[key].environment == each.key
    ]
  }
}

resource "aws_iam_role_policy" "external_secrets" {
  for_each = local.environments
  role     = aws_iam_role.external_secrets[each.key].id
  policy   = data.aws_iam_policy_document.external_secrets[each.key].json
}
