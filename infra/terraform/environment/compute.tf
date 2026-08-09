data "aws_ssm_parameter" "ubuntu_ami" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

locals {
  bootstrap = {
    aws_region                 = var.aws_region
    kubernetes_version         = var.kubernetes_version
    kubernetes_package_version = var.kubernetes_package_version
    containerd_version         = var.containerd_version
    calico_version             = var.calico_version
    join_parameter_name        = aws_ssm_parameter.kubeadm_join.name
    join_token_ttl             = var.join_token_ttl
  }
}

resource "aws_instance" "control_plane" {
  ami                         = data.aws_ssm_parameter.ubuntu_ami.value
  instance_type               = var.control_plane_instance_type
  subnet_id                   = aws_subnet.private[0].id
  associate_public_ip_address = false
  vpc_security_group_ids      = [aws_security_group.nodes.id]
  iam_instance_profile        = aws_iam_instance_profile.control_plane.name
  user_data                   = templatefile("${path.module}/templates/control-plane.sh.tftpl", local.bootstrap)
  user_data_replace_on_change = true

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 30
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  tags = { Name = "${var.project_name}-${var.environment}-control-plane", manage_via_ssm = "true" }
  lifecycle { replace_triggered_by = [terraform_data.node_generation] }
}

resource "aws_instance" "worker" {
  count                       = 2
  ami                         = data.aws_ssm_parameter.ubuntu_ami.value
  instance_type               = var.worker_instance_type
  subnet_id                   = aws_subnet.private[count.index].id
  associate_public_ip_address = false
  vpc_security_group_ids      = [aws_security_group.nodes.id]
  iam_instance_profile        = aws_iam_instance_profile.worker.name
  user_data                   = templatefile("${path.module}/templates/worker.sh.tftpl", local.bootstrap)
  user_data_replace_on_change = true

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 30
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  tags = { Name = "${var.project_name}-${var.environment}-worker-${count.index + 1}", manage_via_ssm = "true" }
  lifecycle { replace_triggered_by = [terraform_data.node_generation] }

  depends_on = [aws_instance.control_plane]
}

output "control_plane_instance_id" {
  value = aws_instance.control_plane.id
}

output "worker_instance_ids" {
  value = aws_instance.worker[*].id
}

output "join_parameter_name" {
  value     = aws_ssm_parameter.kubeadm_join.name
  sensitive = true
}
