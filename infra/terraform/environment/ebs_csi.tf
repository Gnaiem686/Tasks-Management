data "aws_iam_policy_document" "ebs_csi_controller_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.kubernetes.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.cluster_oidc_hostpath}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.cluster_oidc_hostpath}:sub"
      values   = ["system:serviceaccount:kube-system:ebs-csi-controller-sa"]
    }
  }
}

resource "aws_iam_role" "ebs_csi_controller" {
  name               = "${var.project_name}-${var.environment}-ebs-csi-controller"
  assume_role_policy = data.aws_iam_policy_document.ebs_csi_controller_assume.json
}

resource "aws_iam_role_policy_attachment" "ebs_csi_controller" {
  role       = aws_iam_role.ebs_csi_controller.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}
