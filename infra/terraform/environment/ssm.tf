resource "aws_kms_key" "join_material" {
  description             = "Encrypt short-lived kubeadm join material"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_ssm_parameter" "kubeadm_join" {
  name   = "/${var.project_name}/${var.environment}/cluster/kubeadm-join"
  type   = "SecureString"
  key_id = aws_kms_key.join_material.arn
  value  = "pending-control-plane-bootstrap"
  lifecycle {
    ignore_changes = [value]
  }
}

resource "terraform_data" "node_generation" {
  input = var.node_generation
}
