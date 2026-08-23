# EBS-backed observability persistence design

## Scope

Add persistent AWS storage for the Kubernetes observability stack without
changing Workforce Risk application logic, the local Docker workflow, or any
current user-facing behavior.

## Selected design

The self-managed Kubernetes cluster uses the AWS EBS CSI driver to dynamically
provision encrypted `gp3` volumes. A cluster-scoped StorageClass uses
`WaitForFirstConsumer`, filesystem volume mode, expansion support, and a
`Retain` reclaim policy.

Each environment receives independent persistent storage:

- Prometheus: EBS-backed metrics storage with the configured retention period.
- Loki: EBS-backed log storage with the configured environment retention.
- Grafana: EBS-backed dashboard, user, and local configuration state.

Dev and prod PVCs are created in their respective namespaces and cannot share
volumes. Initial sizes remain cost-aware and may be expanded after measuring
ingestion and retention needs.

## Ownership and access

Terraform creates the least-privilege IAM role required by the EBS CSI
controller. The role is bound to the controller service account through the
cluster OIDC provider. Helm or Kubernetes manifests install the pinned EBS CSI
driver, StorageClass, and observability persistence settings.

Application service accounts receive no EBS permissions. Kubernetes workloads
consume only PVCs; they do not call the EC2 volume API directly.

## Data behavior

Grafana remains a visualization layer. Prometheus stores metrics, Loki stores
logs, and Grafana stores only its own state. Restarting or rescheduling a pod
reattaches its PVC and preserves data. Deleting a pod does not delete an EBS
volume. The `Retain` policy prevents automatic destruction when a PVC is
removed, so deliberate cleanup requires an explicit infrastructure operation.

Local Docker Compose continues to use the existing named volumes. EBS is used
only by Kubernetes workloads running on AWS.

## Failure behavior

- If EBS provisioning fails, the affected observability pod remains pending and
  exposes a visible Kubernetes event; application workloads continue running.
- Prometheus, Loki, and Grafana use separate claims so one full or unavailable
  volume does not corrupt the other stores.
- Volume expansion is allowed, but shrinking is not attempted.
- No observability storage failure changes workforce scores or Jira state.

## Validation

- Terraform validates the CSI IAM trust and least-privilege policy attachment.
- Kubernetes schema tests verify encryption, `gp3`, `Retain`, expansion, and
  namespace-isolated claims.
- Manifest or Helm rendering verifies that Prometheus, Loki, and Grafana mount
  their intended claims.
- A controlled restart test verifies that stored metrics, logs, and Grafana
  state remain available after pod replacement.
- A PVC deletion rehearsal verifies that the EBS volume is retained and that
  cleanup requires an explicit operation.

## Exclusions

This change does not deploy resources, modify GitHub workflows, alter
application code, change metrics or log schemas, or introduce a database for
Prometheus metrics.
