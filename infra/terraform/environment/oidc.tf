locals {
  cluster_oidc_bucket   = "${var.project_name}-k8s-oidc-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  cluster_oidc_issuer   = "https://${local.cluster_oidc_bucket}.s3.${var.aws_region}.amazonaws.com"
  cluster_oidc_hostpath = trimsuffix(trimprefix(local.cluster_oidc_issuer, "https://"), "/")
}

resource "aws_s3_bucket" "cluster_oidc" {
  bucket        = local.cluster_oidc_bucket
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "cluster_oidc" {
  bucket                  = aws_s3_bucket.cluster_oidc.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cluster_oidc" {
  bucket = aws_s3_bucket.cluster_oidc.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

data "aws_iam_policy_document" "cluster_oidc_public_keys" {
  statement {
    sid     = "ReadOnlyPublicDiscovery"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.cluster_oidc.arn}/.well-known/openid-configuration",
      "${aws_s3_bucket.cluster_oidc.arn}/openid/v1/jwks",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_s3_bucket_policy" "cluster_oidc_public_keys" {
  bucket     = aws_s3_bucket.cluster_oidc.id
  policy     = data.aws_iam_policy_document.cluster_oidc_public_keys.json
  depends_on = [aws_s3_bucket_public_access_block.cluster_oidc]
}

resource "terraform_data" "cluster_oidc_ready" {
  triggers_replace = [aws_instance.control_plane.id]
  depends_on       = [aws_instance.control_plane]

  provisioner "local-exec" {
    command     = <<-EOT
      set -Eeuo pipefail
      for attempt in $(seq 1 60); do
        if aws s3api head-object --region '${var.aws_region}' --bucket '${local.cluster_oidc_bucket}' --key '.well-known/openid-configuration' >/dev/null 2>&1 && aws s3api head-object --region '${var.aws_region}' --bucket '${local.cluster_oidc_bucket}' --key 'openid/v1/jwks' >/dev/null 2>&1; then
          exit 0
        fi
        sleep 10
      done
      echo 'Timed out waiting for public Kubernetes OIDC documents' >&2
      exit 1
    EOT
    interpreter = ["/bin/bash", "-c"]
  }
}

resource "aws_iam_openid_connect_provider" "kubernetes" {
  url            = local.cluster_oidc_issuer
  client_id_list = ["sts.amazonaws.com"]
  depends_on     = [terraform_data.cluster_oidc_ready]
}

output "cluster_oidc_issuer" {
  value = local.cluster_oidc_issuer
}
