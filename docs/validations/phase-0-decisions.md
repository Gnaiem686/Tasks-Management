# Phase 0 stakeholder decisions

Status: Approved

Approver: Project stakeholder and repository owner

Approved on: 2026-08-06

This record closes the stakeholder choices required before the technical Phase
0 validations begin. It does not authorize application implementation; Tasks
0.2 through 0.5 remain blocking.

## Decision checklist

| Decision | Outcome | Approver | Approved on |
| --- | --- | --- | --- |
| External project-management platform | Jira Cloud Free is selected for the MVP, subject to its plan limits and the approved synthetic-data model. | Project stakeholder and repository owner | 2026-08-06 |
| Jira MCP and REST boundary | Atlassian Rovo MCP remains the runtime integration. Runtime REST is permitted only if Phase 0 proves an essential MCP capability missing and a later architecture review approves it. Guarded REST automation may be used only for development seeding, validation, and cleanup where supported. | Project stakeholder and repository owner | 2026-08-06 |
| Kubernetes topology | Use upstream kubeadm on EC2 with one control-plane node and two worker nodes. The non-HA control-plane limitation is accepted for the MVP. Amazon EKS is prohibited. | Project stakeholder and repository owner | 2026-08-06 |
| RDS isolation | Use one encrypted RDS PostgreSQL instance with separate dev and prod databases, database users, credentials, Kubernetes Secrets, and access boundaries. Cross-environment access is prohibited. | Project stakeholder and repository owner | 2026-08-06 |
| Email delivery | Use Amazon SES in both dev and prod so the environments exercise the same adapter. No development SMTP fallback is approved. SES sandbox restrictions must be handled through validated recipients and documented promotion prerequisites. | Project stakeholder and repository owner | 2026-08-06 |
| Report format | Immutable JSON is required for the MVP. PDF is optional and cannot block completion. | Project stakeholder and repository owner | 2026-08-06 |
| Infrastructure automation | AWS resources may not be created manually in the AWS Console. Terraform owns AWS resources; unavoidable initial Atlassian administrator authorization may be documented. Repeatable Jira checks and data lifecycle operations must be scripted or API-driven where supported. | Project stakeholder and repository owner | 2026-08-06 |
| Manager interface | The Agent API serves a lightweight HTML/CSS/JavaScript manager UI directly. React, Vite, Node, and a separate frontend workload are excluded. | Project stakeholder and repository owner | 2026-08-06 |
| Application authentication | Application-managed, role-, environment-, and project-scoped API keys are selected for the MVP. Cognito is excluded. | Project stakeholder and repository owner | 2026-08-06 |
| Synthetic workforce model | Use seven synthetic workforce profiles and exactly two synthetic Jira accounts for the controlled reassignment demonstration. | Project stakeholder and repository owner | 2026-08-06 |
| Scenario execution | Scenario progression runs outside Kubernetes from a workstation or `run-scenario.yml`. Kubernetes contains only dev and prod namespaces; no simulator namespace or simulator workload is allowed. | Project stakeholder and repository owner | 2026-08-06 |

## Jira scope decision

Decision: Adopt the already validated temporary `WRD` project as the configured
development Jira scope for the MVP.

Approver: Project stakeholder and repository owner

Approved on: 2026-08-06

Development Jira key: `WRD`

The implementation configuration created in Task 1.2 must enforce:

- `allowed_project_keys` for dev contains only `WRD`;
- `mutation_project_key` for dev is exactly `WRD`;
- no replacement project is created or configured unless a later approved
  change replaces this decision and repeats all MCP smoke tests;
- `WORKFORCE-PROD` is production-scoped, read-only, and forbidden to seed,
  clean, or mutate;
- dev identities, credentials, simulator tooling, and cleanup tooling cannot
  access `WORKFORCE-PROD`.

## Automation boundary

No AWS resource may be created through the AWS Console. Terraform provisions
AWS infrastructure, bootstrap automation installs the cluster, Helm or
manifests manage Kubernetes resources, and GitHub Actions owns application
release promotion.

An unavoidable initial Atlassian administrator authorization may be completed
interactively and recorded without credentials. After that authorization,
repeatable Jira discovery, custom-field validation, seeding, permission checks,
scenario execution, and cleanup must be scripted or API-driven where Atlassian
supports it.

## Gate result

Task 0.1 decision completeness: PASS

Task 0.1 scope-safety definition: PASS

Phase 0 overall: BLOCKED until Tasks 0.2, 0.3, 0.4, and 0.5 pass.
