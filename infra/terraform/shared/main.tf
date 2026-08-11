data "aws_caller_identity" "current" {}

locals {
  tags = {
    Project   = var.project_name
    Owner     = "workforce-platform"
    ManagedBy = "terraform"
    CostScope = "shared"
  }
  image_repositories = toset([
    "agent-api",
    "workforce-risk-mcp",
    "devops-mcp",
    "notification-worker",
  ])
}

resource "aws_ecr_repository" "application" {
  for_each             = local.image_repositories
  name                 = "${var.project_name}/${each.value}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "application" {
  for_each   = aws_ecr_repository.application
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Retain the newest 30 immutable images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 30
      }
      action = { type = "expire" }
    }]
  })
}

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "github_environment_trust" {
  for_each = toset(["dev", "prod"])

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository_subject}:environment:${each.key == "prod" ? "production" : each.key}"
      ]
    }
  }
}

resource "aws_iam_role" "github_environment" {
  for_each             = toset(["dev", "prod"])
  name                 = "${var.project_name}-github-${each.key}"
  assume_role_policy   = data.aws_iam_policy_document.github_environment_trust[each.key].json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "github_ecr" {
  statement {
    sid       = "PushAndReadProjectImages"
    effect    = "Allow"
    resources = [for repository in aws_ecr_repository.application : repository.arn]
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
  }
  statement {
    sid       = "AuthenticateToEcr"
    effect    = "Allow"
    resources = ["*"]
    actions   = ["ecr:GetAuthorizationToken"]
  }
}

resource "aws_iam_role_policy" "github_ecr" {
  for_each = aws_iam_role.github_environment
  name     = "project-ecr"
  role     = each.value.id
  policy   = data.aws_iam_policy_document.github_ecr.json
}
