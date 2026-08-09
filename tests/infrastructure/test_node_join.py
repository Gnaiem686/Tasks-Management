from pathlib import Path

ROOT = Path(__file__).parents[2]
TF_ROOT = ROOT / "infra" / "terraform" / "environment"
TEMPLATES = TF_ROOT / "templates"


def _terraform() -> str:
    return "\n".join(path.read_text() for path in TF_ROOT.glob("*.tf"))


def test_cluster_is_kubeadm_not_eks_and_nodes_are_private() -> None:
    terraform = _terraform().lower()
    assert "aws_eks_" not in terraform
    assert 'map_public_ip_on_launch = false' in terraform
    assert 'associate_public_ip_address = false' in terraform
    assert 'from_port   = 22' not in terraform
    assert 'var.admin_cidr != "0.0.0.0/0"' in terraform
    assert 'manage_via_ssm' in terraform
    assert 'load_balancer_type = "network"' in terraform
    assert 'source_security_group_id = aws_security_group.ingress_nlb.id' in terraform


def test_cluster_state_uses_encrypted_remote_locking() -> None:
    versions = (TF_ROOT / "versions.tf").read_text()
    assert 'backend "s3"' in versions
    assert 'encrypt      = true' in versions
    assert 'use_lockfile = true' in versions


def test_join_material_is_encrypted_short_lived_and_least_privilege() -> None:
    terraform = _terraform()
    assert 'type   = "SecureString"' in terraform
    assert "key_id = aws_kms_key.join_material.arn" in terraform
    assert 'join_token_ttl' in terraform
    assert 'ssm:GetParameter' in terraform
    assert 'ssm:PutParameter' in terraform
    assert 'ssm:DeleteParameter' in terraform
    assert 'resources = [aws_ssm_parameter.kubeadm_join.arn]' in terraform


def test_control_plane_publishes_minimal_join_material() -> None:
    script = (TEMPLATES / "control-plane.sh.tftpl").read_text()
    assert "kubeadm init" in script
    assert "kubeadm token create --ttl" in script
    assert "discovery-token-ca-cert-hash" in script
    assert "aws ssm put-parameter" in script
    assert "--type SecureString" in script
    assert "certificate-key" not in script


def test_worker_join_is_idempotent_bounded_and_observable() -> None:
    script = (TEMPLATES / "worker.sh.tftpl").read_text()
    assert "test -f /etc/kubernetes/kubelet.conf" in script
    assert "MAX_JOIN_ATTEMPTS=" in script
    assert "aws ssm get-parameter" in script
    assert "--with-decryption" in script
    assert "systemd-cat" in script
    assert "sleep_seconds" in script
    assert "exit 1" in script


def test_versions_are_explicit_and_replacement_is_supported() -> None:
    variables = (TF_ROOT / "variables.tf").read_text()
    compute = (TF_ROOT / "compute.tf").read_text()
    assert 'variable "kubernetes_version"' in variables
    assert 'variable "containerd_version"' in variables
    assert 'variable "calico_version"' in variables
    assert "validation {" in variables
    assert 'replace_triggered_by = [terraform_data.node_generation]' in compute


def test_verification_script_checks_topology_and_parameter_cleanup() -> None:
    script = (ROOT / "scripts" / "validation" / "verify_node_join.sh").read_text()
    assert "kubectl get nodes" in script
    assert 'control-plane' in script
    assert 'worker' in script
    assert "ssm get-parameter" in script
    assert "must be deleted" in script
