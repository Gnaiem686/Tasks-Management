data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "control_plane" {
  name               = "${var.project_name}-${var.environment}-control-plane"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role" "worker" {
  name               = "${var.project_name}-${var.environment}-worker"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "control_plane_ssm_core" {
  role       = aws_iam_role.control_plane.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "worker_ssm_core" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "control_plane_join" {
  statement {
    actions   = ["ssm:PutParameter", "ssm:DeleteParameter"]
    resources = [aws_ssm_parameter.kubeadm_join.arn]
  }
  statement {
    actions   = ["kms:Encrypt"]
    resources = [aws_kms_key.join_material.arn]
  }
  statement {
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.cluster_oidc.arn}/.well-known/openid-configuration",
      "${aws_s3_bucket.cluster_oidc.arn}/openid/v1/jwks",
    ]
  }
}

resource "aws_iam_role_policy" "control_plane_join" {
  role   = aws_iam_role.control_plane.id
  policy = data.aws_iam_policy_document.control_plane_join.json
}

data "aws_iam_policy_document" "worker_join" {
  statement {
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.kubeadm_join.arn]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.join_material.arn]
  }
}

resource "aws_iam_role_policy" "worker_join" {
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker_join.json
}

data "aws_iam_policy_document" "worker_ecr_pull" {
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [
      "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/workforce-risk/*",
    ]
  }
}

resource "aws_iam_role_policy" "worker_ecr_pull" {
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker_ecr_pull.json
}

resource "aws_iam_instance_profile" "control_plane" {
  name = "${var.project_name}-${var.environment}-control-plane"
  role = aws_iam_role.control_plane.name
}

resource "aws_iam_instance_profile" "worker" {
  name = "${var.project_name}-${var.environment}-worker"
  role = aws_iam_role.worker.name
}
