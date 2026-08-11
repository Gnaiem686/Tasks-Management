resource "aws_kms_key" "deployment_artifacts" {
  description             = "Encrypt checksum-verified CI deployment bundles"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_s3_bucket" "deployment_artifacts" {
  bucket        = "${var.project_name}-deployment-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "deployment_artifacts" {
  bucket                  = aws_s3_bucket.deployment_artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "deployment_artifacts" {
  bucket = aws_s3_bucket.deployment_artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "deployment_artifacts" {
  bucket = aws_s3_bucket.deployment_artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.deployment_artifacts.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "deployment_artifacts" {
  bucket = aws_s3_bucket.deployment_artifacts.id
  rule {
    id     = "expire-release-bundles"
    status = "Enabled"
    filter { prefix = "releases/" }
    expiration { days = 30 }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}

data "aws_iam_role" "github_dev_deploy" {
  name = "${var.project_name}-github-dev"
}

data "aws_iam_policy_document" "github_dev_deploy" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.deployment_artifacts.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["releases/dev/*"]
    }
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.deployment_artifacts.arn}/releases/dev/*"]
  }
  statement {
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.deployment_artifacts.arn]
  }
  statement {
    actions = ["ssm:SendCommand"]
    resources = [
      aws_instance.control_plane.arn,
      "arn:aws:ssm:${var.aws_region}::document/AWS-RunShellScript",
    ]
  }
  statement {
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_dev_deploy" {
  name   = "private-kubeadm-dev-deploy"
  role   = data.aws_iam_role.github_dev_deploy.id
  policy = data.aws_iam_policy_document.github_dev_deploy.json
}

data "aws_iam_policy_document" "control_plane_release_bundle" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.deployment_artifacts.arn}/releases/*"]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.deployment_artifacts.arn]
  }
}

resource "aws_iam_role_policy" "control_plane_release_bundle" {
  name   = "checksum-release-bundle-read"
  role   = aws_iam_role.control_plane.id
  policy = data.aws_iam_policy_document.control_plane_release_bundle.json
}

output "deployment_artifact_bucket" {
  value = aws_s3_bucket.deployment_artifacts.id
}
