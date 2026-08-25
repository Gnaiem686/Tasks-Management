# Kubeadm node bootstrap and replacement

The Terraform root at `infra/terraform/environment` creates one shared cluster:
one private control-plane node and two private worker nodes. Development and
production remain Kubernetes namespaces in this cluster; this root must not be
applied once per application environment.

## Preconditions

- Record reviewed exact Kubernetes, containerd, and Calico versions in the
  Phase 0 compatibility matrix before planning a real deployment.
- Provide a trusted administration CIDR reachable through the approved
  administration path. World-open API or SSH access is rejected.
- Initialize the remote encrypted backend from Task 11.1 before an apply.

## Bootstrap behavior

The control plane initializes kubeadm and publishes only the worker join
command to an encrypted SSM `SecureString`. The token expires after the
configured window. Workers use their instance role to retrieve it with bounded
backoff and first check whether they are already joined. Cloud-init output and
the `workforce-kubeadm-control-plane` or `workforce-kubeadm-worker` journal tags
show failures. The join parameter is deleted automatically after the bootstrap
window.

## Token rotation and replacement workers

Use an SSM session on the control plane to create a new short-lived command:

```bash
sudo kubeadm token create --ttl 30m --print-join-command
```

Publish it to the existing encrypted parameter using the control-plane role,
increment `node_generation` only for the worker replacement being reviewed,
and apply the reviewed plan. Confirm all three nodes are Ready, then delete the
parameter. Never put the command, token, CA hash, or Terraform plan containing
sensitive values in Git or CI artifacts.

## Verification

Export `AWS_REGION` and the sensitive `JOIN_PARAMETER_NAME` Terraform output,
then run `scripts/validation/verify_node_join.sh`. It requires exactly one
Ready control plane, two Ready workers, and an absent join parameter. A failure
blocks add-on installation and application deployment.
