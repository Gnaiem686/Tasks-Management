resource "aws_kms_key" "reports" {
  for_each                = local.environments
  description             = "${each.key} immutable report encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_s3_bucket" "reports" {
  for_each      = local.environments
  bucket        = "${var.project_name}-${each.key}-reports-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "reports" {
  for_each                = local.environments
  bucket                  = aws_s3_bucket.reports[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "reports" {
  for_each = local.environments
  bucket   = aws_s3_bucket.reports[each.key].id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  for_each = local.environments
  bucket   = aws_s3_bucket.reports[each.key].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.reports[each.key].arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  for_each = local.environments
  bucket   = aws_s3_bucket.reports[each.key].id
  rule {
    id     = "archive-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_transition {
      noncurrent_days = each.key == "dev" ? 30 : 90
      storage_class   = "STANDARD_IA"
    }
    noncurrent_version_expiration {
      noncurrent_days = each.key == "dev" ? 90 : 365
    }
  }
}

data "aws_iam_policy_document" "report_storage" {
  for_each = local.environments
  statement {
    actions   = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
    resources = ["${aws_s3_bucket.reports[each.key].arn}/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.reports[each.key].arn]
  }
  statement {
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.reports[each.key].arn]
  }
}

resource "aws_iam_role_policy" "report_storage" {
  for_each = local.environments
  name     = "report-storage-${each.key}"
  role     = aws_iam_role.application[each.key].id
  policy   = data.aws_iam_policy_document.report_storage[each.key].json
}
