# EBS Observability Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add encrypted EBS-backed persistent storage contracts for Prometheus, Loki, and Grafana in the self-managed AWS Kubernetes cluster.

**Architecture:** Terraform creates an OIDC-trusted EBS CSI controller role. A pinned upstream EBS CSI Helm release provisions encrypted `gp3` volumes through one retained StorageClass, while the Prometheus, Loki, and Grafana Helm values request independent namespace-scoped claims.

**Tech Stack:** Terraform AWS provider, Kubernetes StorageClass/PVCs, Helm, AWS EBS CSI Driver chart `2.63.1`, pytest, PyYAML.

## Global Constraints

- Do not modify Workforce Risk application logic.
- Do not deploy or modify GitHub workflows.
- Keep Docker Compose named volumes for local development.
- Use EBS only for Kubernetes workloads running on AWS.
- Use encrypted `gp3`, `WaitForFirstConsumer`, expansion support, and `Retain`.
- Keep Prometheus, Loki, and Grafana on separate namespace-scoped claims.

---

### Task 1: Define and test Kubernetes EBS persistence contracts

**Files:**
- Create: `tests/observability/test_ebs_persistence.py`
- Create: `infra/kubernetes/observability/ebs/storage-class.yaml`
- Create: `infra/kubernetes/observability/ebs/aws-ebs-csi-driver-values.yaml`
- Create: `infra/kubernetes/observability/ebs/kube-prometheus-stack-values.yaml`
- Create: `infra/kubernetes/observability/ebs/loki-values.yaml`
- Create: `infra/kubernetes/observability/ebs/versions.env`

**Interfaces:**
- Consumes: Kubernetes namespaces `dev` and `prod`; Terraform output `ebs_csi_controller_role_arn`.
- Produces: StorageClass `workforce-ebs-gp3-retain` and Helm persistence values for the three stores.

- [ ] **Step 1: Write failing manifest contract tests**

Assert that the StorageClass uses `ebs.csi.aws.com`, encrypted `gp3`, `Retain`, `WaitForFirstConsumer`, and expansion. Assert that EBS CSI chart version is exactly `2.63.1`, that the controller service-account role placeholder is present, and that Prometheus, Grafana, and Loki request separate EBS-backed storage.

- [ ] **Step 2: Verify the tests fail because the manifests are absent**

Run:

```bash
uv run pytest tests/observability/test_ebs_persistence.py -q
```

Expected: failures identify the missing EBS observability files.

- [ ] **Step 3: Add the minimal Kubernetes and Helm configuration**

Use this StorageClass contract:

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: workforce-ebs-gp3-retain
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  encrypted: "true"
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
```

Set Prometheus retention to `7d`, Prometheus storage to `10Gi`, Grafana storage to `2Gi`, and Loki storage to `10Gi`. Each Helm release receives the same StorageClass but creates its own claim within the release namespace.

- [ ] **Step 4: Verify manifest contracts pass**

Run:

```bash
uv run pytest tests/observability/test_ebs_persistence.py -q
```

Expected: all EBS persistence contract tests pass.

---

### Task 2: Add and test least-privilege EBS CSI IAM wiring

**Files:**
- Modify: `tests/infrastructure/test_iam_permissions.py`
- Create: `infra/terraform/environment/ebs_csi.tf`
- Modify: `infra/terraform/environment/outputs.tf`

**Interfaces:**
- Consumes: `aws_iam_openid_connect_provider.kubernetes`, `local.cluster_oidc_hostpath`, and AWS-managed `AmazonEBSCSIDriverPolicy`.
- Produces: IAM role `aws_iam_role.ebs_csi_controller` and sensitive output `ebs_csi_controller_role_arn`.

- [ ] **Step 1: Write failing Terraform contract tests**

Assert that the trust policy accepts only `system:serviceaccount:kube-system:ebs-csi-controller-sa`, requires audience `sts.amazonaws.com`, attaches only the AWS-managed EBS CSI driver policy, and exports the controller role ARN as sensitive.

- [ ] **Step 2: Verify the tests fail because IAM wiring is absent**

Run:

```bash
uv run pytest tests/infrastructure/test_iam_permissions.py -q
```

Expected: failure identifies missing `ebs_csi.tf` or output.

- [ ] **Step 3: Add the minimal Terraform IAM resources**

Create an `AssumeRoleWithWebIdentity` trust document bound to the exact EBS CSI controller service account. Attach `arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy` and expose only the resulting role ARN.

- [ ] **Step 4: Validate Terraform and run infrastructure tests**

Run:

```bash
terraform -chdir=infra/terraform/environment fmt -check
terraform -chdir=infra/terraform/environment init -backend=false
terraform -chdir=infra/terraform/environment validate
uv run pytest tests/infrastructure/test_iam_permissions.py tests/observability/test_ebs_persistence.py -q
```

Expected: Terraform validation succeeds and all targeted tests pass.

---

### Task 3: Verify scope and renderability

**Files:**
- Modify only the files listed in Tasks 1 and 2 if validation reveals a scoped defect.

**Interfaces:**
- Consumes: all EBS persistence configuration.
- Produces: fresh evidence that the change is isolated and renderable.

- [ ] **Step 1: Run YAML parsing and targeted test suite**

```bash
uv run pytest tests/observability tests/infrastructure/test_iam_permissions.py -q
```

Expected: the complete observability suite and IAM permission tests pass.

- [ ] **Step 2: Confirm application logic did not change**

```bash
git diff --name-only -- services domain packages
```

Expected: no new EBS-related edits under application directories.

- [ ] **Step 3: Review the scoped diff without deploying**

```bash
git diff -- infra/kubernetes/observability/ebs infra/terraform/environment tests/observability/test_ebs_persistence.py tests/infrastructure/test_iam_permissions.py
```

Expected: only EBS storage contracts, CSI IAM wiring, and their tests appear.

No GitHub push, merge, Terraform apply, Helm install, or Kubernetes apply is performed.
