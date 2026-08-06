# AI Project Workforce Risk Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy an explainable workforce-risk system that reads synthetic Jira Cloud work data through Atlassian Rovo MCP, combines it with authoritative workforce profiles, calculates deterministic risk, supports manager investigation and safe simulation, and performs one explicitly approved and verified Jira assignee update.

**Architecture:** A lightweight HTML/CSS/JavaScript manager UI is served directly by the API-key-protected FastAPI/LangGraph Agent API. The mandatory MVP uses a constrained Supervisor workflow; the selected extra-credit topology adds Workforce Analysis, Project Delivery, Reassignment Planning, and Operations Diagnostic specialist agents with typed handoffs and deterministic degraded fallback. MCP servers remain tools, and the domain-centric Workforce Risk MCP retains deterministic logic and transactional state. PostgreSQL stores authoritative workflow state and seven synthetic profiles, Jira Cloud stores seeded synthetic tasks, S3 stores immutable JSON reports, an outbox feeds SQS and the notification worker, and all custom workloads run in `dev` and `prod` namespaces on a Terraform-provisioned kubeadm cluster on EC2.

**Tech Stack:** Python, FastAPI, Pydantic, Jinja2/static HTML/CSS/JavaScript, LangGraph, the official Python MCP SDK, SQLAlchemy, Alembic, PostgreSQL, Amazon Bedrock, RDS, S3, SQS, SES, Terraform, kubeadm, containerd, Calico, NGINX Ingress, External Secrets Operator, Prometheus, Alertmanager, Grafana, Loki, OpenTelemetry, Docker, Kubernetes, and GitHub Actions. Exact compatible versions are a blocking Phase 0 output.

## Global Constraints

- `docs/spec.md` is authoritative. Do not redesign its approved domain-centric architecture.
- The governing failure rule is **read degraded; write closed**.
- Risk scores are deterministic, reproducible, auditable, clamped to `0–100`, and immutable once recorded.
- Bedrock explains deterministic results; it never creates or alters scores, candidates, approvals, or proposal state.
- The mandatory Supervisor workflow and the four selected extra-credit
  specialist agents orchestrate typed workflows only. MCP servers are tools,
  not agents, and Workforce Risk MCP exclusively owns scoring, candidate
  eligibility, simulations, proposals, approvals, execution, reconciliation,
  and audit state.
- Agent API authentication and primary authorization complete before LangGraph
  runs. Agents receive typed verified context and never receive raw API keys.
- The Agent API never forwards raw manager API keys to Workforce Risk MCP. It
  issues a signed, short-lived internal authorization context over the
  authenticated service transport; raw keys never enter graph state, prompts,
  MCP arguments, logs, traces, handoffs, audits, errors, or memory.
- Jira comments and descriptions are untrusted free text, not confirmed Jira
  facts. MVP comment classification is deterministic and explicit-pattern-only;
  general Bedrock/LLM comment interpretation is deferred.
- Use only work-planning data. Never infer or use protected characteristics or personal proxies.
- Atlassian Rovo MCP is the primary runtime Jira boundary. Do not implement a
  runtime Jira REST fallback unless Phase 0 proves an essential MVP capability
  missing or insufficiently structured. Guarded official REST use is permitted
  only for dev setup, bulk seeding, validation, reset, and cleanup.
- Chat text is never approval. Approval uses a dedicated authenticated endpoint and exact proposal ID.
- Do not implement Jira mutation until authorization, proposal state, evidence freshness, confidence, audit chaining, idempotency, optimistic preconditions, and read-back verification are complete and passing.
- Never generically retry a Jira mutation. Ambiguous outcomes become `uncertain` and enter reconciliation.
- Jira development mutations use only the configured synthetic dev project. Production Jira tests are read-only.
- Scenario progression runs only from external workstation/GitHub Actions test
  tooling against `WORKFORCE-SIM`. Do not create a simulation namespace,
  simulator container, pod, Job, CronJob, service, or LangGraph tool.
- Amazon EKS is not used.
- Dev and prod use isolated credentials, Jira scopes, databases, buckets,
  queues, DLQs, secrets, Kubernetes service accounts, release configuration,
  API-key records/secret delivery, and IAM.
- Dev and prod therefore receive separate buckets, queues, DLQs, secrets,
  service accounts, release configuration, and Jira scopes.
- Unit tests use no network and no real credentials. They mock Bedrock/LLM,
  Jira, AWS services, Kubernetes, Prometheus, Loki, GitHub, and repositories
  where appropriate.
- Secrets never enter Git, browser code, logs, traces, reports, ordinary Terraform variables, or non-sensitive outputs.
- Every API, MCP, scan, queue, and mutation workflow propagates an environment and correlation ID.
- Every task follows test-first development and ends at a reviewable commit checkpoint.
- Phase 0 is blocking. Tasks in Phase 1 or later must not start until its validation gate passes.

## Proposed repository map

The following paths are fixed for this plan:

```text
.
├── .env.example
├── .github/workflows/
├── Makefile
├── config/
│   ├── environments/{dev,prod,test}.yaml
│   ├── scoring/v1.yaml
│   └── versions.env
├── domain/workforce_risk/
├── services/
│   ├── agent-api/             # API plus lightweight manager UI
│   ├── workforce-risk-mcp/
│   ├── devops-mcp/
│   └── notification-worker/
├── packages/
│   ├── contracts/
│   ├── jira-mcp-client/
│   ├── observability/
│   └── persistence/
├── infra/
│   ├── terraform/{bootstrap,shared,environment}/
│   └── kubernetes/{base,overlays/dev,overlays/prod,observability}/
├── scripts/
│   ├── jira/
│   ├── scenario/
│   ├── demo/
│   └── validation/
├── skills/
│   ├── workforce-risk-triage/SKILL.md
│   ├── deploy-and-verify-environment/SKILL.md
│   └── safe-jira-reassignment-demo/SKILL.md
├── tests/
│   ├── contract/
│   ├── integration/
│   ├── e2e/
│   ├── infrastructure/
│   ├── performance/
│   └── security/
└── docs/
    ├── spec.md
    ├── plan.md
    ├── test-plan.md
    ├── validations/
    ├── runbooks/
    └── test-mapping.md
```

## Stable cross-component interfaces

These names remain consistent throughout implementation:

- `JiraEvidenceClient.get_issue(issue_key, correlation_id) -> JiraIssueEvidence`
- `JiraEvidenceClient.search_issues(jql, correlation_id) -> list[JiraIssueEvidence]`
- `JiraEvidenceClient.resolve_account(query, correlation_id) -> JiraAccountRef`
- `JiraMutationClient.assign_issue(command: AssignIssueCommand) -> JiraMutationReceipt`
- `OverloadScorer.score(input: EmployeeOverloadInput) -> RiskResult`
- `TaskFitScorer.score(input: TaskFitInput) -> RiskResult`
- `ProjectDeliveryScorer.score(input: ProjectDeliveryInput) -> RiskResult`
- `SimulationService.simulate(command: ReassignmentSimulationCommand) -> SimulationResult`
- `ProposalService.create(command: CreateProposalCommand) -> ReassignmentProposal`
- `ProposalService.approve(command: ApproveProposalCommand, principal: Principal) -> ExecutionOperation`
- `ReconciliationService.reconcile(proposal_id, correlation_id) -> ExecutionOperation`
- `CommentEvidenceClassifier.classify(input: JiraCommentObservation) -> CommentEvidenceSignal | None`
- All MCP envelopes use `schema_version`, `environment`, `correlation_id`, `evidence_timestamp`, `status`, `data`, and `error`.

---

# Phase 0 — Pre-implementation validations

## Task 0.1: Close stakeholder decisions and choose the Jira development scope

**Classification:** Security/Hardening

**Objective:** Record every open stakeholder decision and select either temporary project `WRD` or a newly created `WORKFORCE-DEV` as the single configured development scope.

**Why this task is needed:** Project keys, access policies, smoke tests, cleanup guards, RDS topology, notification adapter, and report scope cannot be implemented safely while their approval gates remain ambiguous.

**Dependencies:** Approved `docs/spec.md`; stakeholder and architecture-review availability.

**Files or directories:**

- Create: `docs/validations/phase-0-decisions.md`
- Reference: `docs/spec.md` Sections 6.1, 6.4, 7, and 23.1

**Tests to write first:**

- Define a validation checklist in `docs/validations/phase-0-decisions.md` that fails while any required decision has no named approver, date, and outcome.
- Define acceptance checks for `allowed_project_keys`, `mutation_project_key`, and forbidden `WORKFORCE-PROD`.

**Detailed implementation steps:**

- [ ] Record decisions for Jira Cloud SaaS use, Jira REST contingency, kubeadm
  topology, RDS isolation, dev SMTP contingency, JSON-only MVP reports, and the
  no-manual-clicking boundary.
- [ ] Record Jira Cloud Free as the selected plan, its ten-user boundary and
  reduced permission controls, the seven-profile/two-account synthetic model,
  the lightweight FastAPI UI, and scoped API keys replacing Cognito.
- [ ] Record that no AWS resource may be created through the AWS Console; note
  any unavoidable initial Atlassian administrator consent separately.
- [ ] Require repeatable Jira validation, custom-field checks, seeding,
  permission checks, and cleanup to be scripted or API-driven where Atlassian
  supports automation.
- [ ] Record the selected development key as exactly `WRD` or `WORKFORCE-DEV`; do not permit both as mutation scopes.
- [ ] Keep the selected key only in the Phase 0 decision record; do not create
  or modify environment configuration in this task.
- [ ] Record `WORKFORCE-PROD` as read-only and forbidden to seed, clean, or mutate.
- [ ] If `WORKFORCE-DEV` is selected, create it through an approved Jira administrative process and repeat the already-proven discovery, custom-field, account-resolution, assignee-update, and read-back checks.
- [ ] Obtain stakeholder signatures in the validation record.

**Commands to run:**

```bash
rg -n "Decision:|Approver:|Approved on:|Development Jira key:" docs/validations/phase-0-decisions.md
rg -n "WRD|WORKFORCE-DEV|WORKFORCE-PROD" docs/validations/phase-0-decisions.md
```

**Expected output or observable result:** One approved development key is
recorded in `docs/validations/phase-0-decisions.md`, production remains
explicitly read-only, and no environment configuration file has been created
or modified by this task.

**Validation gate:** Architecture reviewer signs Phase 0 decisions; the selected Jira key is accessible with synthetic data.

**Commit checkpoint:** `docs: record phase zero architecture decisions`

## Task 0.2: Prove unattended Jira MCP authentication and required tools

**Classification:** Security/Hardening

**Objective:** Prove non-interactive Atlassian Rovo MCP startup with a dedicated least-privilege integration identity and verify every required read/write operation within the chosen dev project.

**Why this task is needed:** The configured development client proved MCP functionality but did not prove unattended authentication suitable for CronJobs and services.

**Dependencies:** Task 0.1; Atlassian administrator; exactly two synthetic Jira
accounts in total—the dedicated integration/demo-current-assignee identity and
one reassignment target.

**Files or directories:**

- Create: `docs/validations/jira-mcp-unattended-auth.md`
- Create: `docs/validations/jira-mcp-tool-matrix.json`
- Create: `scripts/validation/verify_jira_scope.sh`
- Create: `scripts/jira/{validate_fields,verify_permissions}.py`
- Do not create a runtime Jira REST adapter; guarded dev-administration REST
  scripts are planned only in Task 3.6.

**Tests to write first:**

- Checklist for non-interactive startup, credential rotation, restart without
  browser consent, project filtering, `Blocker Category`, `Workforce Employee
  ID`, account lookup for exactly two synthetic write-demo users, single
  assignee update, read-back, and refusal outside the dev key.
- Failure cases for expired/revoked credentials, forbidden project, rate limiting, malformed fields, and unavailable MCP.

**Detailed implementation steps:**

- [ ] Configure one of the two synthetic accounts as the dedicated
  integration/demo-current-assignee identity and the other as the reassignment
  target; do not create additional employee accounts.
- [ ] Store its credential outside Git and document rotation/revocation without recording the secret.
- [ ] Start an MCP client twice without interactive login and record sanitized evidence.
- [ ] Discover the Jira resource and assert only approved project keys are accepted by the application-side allowlist.
- [ ] Search the selected dev project with JQL and read a synthetic issue.
- [ ] Verify standard fields and mapped `Blocker Category` through structured MCP output.
- [ ] Verify `Workforce Employee ID` is structured and supports values
  `EMP-001` through `EMP-007` without requiring seven Jira accounts.
- [ ] Record the Jira Free permission limitation and prove the application-side
  site/project allowlist rejects every nonconfigured scope.
- [ ] Resolve a synthetic account and perform one controlled assignee update.
- [ ] Read back and compare the exact target account ID; do not retry mutation on ambiguity.
- [ ] Rotate the credential and repeat a read after restart.
- [ ] Run scripted custom-field and permission checks twice and confirm
  identical results without another interactive consent step.
- [ ] Record MCP coverage as complete. If and only if an essential capability fails, stop and request architecture approval before adding any REST task to this plan.

**Commands to run:**

```bash
bash scripts/validation/verify_jira_scope.sh
jq -e '.authentication.non_interactive == true and .authentication.rotation_verified == true' docs/validations/jira-mcp-tool-matrix.json
jq -e '.tools.read_issue and .tools.custom_fields and .tools.resolve_account and .tools.assign_issue and .tools.read_back' docs/validations/jira-mcp-tool-matrix.json
```

**Expected output or observable result:** All `jq` expressions return `true`; logs contain no credential; the mutation and read-back match exactly.

**Validation gate:** Security reviewer approves unattended authentication, rotation, project scope, and tool coverage. Phase 0 fails if this gate fails.

**Commit checkpoint:** `docs: validate unattended Jira MCP integration`

## Task 0.3: Validate Amazon Bedrock access and fallback assumptions

**Classification:** Security/Hardening

**Objective:** Verify the chosen AWS region exposes an approved Bedrock model to the project role and document the deterministic fallback path.

**Why this task is needed:** Bedrock explanations must not become a deployment blocker or weaken deterministic endpoints.

**Dependencies:** AWS account access and selected deployment region.

**Files or directories:**

- Create: `docs/validations/bedrock-access.md`
- Create: `docs/validations/bedrock-model.json`

**Tests to write first:**

- Validation checklist for model access, IAM-denied behavior, timeout behavior, structured JSON response, regional availability, and absence of sensitive prompt content.

**Detailed implementation steps:**

- [ ] Select one Bedrock model available in the deployment region and record its exact model ID.
- [ ] Invoke it with a synthetic, minimized risk result and validate a structured explanation.
- [ ] Deny model permission temporarily in a test role and confirm the planned fallback remains sufficient.
- [ ] Record timeout, retry budget, maximum token budget, and circuit-breaker assumptions for implementation.

**Commands to run:**

```bash
aws bedrock list-foundation-models --region "$(jq -r '.region' docs/validations/bedrock-model.json)"
jq -e '.model_id != "" and .region != "" and .structured_output_verified == true and .fallback_verified == true' docs/validations/bedrock-model.json
```

**Expected output or observable result:** The selected model is listed and both validation booleans are true.

**Validation gate:** Cloud/security reviewer accepts the model, region, IAM boundary, and fallback.

**Commit checkpoint:** `docs: validate Bedrock model access`

## Task 0.4: Select and pin compatible platform versions

**Classification:** Infrastructure

**Objective:** Produce one reviewed compatibility matrix and exact version pins for all runtimes, cluster components, and observability charts.

**Why this task is needed:** kubeadm skew, CNI compatibility, Helm chart compatibility, and reproducible builds are blocking infrastructure constraints.

**Dependencies:** Tasks 0.1–0.3.

**Files or directories:**

- Create: `config/versions.env`
- Create: `docs/validations/version-matrix.md`

**Tests to write first:**

- A shell validation that every required key occurs exactly once and contains an exact version, not `latest`, a wildcard, or a range.

**Detailed implementation steps:**

- [ ] Select exact versions for Python, Kubernetes, kubectl, kubeadm, kubelet, containerd, Calico, NGINX Ingress, metrics-server, External Secrets Operator, Prometheus stack, Grafana, Loki, log collector, OpenTelemetry collector, Terraform, Helm, and PostgreSQL.
- [ ] Validate Kubernetes supported-version skew and each chart's Kubernetes range.
- [ ] Record source links, validation date, and upgrade owner.
- [ ] Make every later Dockerfile, bootstrap script, workflow, and Helm release read these pins.

**Commands to run:**

```bash
required='PYTHON_VERSION KUBERNETES_VERSION CONTAINERD_VERSION CALICO_VERSION INGRESS_VERSION METRICS_SERVER_VERSION EXTERNAL_SECRETS_VERSION PROMETHEUS_STACK_VERSION GRAFANA_VERSION LOKI_VERSION OTEL_COLLECTOR_VERSION TERRAFORM_VERSION HELM_VERSION POSTGRES_VERSION'
for key in $required; do test "$(grep -c "^${key}=" config/versions.env)" -eq 1; done
! rg -n 'latest|\\*|>=|~|\\^' config/versions.env
```

**Expected output or observable result:** Both commands exit zero and the compatibility document has reviewer approval.

**Validation gate:** Version compatibility is approved; Phase 0 completes only
after Tasks 0.1–0.5 all pass.

**Commit checkpoint:** `build: pin validated platform versions`

## Task 0.5: Record HPA measurement and Argo CD decisions

**Classification:** Infrastructure

**Objective:** Define the production HPA target/metric validation and record
whether optional Argo CD hardening is adopted or omitted.

**Why this task is needed:** The specification requires at least one measured
production HPA and an explicit GitOps decision while keeping GitHub Actions plus
Helm/manifests as the MVP deployment path.

**Dependencies:** Tasks 0.1 and 0.4.

**Files or directories:**

- Create: `docs/validations/hpa-target.md`
- Create: `docs/validations/argocd-decision.md`
- Create: `scripts/validation/validate_hpa_evidence.sh`

**Tests to write first:**

- A validation script that rejects a missing workload target, metric source,
  load profile, minimum/maximum replicas, scale-out threshold, stabilization
  criterion, or evidence location.
- A decision check accepting exactly `adopt` or `omit`, and rejecting any claim
  that Argo CD is required for MVP.

**Detailed implementation steps:**

- [ ] Select Agent API or Workforce Risk MCP as the provisional production HPA
  target and document why its measured workload can drive scaling.
- [ ] Define the CPU or bounded-cardinality custom metric, representative load
  profile, thresholds, replica range, stabilization window, and final
  production acceptance test.
- [ ] Mark final HPA parameters provisional until Task 12.2 records
  production-shaped
  load-test evidence; production promotion remains blocked until that evidence
  passes.
- [ ] Record `adopt` or `omit` for Argo CD. For `omit`, retain GitHub Actions
  plus Helm/manifests. For `adopt`, defer implementation to optional Task 14.4
  without changing the MVP path.

**Commands to run:**

```bash
bash scripts/validation/validate_hpa_evidence.sh --definition docs/validations/hpa-target.md
rg -n '^Decision: (adopt|omit)$|^MVP deployment path: GitHub Actions \\+ Helm/manifests$' docs/validations/argocd-decision.md
```

**Expected output or observable result:** The HPA validation contract is
complete, the final evidence gate is explicit, and Argo CD has one recorded
decision without becoming an MVP dependency.

**Validation gate:** Infrastructure reviewer approves the provisional HPA
measurement contract and the Argo CD adoption/omission record.

**Commit checkpoint:** `docs: define HPA and GitOps validation gates`

---

# Phase 1 — Repository foundation

## Task 1.1: Scaffold the monorepo and dependency management

**Classification:** MVP

**Objective:** Establish the approved service, package, domain, test,
infrastructure, and embedded lightweight-UI boundaries with reproducible Python
dependency management.

**Why this task is needed:** Every later task needs stable import paths, commands, lockfiles, and ownership boundaries.

**Dependencies:** Phase 0 complete.

**Files or directories:**

- Create: `pyproject.toml`, `uv.lock`
- Create: `.python-version`, `.gitignore`, `.dockerignore`, `Makefile`, `README.md`
- Create: `domain/workforce_risk/__init__.py`
- Create: `services/{agent-api,workforce-risk-mcp,devops-mcp,notification-worker}/pyproject.toml`
- Create: `packages/{contracts,jira-mcp-client,observability,persistence}/pyproject.toml`
- Create all test directories from the repository map.

**Tests to write first:**

- `tests/test_repository_layout.py` asserting every planned top-level path and workspace member exists.

**Detailed implementation steps:**

- [ ] Configure a Python workspace and lock Python dependencies with `uv`.
- [ ] Add Ruff, mypy, pytest, pytest-asyncio, coverage, HTML validation, and
  Python Playwright configuration for the FastAPI-served static UI.
- [ ] Register separate `unit`, `contract`, `integration`, `e2e`,
  `infrastructure`, `performance`, and `security` test markers. Configure the
  unit suite to deny network sockets and fail when real credential environment
  variables are present.
- [ ] Provide unit fixtures that mock Bedrock/LLM, Jira, AWS, Kubernetes,
  Prometheus, Loki, GitHub, and repository boundaries.
- [ ] Add Make targets `bootstrap`, `lint`, `typecheck`, `test-unit`,
  `test-integration`, `ui-test`, and `check`.
- [ ] Document local prerequisites and the Phase 0 gate in `README.md`.

**Commands to run:**

```bash
uv sync --all-packages
make lint
make typecheck
uv run pytest tests/test_repository_layout.py -q
```

**Expected output or observable result:** Dependency installs are locked; lint/type checks pass; the layout test reports one passing test.

**Validation gate:** A clean clone can run `make bootstrap && make check` without undocumented steps or secrets.

**Commit checkpoint:** `build: scaffold workforce risk monorepo`

## Task 1.2: Add typed shared configuration and secret boundaries

**Classification:** Security/Hardening

**Objective:** Define environment-safe configuration schemas and examples without storing secrets.

**Why this task is needed:** Project scope, custom fields, AWS resources, scoring version, and external endpoints must be explicit and isolated.

**Dependencies:** Task 1.1.

**Files or directories:**

- Create: `.env.example`
- Create: `config/environments/{dev,prod,test}.yaml`
- Create: `packages/contracts/src/workforce_contracts/config.py`
- Create: `packages/contracts/tests/test_config.py`
- Create: `docs/security/secrets.md`

**Tests to write first:**

- Reject unknown environment, overlapping dev/prod Jira mutation scopes,
  production mutation enablement, missing `Blocker Category` or `Workforce
  Employee ID` mapping, literal API keys/secrets, and `WORKFORCE-PROD`
  seed/cleanup.

**Detailed implementation steps:**

- [ ] Define `EnvironmentConfig`, `JiraConfig`, `AwsConfig`, `AuthConfig`, `LimitsConfig`, and `ScoringConfigRef`.
- [ ] Read the approved development Jira key from
  `docs/validations/phase-0-decisions.md` and apply it to
  `config/environments/dev.yaml` as the sole dev mutation scope.
- [ ] Store only secret references, never secret values.
- [ ] Set `custom_fields.blocker_category` to the environment-specific ID established in Phase 0.
- [ ] Set `custom_fields.workforce_employee_id` and the seven permitted
  `EMP-001`–`EMP-007` values from the approved seed contract.
- [ ] Configure API-key HMAC pepper references, cache TTL, role, environment,
  and Jira-project scope rules without storing any raw key.
- [ ] Make `prod.jira.allow_mutations` false and configure read-only smoke checks.
- [ ] Add a configuration fingerprint for evidence and deployment metadata.

**Commands to run:**

```bash
uv run pytest packages/contracts/tests/test_config.py -q
uv run python -m workforce_contracts.config --validate config/environments/dev.yaml
uv run python -m workforce_contracts.config --validate config/environments/prod.yaml
```

**Expected output or observable result:** Tests pass; both files validate; prod mutation and dev/prod overlap tests fail closed.

**Validation gate:** Security reviewer confirms no secret values and environment isolation is explicit.

**Commit checkpoint:** `feat: add environment-safe configuration contracts`

## Task 1.3: Establish the initial CI validation skeleton

**Classification:** Infrastructure

**Objective:** Run repository, lint, typing, unit, lightweight browser-UI,
secret, dependency, and artifact checks on every pull request.

**Why this task is needed:** Every vertical slice needs an automated quality gate from its first commit.

**Dependencies:** Tasks 1.1–1.2.

**Files or directories:**

- Create: `.github/workflows/ci.yml`
- Create: `.github/dependabot.yml`
- Create: `.github/pull_request_template.md`
- Create: `scripts/validation/check_no_secrets.sh`

**Tests to write first:**

- Add fixture-based tests proving the secret scanner catches a fake Jira token and ignores `.env.example` placeholders.

**Detailed implementation steps:**

- [ ] Configure workflow concurrency to cancel superseded PR runs.
- [ ] Add pinned Python setup, locked installs, cache keys, `make check`, static
  asset validation, and browser UI tests.
- [ ] Upload JUnit, coverage, dependency, and secret-scan summaries even on test failure.
- [ ] Publish a GitHub Actions job summary and JUnit-compatible results for
  Python and browser UI tests.
- [ ] Upload coverage to Codecov or an approved equivalent and make the status
  available to branch protection.
- [ ] Define retained artifact groups for failed-test diagnostics, security and
  vulnerability reports, SBOMs, Terraform plans/summaries, Kubernetes
  validation, and deployment/smoke-test results; upload empty/not-applicable
  manifests until later phases produce each artifact.
- [ ] Use minimal workflow permissions and no AWS credentials.

**Commands to run:**

```bash
actionlint .github/workflows/ci.yml
bash scripts/validation/check_no_secrets.sh
make check
```

**Expected output or observable result:** Local workflow validation succeeds and a test PR produces one consolidated required CI check.

**Validation gate:** Branch protection can require `ci` without permitting direct protected-branch pushes.

**Commit checkpoint:** `ci: add pull request quality gate`

## Task 1.4: Create the executable test plan and requirement mapping

**Classification:** Security/Hardening

**Objective:** Define test categories, isolation boundaries, commands, success
criteria, and traceability before feature implementation expands.

**Why this task is needed:** The specification requires an inspectable test
plan, and later tasks need one stable place to map automated evidence.

**Dependencies:** Tasks 1.1–1.3.

**Files or directories:**

- Create: `docs/test-plan.md`
- Create: `docs/test-mapping.md`
- Create: `tests/test_test_plan_contract.py`

**Tests to write first:**

- Assert every numbered specification requirement has a mapping row.
- Assert unit tests prohibit network and credentials and list all required
  mocked boundaries.
- Assert the mandatory Agent API→Workforce Risk MCP separate-process
  Streamable HTTP test has a named command and success criterion.

**Detailed implementation steps:**

- [ ] Document required PR, dev smoke, optional live Bedrock, and controlled
  dev-only failure-injection categories.
- [ ] Define unit, contract, integration, end-to-end, infrastructure,
  performance, accessibility, and security entry criteria and success criteria.
- [ ] Record exact commands and CI artifact names.
- [ ] Map each requirement number from `docs/spec.md` to planned test files,
  initially marked `planned`.
- [ ] Map comment-evidence safety to Task 3.5, API-key authentication and
  raw-key exclusion to Tasks 3.2/6.2, add-on/manifest readiness to Task 11.4,
  dev deployment to Task 12.1, production-shaped HPA evidence to Task 12.2, and
  protected exact-digest promotion to Task 12.3.
- [ ] Map the FastAPI-served manager UI to Tasks 2.5/4.3/6.3/8.1 and the
  seven-profile/two-account automated dataset plus guarded dev-only REST setup
  boundary to Task 3.6.
- [ ] Map the external-only scenario progression/evaluator, real-MCP observation,
  `run-scenario.yml`, Kubernetes-absence, and production-refusal requirements
  to Tasks 3.6, 11.4, and 13.2.

**Commands to run:**

```bash
uv run pytest tests/test_test_plan_contract.py -q
rg -n 'no network|no real credentials|Streamable HTTP|separate real processes' docs/test-plan.md
```

**Expected output or observable result:** The contract test passes and every
specification requirement has an explicit planned test evidence row.

**Validation gate:** Reviewers can locate the command, boundary, and success
criterion for each required test category.

**Commit checkpoint:** `docs: add executable test strategy and mapping`

---

# Phase 2 — Smallest vertical slice

## Task 2.1: Implement typed Jira MCP read contracts and adapter

**Classification:** MVP

**Objective:** Read one issue through Rovo MCP and return normalized, typed, source-attributed evidence.

**Why this task is needed:** This is the external evidence boundary for the first working flow and every later scoring workflow.

**Dependencies:** Phase 0; Phase 1.

**Files or directories:**

- Create: `packages/contracts/src/workforce_contracts/jira.py`
- Create: `packages/jira-mcp-client/src/jira_mcp_client/client.py`
- Create: `packages/jira-mcp-client/src/jira_mcp_client/normalize.py`
- Create: `packages/jira-mcp-client/tests/test_normalize.py`
- Create: `tests/contract/test_jira_mcp_read.py`
- Create: `tests/fixtures/jira/wrd_1_structured.json`

**Tests to write first:**

- Parse key, summary, status, priority, assignee, account ID, due date, estimates, links, activity timestamp, and mapped custom fields.
- Reject wrong schema version, environment mismatch, missing timestamp/correlation ID, malformed assignee, unknown custom-field shape, and prompt-like text affecting control flow.
- Verify `Blocker Category` is sourced from the structured custom field, never comments/description.

**Detailed implementation steps:**

- [ ] Define `JiraIssueEvidence`, `JiraAccountRef`, `JiraCustomFieldValue`, `EvidenceRef`, and typed MCP envelope models.
- [ ] Implement `JiraEvidenceClient.get_issue` with timeout, read-only retry budget, correlation ID, circuit breaker, and project allowlist.
- [ ] Normalize raw field IDs through environment mapping.
- [ ] Preserve untrusted free text as quoted evidence and exclude it from instructions.
- [ ] Add a real MCP transport contract test against the configured synthetic dev project, guarded from production.

**Commands to run:**

```bash
uv run pytest packages/jira-mcp-client/tests/test_normalize.py -q
uv run pytest tests/contract/test_jira_mcp_read.py -q
```

**Expected output or observable result:** `WRD-1` or its approved replacement normalizes deterministically, including `Blocker Category`, with no REST calls.

**Validation gate:** Contract test proves real MCP transport success and typed failure behavior.

**Commit checkpoint:** `feat: add typed Jira MCP evidence reader`

## Task 2.2: Implement the first deterministic employee-overload score

**Classification:** MVP

**Objective:** Calculate a reproducible utilization-based overload score from normalized Jira estimates and authoritative capacity.

**Why this task is needed:** It creates the smallest useful business result without introducing LLM behavior or persistence.

**Dependencies:** Task 2.1.

**Files or directories:**

- Create: `domain/workforce_risk/models.py`
- Create: `domain/workforce_risk/scoring/common.py`
- Create: `domain/workforce_risk/scoring/overload.py`
- Create: `domain/workforce_risk/scoring/config.py`
- Create: `config/scoring/v1.yaml`
- Create: `domain/workforce_risk/tests/test_overload.py`
- Create: `tests/fixtures/scenarios/{balanced_team,overloaded_employee}.json`

**Tests to write first:**

- Utilization formula, cap, `0–100` clamp, risk boundaries 29/30/54/55/74/75, missing capacity, missing estimates, stale evidence, model version, repeated-input equality, and evidence references.

**Detailed implementation steps:**

- [ ] Define `EmployeeOverloadInput`, `FactorContribution`, `RiskResult`, `RiskLevel`, and `ConfidenceLevel`.
- [ ] Validate configured weights total `1.0 ± 1e-9` and factor directions are explicit.
- [ ] Implement all employee-overload factors and confidence coverage from the spec, beginning with utilization and adding the remaining configured factors in the same task.
- [ ] Return `insufficient-data` without a numeric claim when mandatory evidence is absent.
- [ ] Preserve scoring version and timestamp in every result.

**Commands to run:**

```bash
uv run pytest domain/workforce_risk/tests/test_overload.py -q
uv run python -m workforce_risk.scoring.config --validate config/scoring/v1.yaml
```

**Expected output or observable result:** Balanced and overloaded fixtures return their exact expected score/level/confidence and repeat identically.

**Validation gate:** Domain reviewer can trace the score to factor values, weights, thresholds, and evidence IDs.

**Commit checkpoint:** `feat: add deterministic overload scoring`

## Task 2.3: Expose overload scoring through the Workforce Risk MCP

**Classification:** MVP

**Objective:** Provide typed MCP tools for overload scoring without exposing domain internals.

**Why this task is needed:** The Agent API must consume deterministic business truth through the approved custom MCP boundary.

**Dependencies:** Task 2.2.

**Files or directories:**

- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/server.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/tools/score_overload.py`
- Create: `services/workforce-risk-mcp/tests/test_score_overload_tool.py`
- Create: `tests/contract/test_workforce_mcp_transport.py`

**Tests to write first:**

- Valid tool call, schema mismatch, environment mismatch, duplicate correlation ID, malformed input, insufficient data, timeout, and service restart during real Streamable HTTP interaction.

**Detailed implementation steps:**

- [ ] Implement `score_employee_overload` returning the stable MCP envelope.
- [ ] Validate request and response schemas at the server boundary.
- [ ] Add request deadline, correlation logging, environment guard, and safe typed errors.
- [ ] Run the service as a separate process in contract tests.

**Commands to run:**

```bash
uv run pytest services/workforce-risk-mcp/tests/test_score_overload_tool.py -q
uv run pytest tests/contract/test_workforce_mcp_transport.py -q
```

**Expected output or observable result:** A real MCP client receives the same score as direct domain execution; invalid messages fail explicitly.

**Validation gate:** Real MCP transport is required; in-process mocks alone do not pass.

**Commit checkpoint:** `feat: expose overload scoring through workforce MCP`

## Task 2.4: Add the first Agent API risk endpoint

**Classification:** MVP

**Objective:** Compose Jira MCP read and Workforce Risk MCP scoring behind one read-only HTTP endpoint.

**Why this task is needed:** It completes the backend portion of the first vertical slice.

**Dependencies:** Tasks 2.1–2.3.

**Files or directories:**

- Create: `services/agent-api/src/agent_api/main.py`
- Create: `services/agent-api/src/agent_api/routes/risks.py`
- Create: `services/agent-api/src/agent_api/dependencies.py`
- Create: `services/agent-api/src/agent_api/errors.py`
- Create: `services/agent-api/tests/test_risk_endpoint.py`
- Create: `tests/integration/test_agent_workforce_mcp_streamable_http.py`
- Create: `tests/integration/processes.py`

**Tests to write first:**

- `GET /api/v1/employees/{employee_id}/overload-risk` success, Jira timeout degraded response, malformed MCP response, insufficient data, forbidden project, correlation propagation, and no mutation tool availability.
- A mandatory test that starts Agent API and Workforce Risk MCP as separate
  operating-system processes, calls the Agent API over HTTP, observes its
  Workforce Risk MCP call over Streamable HTTP. Direct handler calls and
  mocked MCP clients do not satisfy this test.
- Assert the external Agent API HTTP status, deterministic numeric score, risk
  level, confidence, factor contributions, evidence references, scoring-model
  version, end-to-end correlation propagation, typed response schema, and
  captured proof that the MCP exchange used real Streamable HTTP transport.

**Detailed implementation steps:**

- [ ] Implement the endpoint using only typed clients.
- [ ] Return score, level, confidence, factors, evidence references, scoring version, and timestamp.
- [ ] Apply safe error codes and `X-Correlation-ID`.
- [ ] Permit a clearly marked unpersisted degraded read only when deterministic confidence rules allow it.
- [ ] Do not add LangGraph or Bedrock to this endpoint.
- [ ] Build a process harness that allocates separate ports, waits for both
  readiness endpoints, captures sanitized logs, and always terminates both
  processes.
- [ ] Verify transport negotiation, typed schemas, HTTP status, environment,
  correlation propagation, risk level, confidence, factor contributions,
  evidence references, scoring version, and equality with the expected
  deterministic overload score.
- [ ] Capture process IDs, independently bound ports, and sanitized client/server
  transport logs as proof that no direct handler or mocked MCP client satisfied
  the test.

**Commands to run:**

```bash
uv run pytest services/agent-api/tests/test_risk_endpoint.py -q
uv run pytest tests/integration/test_agent_workforce_mcp_streamable_http.py -q
uv run uvicorn agent_api.main:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/health/live
```

**Expected output or observable result:** The endpoint returns a typed deterministic overload result and correlation ID from live local MCP services.

**Validation gate:** No response field is LLM-generated and no write tool is
reachable. Every listed assertion passes through separate-process Streamable
HTTP, and the retained transport evidence proves an in-process handler call or
mocked MCP client did not satisfy the gate.

**Commit checkpoint:** `feat: expose read-only overload risk API`

## Task 2.5: Add the basic FastAPI-served overload result view

**Classification:** MVP

**Objective:** Display the first vertical slice with score, level, confidence, factors, and freshness.

**Why this task is needed:** It produces working manager-visible behavior early and validates API/UI contracts.

**Dependencies:** Task 2.4.

**Files or directories:**

- Create: `services/agent-api/src/agent_api/web/templates/chat.html`
- Create: `services/agent-api/src/agent_api/web/static/chat.js`
- Create: `services/agent-api/src/agent_api/web/static/styles.css`
- Create: `services/agent-api/src/agent_api/routes/ui.py`
- Create: `services/agent-api/tests/ui/test_overload_view.py`

**Tests to write first:**

- Render low/high/insufficient-data states, evidence timestamp, scoring version, factor table, stale warning, API error correlation ID, keyboard navigation, and non-color-only risk labels.

**Detailed implementation steps:**

- [ ] Mount the static directory and render the single manager page from FastAPI.
- [ ] Implement a small JavaScript API client against the stable response schema.
- [ ] Implement one employee selector backed by configured synthetic data.
- [ ] Render deterministic values without recomputation.
- [ ] Add accessible loading, degraded, stale, and error states.

**Commands to run:**

```bash
uv run pytest services/agent-api/tests/ui/test_overload_view.py -q
uv run uvicorn agent_api.main:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/
```

**Expected output or observable result:** A browser shows the selected employee’s traceable overload result from the full Jira→MCP→score→API flow.

**Validation gate:** Phase 2 demo passes using real local MCP transports and no Bedrock.

**Commit checkpoint:** `feat: display employee overload risk`

---

# Phase 3 — Persistence, profiles, and complete deterministic risk

## Task 3.1: Add PostgreSQL persistence and migrations

**Classification:** MVP

**Objective:** Establish transactional PostgreSQL storage for profiles, scoring versions, snapshots, risks, proposals, decisions, alerts, reports, scans, outbox, and audit.

**Why this task is needed:** Durable state is mandatory before proposals, approvals, alerts, or external writes.

**Dependencies:** Phase 2.

**Files or directories:**

- Create: `packages/persistence/src/workforce_persistence/{database,models,repositories}.py`
- Create: `packages/persistence/alembic.ini`
- Create: `packages/persistence/migrations/`
- Create: `packages/persistence/tests/test_schema.py`
- Create: `tests/integration/test_postgres_transactions.py`
- Create: `compose.yaml`

**Tests to write first:**

- Migration up from empty database, idempotent startup, constraints, append-only
  audit API, immutable scoring activation, proposal uniqueness, outbox
  retention, optimistic versions, API-key actor/digest/role/environment/project
  scope/expiry/revocation fields with no raw-key column, and rollback on failed
  approval transaction.

**Detailed implementation steps:**

- [ ] Model every principal record in Section 14 with UUID identifiers and environment columns.
- [ ] Add unique idempotency constraints and legal-state check constraints.
- [ ] Add audit sequence/hash columns and prohibit normal update/delete repository methods.
- [ ] Configure bounded async pools, statement timeouts, readiness checks, and graceful close.
- [ ] Run migrations as a separate command suitable for a Kubernetes Job.

**Commands to run:**

```bash
docker compose up -d postgres
uv run alembic -c packages/persistence/alembic.ini upgrade head
uv run pytest packages/persistence/tests tests/integration/test_postgres_transactions.py -q
```

**Expected output or observable result:** Fresh PostgreSQL reaches head revision and transaction tests pass.

**Validation gate:** No proposal/approval operation can succeed without a committed audit-capable transaction.

**Commit checkpoint:** `feat: add transactional workforce persistence`

## Task 3.2: Implement workforce profile administration

**Classification:** MVP

**Objective:** Store authoritative role, seniority, skills, capacity,
allocations, mentoring availability, temporary overrides, and optional Jira
account mappings for seven synthetic employees.

**Why this task is needed:** Task-fit and workload analysis cannot rely on Jira for workforce-profile fields.

**Dependencies:** Task 3.1.

**Files or directories:**

- Create: `domain/workforce_risk/profiles.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/tools/profiles.py`
- Create: `services/agent-api/src/agent_api/routes/profiles.py`
- Create: `services/agent-api/src/agent_api/clients/workforce_mcp.py`
- Create: `services/agent-api/src/agent_api/auth/{api_keys,principal,roles,internal_context}.py`
- Create: `scripts/security/manage_api_keys.py`
- Create: `domain/workforce_risk/tests/test_profiles.py`
- Create: `services/agent-api/tests/test_profile_authorization.py`
- Create: `services/agent-api/tests/test_workforce_mcp_auth_transport.py`

**Tests to write first:**

- Valid proficiency/capacity, overlapping overrides, optimistic conflict,
  administrator-only mutation, viewer/manager denial, cross-environment access,
  audit event, request-body identity forgery, and missing/invalid authenticated
  Workforce Risk MCP transport context.
- Prove the Agent API validates the manager API key first, converts its verified identity/scope
  into a signed short-lived internal authorization context, never to MCP as a
  raw key, and excludes it from MCP arguments, logs, traces, graph state,
  prompts, handoffs, and memory.
- Reject missing, malformed, unknown, expired, revoked, wrong-role,
  cross-environment, and wrong-project API keys. Assert the complete raw key and
  HMAC digest are absent from graph state, MCP arguments, prompts, logs, traces,
  audit metadata, safe error responses, reports, and conversation memory.
- Require unique `EMP-001`–`EMP-007` profile identifiers, permit only the two
  approved write-demo profiles to carry Jira account mappings, and reject
  duplicate or cross-environment mappings.

**Detailed implementation steps:**

- [ ] Define profile and skill enums and effective-capacity calculation.
- [ ] Add administrator CRUD with ETags/version numbers.
- [ ] Validate authentication and primary authorization in the Agent API before
  invoking any protected MCP operation.
- [ ] Implement API-key generation, keyed HMAC digest storage, constant-time
  verification, expiry/revocation checks, and role/environment/project scope.
- [ ] Implement a noninteractive management command to create, list metadata,
  rotate, and revoke keys; show a new raw key exactly once and never print it in
  routine list/revoke output.
- [ ] Implement the Agent API Workforce MCP service client so it sends a signed,
  short-lived internal authorization context over authenticated transport and
  never forwards the manager API key.
- [ ] Independently enforce protected Workforce MCP authorization from the
  authenticated transport context; never trust identity or roles in plain tool
  input.
- [ ] Link profiles to safe Jira account references and prevent duplicates per environment.
- [ ] Keep Jira account mapping optional for general profiles and constrain the
  controlled mutation scenario to the two configured synthetic Jira accounts.
- [ ] Audit every create/update without storing raw keys or HMAC digests.

**Commands to run:**

```bash
uv run pytest domain/workforce_risk/tests/test_profiles.py services/agent-api/tests/test_profile_authorization.py services/agent-api/tests/test_workforce_mcp_auth_transport.py -q
uv run python scripts/security/manage_api_keys.py --help
```

**Expected output or observable result:** An administrator can create/update a synthetic profile; stale ETag and unauthorized roles fail.

**Validation gate:** Profile changes are transactional, audited,
environment-scoped, and never inferred from Jira text. Protected MCP calls
derive identity only from verified transport context, and raw-key exclusion
tests plus every missing/malformed/unknown/expired/revoked/role/environment/
project-scope case pass.

**Commit checkpoint:** `feat: add audited workforce profiles`

## Task 3.3: Implement versioned scoring configuration and all three scores

**Classification:** MVP

**Objective:** Complete employee-overload, task-fit, and project-delivery scoring exactly as specified.

**Why this task is needed:** Simulations, alerts, reports, and recommendations require all deterministic score types.

**Dependencies:** Tasks 3.1–3.2.

**Files or directories:**

- Create: `domain/workforce_risk/scoring/{task_fit,project_delivery,confidence}.py`
- Modify: `domain/workforce_risk/scoring/overload.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/tools/scoring.py`
- Create: `domain/workforce_risk/tests/test_{task_fit,project_delivery,confidence,scoring_versions}.py`
- Create: `tests/fixtures/scenarios/{weak_fit,paired_fit,insufficient_data}.json`

**Tests to write first:**

- All boundaries, weight-sum failure, protective factors, extreme utilization, missing mandatory data, stale evidence, same-version comparison, immutable historical versions, and all seeded expected outcomes.

**Detailed implementation steps:**

- [ ] Implement factor normalization and direction metadata.
- [ ] Calculate confidence from weighted evidence coverage and freshness.
- [ ] Persist immutable scoring versions and require explicit administrator activation.
- [ ] Expose typed MCP tools for all score types.
- [ ] Store complete contribution and evidence records with each snapshot.

**Commands to run:**

```bash
uv run pytest domain/workforce_risk/tests/test_task_fit.py domain/workforce_risk/tests/test_project_delivery.py domain/workforce_risk/tests/test_confidence.py domain/workforce_risk/tests/test_scoring_versions.py -q
```

**Expected output or observable result:** All deterministic scenarios match reviewed expected values; historical results retain version `v1`.

**Validation gate:** Domain/stakeholder review accepts initial hypotheses for dev use, not predictive production claims.

**Commit checkpoint:** `feat: complete deterministic workforce risk scoring`

## Task 3.4: Persist evidence snapshots and targeted refresh fingerprints

**Classification:** MVP

**Objective:** Create reproducible snapshots and material-change fingerprints for scans, investigation, simulation, and approval.

**Why this task is needed:** Stale proposals must fail before any mutation.

**Dependencies:** Task 3.3.

**Files or directories:**

- Create: `domain/workforce_risk/evidence/{snapshot,fingerprint,freshness}.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/tools/evidence.py`
- Create: `domain/workforce_risk/tests/test_fingerprint.py`
- Create: `tests/integration/test_snapshot_persistence.py`

**Tests to write first:**

- Stable canonical fingerprint, material task/assignee/workload/deadline/dependency changes, irrelevant metadata change, stale timestamp, targeted refresh, and environment mismatch.

**Detailed implementation steps:**

- [ ] Canonicalize only approved structured evidence fields.
- [ ] Hash canonical evidence with schema and scoring versions.
- [ ] Persist snapshot and risk results atomically.
- [ ] Implement targeted refresh for task, current/proposed users, workloads, dependencies, due date, and status.
- [ ] Expose visible evidence timestamps and stale warnings.

**Commands to run:**

```bash
uv run pytest domain/workforce_risk/tests/test_fingerprint.py tests/integration/test_snapshot_persistence.py -q
```

**Expected output or observable result:** Identical evidence produces one fingerprint; each material change invalidates it.

**Validation gate:** Freshness behavior matches Section 10 and never treats missing evidence as zero risk.

**Commit checkpoint:** `feat: add versioned evidence snapshots`

## Task 3.5: Normalize attributable Jira comment evidence conservatively

**Classification:** Security/Hardening

**Objective:** Convert eligible Jira comment observations into
author-independent, deterministic report-only metadata without treating
free-text statements as verified facts or persisting raw comment bodies.

**Why this task is needed:** The approved design permits narrowly scoped comment
signals while requiring prompt-injection resistance, valid attribution,
immutable lifecycle history, privacy minimization, and no scoring effect from
ambiguous language.

**Dependencies:** Tasks 2.1, 3.1, 3.2, and 3.4.

**Files or directories:**

- Create: `domain/workforce_risk/comments/models.py`
- Create: `domain/workforce_risk/comments/classifier.py`
- Create: `domain/workforce_risk/comments/lifecycle.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/tools/comment_evidence.py`
- Create: `domain/workforce_risk/tests/test_comment_classifier.py`
- Create: `tests/integration/test_comment_evidence_lifecycle.py`
- Create: `tests/fixtures/comments/source_situations.json`
- Create: `tests/fixtures/comments/ambiguous_cases.json`

**Tests to write first:**

- Map the twelve approved source situations onto exactly these ten normalized
  categories: `temporary_unavailability_report`, `clarification_request`,
  `technical_help_request`, `blocker_report`, `review_waiting_report`,
  `workload_concern`, `deadline_concern`, `missing_access_report`,
  `task_frustration_report`, and `collaboration_concern`.
- Prove category is independent of author type; validate Jira account IDs before
  assigning `employee`, and preserve `manager`, `reviewer`, `automation`, or
  `unmapped` attribution.
- Accept only configured explicit category phrases. Require an explicit time
  window only when calculating temporary-unavailability impact; clarification,
  help, blocker, review, workload, deadline, missing-access, frustration, and
  collaboration reports may normalize without a time window.
- Prove all normalized comment signals remain report-only: they never change
  risk score, confidence, candidate eligibility/ranking, or proposal evidence.
  They may trigger only a structured refresh or conditional work-impact
  analysis, whose result can affect scoring only when corroborated by structured
  Jira fields or authoritative workforce data.
- Prove ambiguous, sarcastic, indirect, conflicting, or uncertain-author
  examples produce no structured signal.
- Record comment ID, issue reference, author reference/type, created time,
  updated time, retrieval time, freshness, attribution state, and optional
  explicit availability window; edits create new immutable observations.
- Mark deleted, inaccessible, or no-longer-returned comments unavailable without
  rewriting historical snapshots.
- Prove raw comment bodies never enter profiles, scores, reports, Bedrock input,
  or general audit metadata.
- Prove health reasons never affect scoring or candidate selection; default
  summaries show temporary unavailability, while an authorized manager may see
  only the necessary employee-reported/unverified sickness label.

**Detailed implementation steps:**

- [ ] Define immutable observation, author-type, attribution-status,
  availability-status, freshness, and extraction-result schemas.
- [ ] Define the ten author-independent category codes and a reviewed mapping
  from the twelve source situations.
- [ ] Implement a versioned, configuration-driven deterministic phrase matcher;
  do not call Bedrock or perform general semantic interpretation.
- [ ] Require an explicit configured category phrase before returning
  `CommentEvidenceSignal`; require an explicit availability window only for
  temporary-unavailability impact calculations.
- [ ] Allow the other nine categories to normalize without a time window while
  preserving their report-only status.
- [ ] Resolve and validate the Jira author account against configured workforce
  mappings while preserving non-employee and unmapped author types.
- [ ] Append lifecycle observations keyed by comment ID and retrieval time;
  retain immutable prior versions and represent deletion/inaccessibility as
  availability metadata.
- [ ] Persist only normalized metadata and Jira references through the Workforce
  Risk MCP tool; discard raw bodies after bounded in-memory classification.
- [ ] Expose sickness detail only through an authorized, necessary manager view;
  use temporary-unavailability wording elsewhere.
- [ ] Permit a normalized signal only to appear in reports or trigger a
  structured refresh/conditional work-impact analysis.
- [ ] Prevent comment signals from entering scoring, confidence, candidate
  eligibility/ranking, proposal fingerprints, or proposal evidence. Only
  corroborated structured Jira fields or authoritative workforce data returned
  by the triggered refresh may become deterministic score inputs.

**Commands to run:**

```bash
uv run pytest domain/workforce_risk/tests/test_comment_classifier.py -q
uv run pytest tests/integration/test_comment_evidence_lifecycle.py -q
```

**Expected output or observable result:** Explicit synthetic Jira statements
produce attributable report-only metadata, non-availability categories can
normalize without a time window, and temporary-unavailability impact requires
one. Unsafe or ambiguous statements produce no signal, and immutable lifecycle
records contain no raw comment body.

**Validation gate:** Privacy, attribution, lifecycle, prompt-injection, and
strict report-only isolation tests pass for all three scores, confidence,
candidate selection/ranking, proposal evidence/fingerprints, all ambiguous
fixtures, and all twelve approved source situations.

**Commit checkpoint:** `feat: normalize safe jira comment evidence`

## Task 3.6: Automate the seven-person synthetic development dataset

**Classification:** MVP

**Objective:** Create a deterministic, idempotent, resettable dataset containing
seven workforce profiles and complete Jira task evidence without requiring
seven Atlassian accounts or manual task entry.

**Why this task is needed:** Every later scan, investigation, simulation, alert,
report, dev smoke test, and demonstration needs the same known business
scenarios before agent behavior is added.

**Dependencies:** Tasks 0.2 and 3.1–3.5.

**Files or directories:**

- Create: `scripts/jira/{seed_dev,advance_scenario,reset_dev,cleanup_dev,verify_seed}.py`
- Create: `scripts/scenario/evaluate_results.py`
- Create: `.github/workflows/run-scenario.yml`
- Create: `tests/fixtures/scenarios/seven_employee_team.json`
- Create: `tests/integration/test_synthetic_seed.py`
- Create: `tests/security/test_seed_cleanup_guards.py`

**Tests to write first:**

- Exactly seven profiles named `EMP-001`–`EMP-007`, unique workforce IDs,
  documented work-only profile fields, and exactly two approved profiles mapped
  to real synthetic Jira account IDs.
- Deterministic Jira issue counts and values for estimates, remaining estimates,
  deadlines, priorities, difficulty, required skills, dependencies, blockers,
  structured custom fields, activity fixtures, and safe comment scenarios.
- Balanced, overload, weak-fit, paired-fit, overloaded-candidate,
  insufficient-data, stale-proposal, primary-demo, and backup-demo fixtures.
- Idempotent re-seed/reset, scenario/version ownership tags, cleanup of only
  owned records, exact configured-dev allowlist, and unconditional production
  refusal.
- Prove general tasks use `Workforce Employee ID` rather than real Jira
  accounts; only the controlled write fixture uses current/target `accountId`.
- Prove runtime code does not call Jira REST. If MCP is insufficient or
  inefficient for bulk preparation, official REST is reachable only from these
  dev-administration scripts and inherits project/prod guards.
- Prove the scenario workflow runs outside Kubernetes, has no Kubernetes/AWS
  production credentials, creates no simulator manifest/namespace/workload,
  cannot be invoked by LangGraph, and can target only `WORKFORCE-SIM`.
- Advance every versioned scenario step idempotently, trigger an authenticated
  dev Agent scan, and compare observed deterministic results with the fixture's
  expected findings/scores without directly sending expectations to the agent.

**Detailed implementation steps:**

- [ ] Define the versioned seven-person scenario fixture with known expected
  deterministic scoring outcomes.
- [ ] Seed authoritative PostgreSQL profiles, skills, capacities, allocations,
  mentoring availability, and optional Jira mappings transactionally.
- [ ] Discover Jira create metadata and verify `Blocker Category` and
  `Workforce Employee ID` before writing fixtures.
- [ ] Create/update scenario-owned Jira issues, estimates, deadlines,
  priorities, dependencies, blockers, and structured evidence idempotently.
- [ ] Implement `advance_scenario.py` as an explicit deterministic state
  transition over Jira evidence with logical timestamps and a stored step ID.
- [ ] Prefer Rovo MCP for supported setup calls; isolate any necessary official
  REST bulk call inside the guarded script client, never the runtime adapter.
- [ ] Verify every expected profile, issue, custom field, relationship, and
  controlled current/target assignee mapping after seeding.
- [ ] Implement `evaluate_results.py` to call the dev Agent API after its real
  Rovo MCP scan and compare returned findings, score ranges, confidence,
  evidence references, and alerts with expected fixture outcomes.
- [ ] Add `run-scenario.yml` with manual dispatch and optional bounded schedule,
  protected simulation secrets, scenario/step inputs, concurrency control,
  retained results, and no AWS/Kubernetes deployment permissions.
- [ ] Implement reset and cleanup from scenario ownership tags and refuse when
  site, project, environment, or production guard does not match exactly.

**Commands to run:**

```bash
uv run pytest tests/integration/test_synthetic_seed.py tests/security/test_seed_cleanup_guards.py -q
uv run python scripts/jira/seed_dev.py --scenario tests/fixtures/scenarios/seven_employee_team.json
uv run python scripts/jira/verify_seed.py --scenario tests/fixtures/scenarios/seven_employee_team.json
uv run python scripts/jira/advance_scenario.py --scenario tests/fixtures/scenarios/seven_employee_team.json --step overload_and_blocker
uv run python scripts/scenario/evaluate_results.py --scenario tests/fixtures/scenarios/seven_employee_team.json --step overload_and_blocker
uv run python scripts/jira/reset_dev.py --scenario tests/fixtures/scenarios/seven_employee_team.json
actionlint .github/workflows/run-scenario.yml
```

**Expected output or observable result:** One command prepares the complete
seven-person synthetic workspace with known risk outcomes; external progression
changes real Jira state, the dev agent independently observes it through MCP,
repeated steps are unchanged, and no more than two profiles require Jira
accounts.

**Validation gate:** Dataset completeness, expected-result, idempotency,
ownership, two-account, runtime-MCP observation, expected-result evaluation,
external-runner/Kubernetes-absence, guarded-dev-REST, and production-refusal
tests pass before Phase 4 begins.

**Commit checkpoint:** `testdata: automate seven-person jira workforce scenario`

---

# Phase 4 — Agent explanations and interactive investigation

## Task 4.1: Add the provider-neutral Bedrock explanation adapter

**Classification:** MVP

**Objective:** Convert deterministic results into validated explanations with a deterministic fallback.

**Why this task is needed:** Managers need understandable causes and recommendations without giving the LLM control over scores or actions.

**Dependencies:** Task 3.3; Phase 0 Bedrock validation.

**Files or directories:**

- Create: `services/agent-api/src/agent_api/llm/{protocol,bedrock,fallback,schemas}.py`
- Create: `services/agent-api/src/agent_api/prompts/system.txt`
- Create: `services/agent-api/tests/test_explanations.py`
- Create: `tests/security/test_prompt_injection.py`

**Tests to write first:**

- Valid schema, unknown citation, changed score, invented candidate, prohibited
  fields, malicious Jira description/comment, timeout, circuit open, IAM denial,
  fallback, and a guard proving Bedrock is never used for MVP comment-signal
  classification.

**Detailed implementation steps:**

- [ ] Define provider-neutral `ExplanationProvider`.
- [ ] Minimize evidence through an allowlist before model invocation.
- [ ] Separate system instructions and quoted untrusted evidence.
- [ ] Validate citations and compare returned numeric values to immutable inputs.
- [ ] Add bounded time/token budgets, retries, and dependency-specific circuit breaker.
- [ ] Limit Bedrock to explanations, root-cause summaries, recommendations, and
  follow-up answers; keep comment normalization in the deterministic classifier
  from Task 3.5.

**Commands to run:**

```bash
uv run pytest services/agent-api/tests/test_explanations.py tests/security/test_prompt_injection.py -q
```

**Expected output or observable result:** Mocked Bedrock produces valid explanations; every invalid output falls back without changing scores.

**Validation gate:** No secrets, protected data, hidden prompts, or invented candidates reach responses.

**Commit checkpoint:** `feat: add guarded Bedrock explanations`

## Task 4.2: Implement the mandatory constrained Supervisor workflow

**Classification:** MVP

**Objective:** Implement the custom-coded LangGraph Supervisor workflow that
supports the approved finite investigation intents with typed evidence and no
conversational write path.

**Why this task is needed:** LangGraph orchestration, authenticated context,
tool boundaries, and manager follow-up are mandatory MVP behavior independent
of the selected extra-credit specialist topology.

**Dependencies:** Tasks 3.6 and 4.1.

**Files or directories:**

- Create: `services/agent-api/src/agent_api/graph/{state,intents,supervisor,workflow}.py`
- Create: `services/agent-api/src/agent_api/prompts/supervisor.txt`
- Create: `services/agent-api/src/agent_api/routes/investigations.py`
- Create: `services/agent-api/tests/test_graph_workflows.py`
- Create: `services/agent-api/tests/test_agent_tool_boundaries.py`
- Create: `services/agent-api/tests/test_graph_auth_context.py`

**Tests to write first:**

- Every supported intent, unsupported intent, malformed MCP output,
  context-reference bounds, tool/step limit, timeout, deterministic partial
  result rules, and chat approval attempt.
- Prove Agent API authentication and primary authorization happen before graph
  entry; the initial graph state is `Receive verified context`, agents never
  receive API keys, and raw keys never appear in state, prompts, tool
  arguments, checkpoints, logs, handoffs, or memory.
- Prove the Supervisor cannot score, construct candidates/proposals, approve,
  execute, or invoke Jira mutation, and that untrusted Jira free text cannot
  alter instructions or select tools.

**Detailed implementation steps:**

- [ ] Authenticate and apply primary route/project authorization in FastAPI
  dependencies before constructing graph input.
- [ ] Define `VerifiedAgentContext` with subject reference, roles, environment,
  authorized Jira site/project scopes, bounded entity references, and
  correlation ID, but no raw API key.
- [ ] Define the finite `Intent` enum and per-intent read-only tool allowlists.
- [ ] Start the LangGraph workflow with a `Receive verified context` node and
  reject missing or inconsistent verified context.
- [ ] Implement Supervisor routing, evidence gathering, combination, global
  deadline, and total tool/step budgets without domain scoring.
- [ ] Store only selected entity references in conversation state.
- [ ] Add graph deadlines, maximum steps, maximum tool calls, and graceful termination.
- [ ] Return facts, evidence-based contributors, unknowns, recommendations, and cited evidence separately.
- [ ] Treat structured Jira fields as facts and descriptions/comments as quoted,
  attributable, unverified, prompt-injection-capable input.
- [ ] Exclude approval and execution nodes from conversational graphs.

**Commands to run:**

```bash
uv run pytest services/agent-api/tests/test_graph_workflows.py services/agent-api/tests/test_agent_tool_boundaries.py services/agent-api/tests/test_graph_auth_context.py -q
```

**Expected output or observable result:** An authenticated manager receives a
typed, cited investigation response through custom-coded LangGraph;
unsupported/action requests return capability guidance.

**Validation gate:** Pre-graph authentication, raw-key exclusion, tool-boundary,
prompt-injection, and chat-approval tests pass. MCP servers are invoked only as
tools, and the workflow cannot create approval state or invoke Jira mutation.

**Commit checkpoint:** `feat: add constrained supervisor workflow`

## Task 4.3: Build the lightweight contextual chat UI

**Classification:** MVP

**Objective:** Add project/employee/task risk details and contextual chat while preserving visible deterministic evidence.

**Why this task is needed:** Managers need structured evidence beside explanations, not a chat-only experience.

**Dependencies:** Task 4.2.

**Files or directories:**

- Modify: `services/agent-api/src/agent_api/web/templates/chat.html`
- Modify: `services/agent-api/src/agent_api/web/static/chat.js`
- Modify: `services/agent-api/src/agent_api/web/static/styles.css`
- Create: `services/agent-api/tests/ui/test_contextual_chat.py`
- Create: `services/agent-api/tests/ui/test_api_key_storage.py`

**Tests to write first:**

- Bounded context IDs, citation links, facts/contributors/unknown labels, stale
  warning, fallback explanation, unsupported request, keyboard/screen-reader
  behavior, tab-scoped key clearing, no key in DOM/URL/diagnostics, output
  escaping, and Content Security Policy.

**Detailed implementation steps:**

- [ ] Add routes for selected employee, project, risk result, alert, and proposal references.
- [ ] Add a one-time-per-tab API-key entry, retain it only in
  `sessionStorage`, attach it explicitly as `Authorization: Bearer`, and clear
  it on logout/tab close without using cookies or `localStorage`.
- [ ] Keep score cards and evidence visible while chat updates.
- [ ] Never send full evidence bundles from the browser.
- [ ] Render all agent/Jira text through safe text nodes, prohibit dynamic HTML
  injection, and set a restrictive Content Security Policy for the embedded UI.
- [ ] Render correlation IDs for safe error support.

**Commands to run:**

```bash
uv run pytest services/agent-api/tests/ui/test_contextual_chat.py services/agent-api/tests/ui/test_api_key_storage.py -q
uv run uvicorn agent_api.main:app --host 127.0.0.1 --port 8000
```

**Expected output or observable result:** A manager can ask why a selected risk exists and see citations without losing deterministic context.

**Validation gate:** Accessibility checks pass and no approval control exists in chat.

**Commit checkpoint:** `feat: add contextual risk investigation UI`

## Task 4.4: Add the selected specialist multi-agent topology

**Classification:** Stretch

**Objective:** Add the selected extra-credit Workforce Analysis, Project
Delivery, Reassignment Planning, and Operations Diagnostic agents as bounded
LangGraph subgraphs coordinated by the Supervisor.

**Why this task is needed:** Specialist collaboration demonstrates genuine
multi-agent decomposition while preserving a usable deterministic MVP when a
specialist is unavailable.

**Dependencies:** Tasks 4.2 and 4.3.

**Files or directories:**

- Create: `services/agent-api/src/agent_api/graph/handoffs.py`
- Create: `services/agent-api/src/agent_api/graph/agents/workforce_analysis.py`
- Create: `services/agent-api/src/agent_api/graph/agents/project_delivery.py`
- Create: `services/agent-api/src/agent_api/graph/agents/reassignment_planning.py`
- Create: `services/agent-api/src/agent_api/graph/agents/operations_diagnostic.py`
- Create: `services/agent-api/src/agent_api/prompts/workforce_analysis.txt`
- Create: `services/agent-api/src/agent_api/prompts/project_delivery.txt`
- Create: `services/agent-api/src/agent_api/prompts/reassignment_planning.txt`
- Create: `services/agent-api/src/agent_api/prompts/operations_diagnostic.txt`
- Create: `services/agent-api/tests/test_agent_handoffs.py`
- Create: `services/agent-api/tests/test_specialist_fallback.py`

**Tests to write first:**

- Route each supported specialist and multi-specialist request through typed
  handoffs with environment, authorization context, bounded entity references,
  evidence freshness/references, and correlation ID.
- Prove Workforce Analysis cannot use DevOps tools, Project Delivery cannot
  mutate, Reassignment Planning cannot invent candidates or construct proposal
  state, and Operations Diagnostic can use only read-only DevOps MCP tools.
- Make each specialist unavailable in turn and prove deterministic read
  workflows remain usable with clearly identified missing sources whenever
  confidence rules permit; write-oriented preparation remains closed.
- Prove handoffs and specialist checkpoints contain no raw API key or raw comment
  body.

**Detailed implementation steps:**

- [ ] Define versioned `AgentHandoff` and specialist result schemas over
  `VerifiedAgentContext`.
- [ ] Implement Supervisor routing and combination for single- and
  multi-specialist requests within the existing global budgets.
- [ ] Implement Workforce Analysis for workload, capacity, skills, task fit, and
  employee-risk explanation through approved MCP tools.
- [ ] Implement Project Delivery for progress, deadlines, blockers,
  dependencies, workload concentration, and project-risk explanation.
- [ ] Implement Reassignment Planning to explain only MCP-selected candidates
  and deterministic simulations, with no proposal/approval/execution tools.
- [ ] Implement Operations Diagnostic with read-only DevOps MCP tools and no
  Kubernetes mutation capability.
- [ ] Add deterministic specialist-unavailable fallback that labels omissions
  and follows `read degraded; write closed`.
- [ ] Retain the core Supervisor route as the mandatory fallback so specialist
  failure cannot remove deterministic investigation capability.

**Commands to run:**

```bash
uv run pytest services/agent-api/tests/test_agent_handoffs.py services/agent-api/tests/test_specialist_fallback.py services/agent-api/tests/test_agent_tool_boundaries.py -q
```

**Expected output or observable result:** Runtime traces show genuine bounded
handoffs among the five named agents; supported read workflows degrade
deterministically if one specialist is unavailable.

**Validation gate:** Reviewers confirm the topology is an extra-credit
extension, MCP servers remain tools, domain decisions remain in Workforce Risk
MCP, and the mandatory MVP remains usable without specialist availability.

**Commit checkpoint:** `feat: add specialist workforce agents`

---

# Phase 5 — Alerts, reports, and scan orchestration

## Task 5.1: Implement alert rules, recurrence, and transactional outbox

**Classification:** MVP

**Objective:** Persist authoritative alerts with noise control and atomic notification events.

**Why this task is needed:** Managers should receive meaningful risks without losing events or creating daily duplicates.

**Dependencies:** Phase 3.

**Files or directories:**

- Create: `domain/workforce_risk/alerts/{rules,state}.py`
- Create: `packages/persistence/src/workforce_persistence/alert_repository.py`
- Create: `packages/persistence/src/workforce_persistence/outbox_repository.py`
- Create: `domain/workforce_risk/tests/test_alert_rules.py`
- Create: `tests/integration/test_alert_outbox_transaction.py`

**Tests to write first:**

- Low/medium/high/critical routing, dedup key, cooldown, escalation, recurrence, dismissal reason/identity, ETag conflict, atomic outbox, and duplicate event.

**Detailed implementation steps:**

- [ ] Implement alert and occurrence states from the spec.
- [ ] Commit alert and outbox event in one transaction.
- [ ] Retain published outbox history and delivery attempts.
- [ ] Audit every manager state change.
- [ ] Keep business alerts separate from Alertmanager.

**Commands to run:**

```bash
uv run pytest domain/workforce_risk/tests/test_alert_rules.py tests/integration/test_alert_outbox_transaction.py -q
```

**Expected output or observable result:** Repeated unchanged risk creates no duplicate alert/email event; material recurrence remains auditable.

**Validation gate:** Database failure cannot produce a claimed alert or orphan notification.

**Commit checkpoint:** `feat: add deduplicated risk alerts and outbox`

## Task 5.2: Implement SQS notification delivery and SES adapter

**Classification:** MVP

**Objective:** Publish outbox events to SQS and deliver best-effort concise email idempotently.

**Why this task is needed:** Email must not block scans or become the authoritative alert channel.

**Dependencies:** Task 5.1.

**Files or directories:**

- Create: `services/notification-worker/src/notification_worker/{main,outbox,sqs,email}.py`
- Create: `services/notification-worker/tests/test_worker.py`
- Create: `tests/integration/test_notification_pipeline.py`

**Tests to write first:**

- Publish retry, duplicate SQS message, SES failure/backoff, DLQ, delivery states, secret redaction, and graceful shutdown.

**Detailed implementation steps:**

- [ ] Publish committed outbox events using their idempotent consumer key.
- [ ] Consume SQS with bounded visibility/attempts and environment checks.
- [ ] Send concise email with application link and minimal workforce data.
- [ ] Record sent/retrying/failed independently from alert state.
- [ ] Support SMTP only if Task 0.1 approved it for dev.

**Commands to run:**

```bash
docker compose up -d localstack postgres
uv run pytest services/notification-worker/tests tests/integration/test_notification_pipeline.py -q
```

**Expected output or observable result:** Duplicate queue deliveries send at most one logical notification; DLQ failure remains visible.

**Validation gate:** Alert remains available when SQS/SES is unavailable.

**Commit checkpoint:** `feat: add asynchronous alert email delivery`

## Task 5.3: Generate immutable daily JSON reports

**Classification:** MVP

**Objective:** Create idempotent JSON risk reports and store verified artifacts in S3.

**Why this task is needed:** Daily reporting is required and must remain durable independently from email.

**Dependencies:** Tasks 3.4 and 5.1.

**Files or directories:**

- Create: `domain/workforce_risk/reports/generator.py`
- Create: `packages/persistence/src/workforce_persistence/report_repository.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/tools/reports.py`
- Create: `domain/workforce_risk/tests/test_report_generator.py`
- Create: `tests/integration/test_s3_reports.py`

**Tests to write first:**

- Required content, safe Jira references, secret exclusion, exact S3 key, checksum, version ID, idempotency, upload failure/pending state, retry, and authorized exact-version download.

**Detailed implementation steps:**

- [ ] Generate JSON from persisted deterministic results and validated explanations.
- [ ] Compute checksum before upload.
- [ ] Upload to `reports/{environment}/{yyyy}/{mm}/{dd}/{report_id}.json`.
- [ ] Persist status only after S3 confirms write/version.
- [ ] Generate short-lived exact-version presigned URLs after authorization.

**Commands to run:**

```bash
uv run pytest domain/workforce_risk/tests/test_report_generator.py tests/integration/test_s3_reports.py -q
```

**Expected output or observable result:** One scan window produces one immutable object and matching PostgreSQL metadata.

**Validation gate:** No report contains token, credential, prohibited personal data, or unrestricted comment content.

**Commit checkpoint:** `feat: generate immutable daily risk reports`

## Task 5.4: Implement asynchronous manual and scheduled scan workflows

**Classification:** MVP

**Objective:** Run the same evidence/scoring/alert/report pipeline from authenticated manual requests and Kubernetes CronJobs.

**Why this task is needed:** Scheduled monitoring is the primary workflow; failures must not block interactive analysis.

**Dependencies:** Tasks 5.1–5.3.

**Files or directories:**

- Create: `domain/workforce_risk/scans/service.py`
- Create: `services/agent-api/src/agent_api/routes/scans.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/tools/scans.py`
- Create: `domain/workforce_risk/tests/test_scan_service.py`
- Create: `tests/integration/test_scan_idempotency.py`

**Tests to write first:**

- State transitions, scan-window key, duplicate active scope, degraded completion, independent interactive request, failure reason, deadline, and manual role authorization.

**Detailed implementation steps:**

- [ ] Implement `queued/running/completed/completed_degraded/failed/skipped_duplicate`.
- [ ] Return `202` and `scan_run_id` for manual requests.
- [ ] Use one scan orchestration method for manual and CronJob callers.
- [ ] Persist timing, result, correlation, and failure reason.
- [ ] Propagate one correlation ID through snapshot, risk, alert, report, and outbox.

**Commands to run:**

```bash
uv run pytest domain/workforce_risk/tests/test_scan_service.py tests/integration/test_scan_idempotency.py -q
```

**Expected output or observable result:** Duplicate scan windows do not repeat processing; failed scheduled work leaves interactive endpoints usable.

**Validation gate:** End-to-end seeded scan creates persisted risk, alert, outbox, and report metadata.

**Commit checkpoint:** `feat: orchestrate idempotent risk scans`

---

# Phase 6 — Simulation and proposal safety

## Task 6.1: Implement deterministic candidate selection and what-if simulation

**Classification:** MVP

**Objective:** Compare eligible Jira-linked employees using current targeted evidence and identical scoring rules.

**Why this task is needed:** Managers must see predicted effects before creating any proposal.

**Dependencies:** Tasks 3.2–3.4.

**Files or directories:**

- Create: `domain/workforce_risk/simulation/{candidates,service}.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/tools/simulation.py`
- Create: `domain/workforce_risk/tests/test_simulation.py`
- Create: `tests/fixtures/scenarios/overloaded_candidate.json`

**Tests to write first:**

- Current/proposed same scoring version, minimum confidence, skill fit, workload impact, dependency impact, overloaded candidate rejection, missing evidence, and invented candidate prevention.

**Detailed implementation steps:**

- [ ] Refresh only task, current/proposed employees, workloads, dependencies, due date, and state.
- [ ] Filter candidates by Jira access, profile completeness, capacity, and required confidence.
- [ ] Score current and predicted states without persistence side effects.
- [ ] Return evidence fingerprint and candidate IDs to the Agent API.

**Commands to run:**

```bash
uv run pytest domain/workforce_risk/tests/test_simulation.py -q
```

**Expected output or observable result:** The seeded suitable candidate lowers reviewed risk while the overloaded candidate is excluded or ranked unsuitable.

**Validation gate:** LLM cannot add candidates and simulation performs no Jira write.

**Commit checkpoint:** `feat: add deterministic reassignment simulation`

## Task 6.2: Implement immutable proposals, authorization, freshness, and audit chaining

**Classification:** Security/Hardening

**Objective:** Create proposal and decision state safely, without implementing Jira mutation.

**Why this task is needed:** Every mutation prerequisite must be complete before a write tool is introduced.

**Dependencies:** Task 6.1; Tasks 3.1–3.4.

**Files or directories:**

- Create: `domain/workforce_risk/proposals/{models,state,service}.py`
- Create: `domain/workforce_risk/audit/{events,chain}.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/tools/proposals.py`
- Modify: `services/agent-api/src/agent_api/auth/{api_keys,principal,roles,internal_context}.py`
- Create: `services/agent-api/tests/test_proposal_endpoints.py`
- Create: `tests/integration/test_proposal_races.py`
- Create: `tests/security/test_audit_chain.py`

**Tests to write first:**

- Every legal/illegal transition, immutable fields/decisions, viewer denial,
  forged identity, low confidence, expired/stale proposal, duplicate approval,
  race, evidence change, idempotency key, audit sequence/hash, and tamper
  detection.
- Reject missing, malformed, unknown, expired, revoked, wrong-role,
  cross-environment, and wrong-project API keys.
- Prove raw keys and HMAC digests never appear in graph state, MCP arguments,
  prompts, logs, traces, audit metadata, reports, error responses, browser
  diagnostics, or conversation memory throughout
  proposal creation, approval, rejection, and duplicate/stale failure paths.

**Detailed implementation steps:**

- [ ] Define exact proposal terminal states and immutable simulation payload.
- [ ] Implement proposal creation only from a stored simulation result.
- [ ] Validate the API key and primary authorization in Agent API before
  LangGraph or proposal-domain invocation.
- [ ] Issue a signed short-lived internal authorization context through the
  existing Agent API service client; never forward the raw manager API key.
- [ ] Make protected Workforce MCP tools independently enforce proposal and
  approval rules from authenticated transport context; reject identity or role
  fields supplied as plain tool input and never expose the raw API key to the
  domain operation.
- [ ] Implement approve/reject endpoints that derive identity only from verified claims.
- [ ] Perform final targeted refresh and reject material changes.
- [ ] Persist `approved`/`executing` intent and audit in a short transaction, but do not call Jira yet.

**Commands to run:**

```bash
uv run pytest services/agent-api/tests/test_proposal_endpoints.py tests/integration/test_proposal_races.py tests/security/test_audit_chain.py -q
```

**Expected output or observable result:** Safe proposals can enter `executing`; all unsafe attempts fail before any external call.

**Validation gate:** Security review confirms mutation prerequisites, audit
integrity, every explicit API-key rejection case, complete raw-key exclusion,
and `read degraded; write closed`.

**Commit checkpoint:** `feat: add safe reassignment proposal lifecycle`

## Task 6.3: Build proposal review and approval UI without execution

**Classification:** MVP

**Objective:** Let managers review exact proposal evidence and explicitly approve or reject it through dedicated controls.

**Why this task is needed:** The UI must prove chat cannot approve and must communicate staleness/confidence before mutation exists.

**Dependencies:** Task 6.2.

**Files or directories:**

- Modify: `services/agent-api/src/agent_api/web/templates/chat.html`
- Modify: `services/agent-api/src/agent_api/web/static/chat.js`
- Modify: `services/agent-api/src/agent_api/web/static/styles.css`
- Create: `services/agent-api/tests/ui/test_proposal_review.py`
- Create: `services/agent-api/tests/ui/test_approval_confirmation.py`
- Create: `services/agent-api/tests/ui/test_operation_status.py`

**Tests to write first:**

- Exact proposal ID, expected/proposed assignee, score comparison, expiry, fingerprint, confirmation, manager-only action, duplicate click, stale response, keyboard flow, and non-color warning.

**Detailed implementation steps:**

- [ ] Render current/predicted employee and project risks, skill fit, workload, dependencies, confidence, and expiry.
- [ ] Require a dedicated confirmation action and idempotency key.
- [ ] Poll operation state after accepted approval.
- [ ] Ensure chat UI has no route to the approval endpoint.

**Commands to run:**

```bash
uv run pytest services/agent-api/tests/ui/test_proposal_review.py services/agent-api/tests/ui/test_approval_confirmation.py services/agent-api/tests/ui/test_operation_status.py -q
```

**Expected output or observable result:** Approval creates an `executing` operation placeholder but cannot yet mutate Jira.

**Validation gate:** Product/security reviewer approves explicit confirmation and accessibility.

**Commit checkpoint:** `feat: add proposal review and approval UI`

---

# Phase 7 — Controlled Jira mutation and reconciliation

## Task 7.1: Implement one-shot Jira assignment and read-back verification

**Classification:** Security/Hardening

**Objective:** Execute exactly one assignee update for a safe `executing` proposal and verify it through a fresh Jira MCP read.

**Why this task is needed:** This is the only approved external mutation and is intentionally delayed until every safety prerequisite passes.

**Dependencies:** Tasks 6.1–6.3 and their security validation gates.

**Files or directories:**

- Create: `packages/jira-mcp-client/src/jira_mcp_client/mutation.py`
- Create: `domain/workforce_risk/proposals/execution.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/tools/execution.py`
- Create: `packages/jira-mcp-client/tests/test_mutation.py`
- Create: `tests/integration/test_verified_reassignment.py`

**Tests to write first:**

- Exact assignee-only payload, expected current account precondition, forbidden project, not-executing proposal, duplicate execution, timeout ambiguity, successful read-back, mismatched read-back, and proof that generic retry count remains zero.

**Detailed implementation steps:**

- [ ] Expose mutation capability only to the execution service, not LangGraph.
- [ ] Re-read expected assignee immediately before mutation and mark stale on mismatch.
- [ ] Send one MCP `editJiraIssue` call containing only `assignee.accountId`.
- [ ] Perform a separate `getJiraIssue` read-back.
- [ ] Persist `executed_verified`, `execution_failed`, or `uncertain` in a new transaction with safe receipt evidence.
- [ ] Return existing operation state for duplicate calls.

**Commands to run:**

```bash
uv run pytest packages/jira-mcp-client/tests/test_mutation.py -q
uv run pytest tests/integration/test_verified_reassignment.py -q
```

**Expected output or observable result:** Controlled dev reassignment records success only when the returned account ID exactly matches.

**Validation gate:** No other Jira field changes; no automatic mutation retry; production mutation test is impossible by configuration.

**Commit checkpoint:** `feat: execute and verify approved Jira reassignment`

## Task 7.2: Implement crash-safe reconciliation and uncertain-state handling

**Classification:** Security/Hardening

**Objective:** Resolve abandoned `executing` operations by reading Jira before deciding state, never by blindly repeating a write.

**Why this task is needed:** A crash after Jira succeeds but before local persistence must not cause duplicate mutation or false failure.

**Dependencies:** Task 7.1.

**Files or directories:**

- Create: `domain/workforce_risk/proposals/reconciliation.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/tools/reconciliation.py`
- Create: `services/workforce-risk-mcp/src/workforce_risk_mcp/workers/reconcile.py`
- Create: `tests/integration/test_execution_reconciliation.py`

**Tests to write first:**

- Crash before write, crash after write, proposed assignee observed, previous assignee with proof of no write, third-party assignee, unavailable Jira, repeated reconciliation, and manager resolution.

**Detailed implementation steps:**

- [ ] Lease abandoned operations without holding a transaction across Jira reads.
- [ ] Compare fresh Jira state to expected and proposed account IDs.
- [ ] Resolve only evidence-certain outcomes; otherwise retain `uncertain`.
- [ ] Emit manager business alert and operator health signal for uncertainty.
- [ ] Require a new proposal for any compensating reassignment.

**Commands to run:**

```bash
uv run pytest tests/integration/test_execution_reconciliation.py -q
```

**Expected output or observable result:** Crash-after-write resolves to verified success without a second mutation; ambiguous state stays blocked.

**Validation gate:** Failure-injection review confirms zero blind repeat writes.

**Commit checkpoint:** `feat: reconcile ambiguous Jira executions safely`

---

# Phase 8 — Complete manager workflows

## Task 8.1: Add lightweight alert, report, risk-summary, and audit views

**Classification:** MVP

**Objective:** Complete the chat-first lightweight manager UI and role-scoped
supporting views without a frontend framework or separate service.

**Why this task is needed:** The primary demo requires alert-to-investigation-to-proposal navigation and visible audit evidence.

**Dependencies:** Phases 5–7.

**Files or directories:**

- Create: `services/agent-api/src/agent_api/routes/{alerts,reports,audit}.py`
- Modify: `services/agent-api/src/agent_api/web/templates/chat.html`
- Modify: `services/agent-api/src/agent_api/web/static/{chat.js,styles.css}`
- Create: `services/agent-api/tests/test_alert_routes.py`
- Create: `services/agent-api/tests/test_report_routes.py`
- Create: `services/agent-api/tests/test_audit_routes.py`
- Create: `services/agent-api/tests/ui/test_manager_supporting_views.py`

**Tests to write first:**

- Pagination/filter/sort, alert ETag, recurrence, exact-version report URL, viewer audit denial, administrator audit access, stale warning, operation status, and safe metadata.

**Detailed implementation steps:**

- [ ] Implement stable paginated APIs.
- [ ] Add simple alert inbox, employee/project risk summaries, report list, and
  authorized audit history panels around the primary chat interface.
- [ ] Link contextual investigation and proposal review.
- [ ] Add authorized short-lived report downloads.
- [ ] Render audit chain state without secrets or unrestricted evidence.

**Commands to run:**

```bash
uv run pytest services/agent-api/tests -q
uv run pytest services/agent-api/tests/ui/test_manager_supporting_views.py -q
```

**Expected output or observable result:** A manager can traverse the complete workflow; a viewer cannot approve or access audit history.

**Validation gate:** Role matrix and accessibility suite pass.

**Commit checkpoint:** `feat: complete lightweight manager workflows`

## Task 8.2: Add rate limits, request limits, and complete API authorization

**Classification:** Security/Hardening

**Objective:** Apply production-safe boundaries to every protected endpoint and cross-environment request.

**Why this task is needed:** Chat, scans, simulations, proposals, approvals, reports, and admin endpoints have different abuse and safety risks.

**Dependencies:** Task 8.1.

**Files or directories:**

- Create: `services/agent-api/src/agent_api/security/{limits,environment}.py`
- Create: `tests/security/test_api_authorization_matrix.py`
- Create: `tests/security/test_request_limits.py`

**Tests to write first:**

- Every role/endpoint combination, forged identity field, cross-environment or
  wrong-project API key, oversized request, repeated scan/simulation/approval,
  expired/revoked key, report ID enumeration, authentication-store outage with
  eligible short-lived cached read, cache expiry, approval/write fail-closed,
  and safe error response.

**Detailed implementation steps:**

- [ ] Define per-route rate and size policies.
- [ ] Enforce environment and Jira project scope server-side.
- [ ] Bound cached successful key validation by a short configured TTL and use
  it only for eligible degraded reads; reject proposals, approvals, profile/
  scoring administration, and Jira writes whenever authoritative key state is
  unavailable.
- [ ] Return `401`, `403`, `409`, `413`, and `429` with stable codes/correlation IDs.
- [ ] Confirm the browser stores the raw API key only in tab-scoped
  `sessionStorage`, never `localStorage`, cookies, DOM text, URLs, or error
  diagnostics, and clears it on logout.

**Commands to run:**

```bash
uv run pytest tests/security/test_api_authorization_matrix.py tests/security/test_request_limits.py -q
```

**Expected output or observable result:** Authorization matrix has no unexpected allow; client-supplied identity never changes audit actor.

**Validation gate:** Security review signs the endpoint matrix.

**Commit checkpoint:** `security: enforce API authorization and limits`

---

# Phase 9 — Read-only DevOps MCP and observability

## Task 9.1: Implement the read-only DevOps MCP server

**Classification:** MVP

**Objective:** Expose allowlisted Kubernetes, Prometheus, Loki, SQS, Jira integration, and deployment evidence without mutation permissions.

**Why this task is needed:** Operators and the agent need diagnostic evidence while preserving strict read-only RBAC.

**Dependencies:** Stable service metrics/log schemas from prior phases.

**Files or directories:**

- Create: `services/devops-mcp/src/devops_mcp/{server,schemas}.py`
- Create: `services/devops-mcp/src/devops_mcp/tools/{kubernetes,prometheus,logs,queues,deployments}.py`
- Create: `services/devops-mcp/tests/`
- Create: `tests/contract/test_devops_mcp_transport.py`

**Tests to write first:**

- Each read tool, namespace scope, query allowlist, time range/log limit, secret redaction, malformed backend response, timeout, and absence of restart/scale/deploy/rollback tools.

**Detailed implementation steps:**

- [ ] Implement typed read-only tools with bounded queries.
- [ ] Add environment and correlation envelopes.
- [ ] Restrict Kubernetes client verbs to get/list/watch and logs.
- [ ] Surface Jira auth, JQL, schema, rate-limit, conflict, verification, and circuit evidence.
- [ ] Expose deployment status as read-only metadata.

**Commands to run:**

```bash
uv run pytest services/devops-mcp/tests tests/contract/test_devops_mcp_transport.py -q
```

**Expected output or observable result:** Real MCP transport returns diagnostic evidence; mutation tool enumeration is empty.

**Validation gate:** RBAC/static review proves no write verbs or operational action tools.

**Commit checkpoint:** `feat: add read-only DevOps MCP diagnostics`

## Task 9.2: Instrument metrics, logs, traces, dashboards, and alerts

**Classification:** Infrastructure

**Objective:** Provide bounded-cardinality end-to-end observability for process, readiness, and workflow health.

**Why this task is needed:** The system must expose failures before users encounter unsafe or silent degradation.

**Dependencies:** Task 9.1.

**Files or directories:**

- Create: `packages/observability/src/workforce_observability/`
- Create: `infra/kubernetes/observability/{prometheus-rules,grafana-dashboards,loki,otel}.yaml`
- Create: `tests/integration/test_correlation_propagation.py`
- Create: `tests/observability/{test_metrics,test_logs,test_alerts}.py`
- Create: `docs/runbooks/`

**Tests to write first:**

- Required metrics, forbidden labels, secret/API-key redaction, HTTP→MCP→SQS
  correlation, missed scan, queue backlog, uncertain write, Jira circuit, and
  dashboard JSON load.

**Detailed implementation steps:**

- [ ] Instrument API, graph, MCP, scoring, scans, proposals, notifications, Jira, RDS, S3, and cluster signals.
- [ ] Keep IDs/correlation/raw errors out of metric labels.
- [ ] Add structured logs and trace propagation with environment-specific sampling/retention.
- [ ] Create four approved dashboards.
- [ ] Add grouped/inhibited operator alerts with severity, owner, runbook, environment, and context.

**Commands to run:**

```bash
uv run pytest tests/observability tests/integration/test_correlation_propagation.py -q
promtool check rules infra/kubernetes/observability/prometheus-rules.yaml
```

**Expected output or observable result:** Failure fixtures fire one actionable grouped alert and can be traced by correlation ID.

**Validation gate:** Business-risk alerts remain outside Alertmanager and sensitive workforce data remains outside shared dashboards.

**Commit checkpoint:** `feat: add end-to-end observability`

---

# Phase 10 — Containers and local integration

## Task 10.1: Containerize every custom workload with health and shutdown contracts

**Classification:** Infrastructure

**Objective:** Build pinned, non-root, reproducible images for all custom
workloads, with the lightweight UI embedded in the Agent API image.

**Why this task is needed:** Kubernetes deployment and image promotion require immutable, probe-ready artifacts.

**Dependencies:** Application services complete; Task 0.4.

**Files or directories:**

- Create: `services/agent-api/Dockerfile`
- Create: `services/workforce-risk-mcp/Dockerfile`
- Create: `services/devops-mcp/Dockerfile`
- Create: `services/notification-worker/Dockerfile`
- Modify: `.dockerignore`, `compose.yaml`
- Create: `tests/infrastructure/test_container_contracts.py`

**Tests to write first:**

- Non-root UID, no secrets, pinned base image, live/ready/start endpoints, signal handling during scan/execution, image labels, and read-only filesystem compatibility.

**Detailed implementation steps:**

- [ ] Use multi-stage builds and exact base digests.
- [ ] Copy validated `web/templates` and `web/static` assets into the Agent API
  image and prove their checksums match the tested source tree.
- [ ] Separate startup, liveness, and request-specific readiness.
- [ ] Add graceful stop and bounded checkpoint behavior.
- [ ] Run PostgreSQL/LocalStack/local MCP services through Compose for integration.

**Commands to run:**

```bash
docker compose build
docker compose up -d
uv run pytest tests/infrastructure/test_container_contracts.py -q
docker compose ps
```

**Expected output or observable result:** Every container is healthy, non-root, and shuts down without false success.

**Validation gate:** Vulnerability scan has no unaccepted critical finding.

**Commit checkpoint:** `build: containerize workforce risk services`

---

# Phase 11 — AWS infrastructure and self-managed Kubernetes

## Task 11.1: Provision secure Terraform state and shared AWS resources

**Classification:** Infrastructure

**Objective:** Create encrypted remote state, locking, OIDC roles, ECR, and shared IAM foundations.

**Why this task is needed:** Environment infrastructure and CI/CD cannot safely proceed with local state or long-lived AWS credentials.

**Dependencies:** Stakeholder infrastructure approvals; Task 0.4.

**Files or directories:**

- Create: `infra/terraform/bootstrap/`
- Create: `infra/terraform/shared/`
- Create: `tests/infrastructure/terraform/`

**Tests to write first:**

- Encryption, public-access block, versioning, lock table, least-privilege OIDC trust, sensitive outputs, and no literal secret values.

**Detailed implementation steps:**

- [ ] Bootstrap S3 state and DynamoDB locking.
- [ ] Use separate state keys and environment-scoped apply roles.
- [ ] Create ECR repositories and GitHub OIDC roles.
- [ ] Add cost tags and outputs without secret values.

**Commands to run:**

```bash
terraform -chdir=infra/terraform/bootstrap fmt -check -recursive
terraform -chdir=infra/terraform/bootstrap init
terraform -chdir=infra/terraform/bootstrap validate
terraform -chdir=infra/terraform/shared init -backend=false
terraform -chdir=infra/terraform/shared validate
```

**Expected output or observable result:** Terraform validates and static security checks report no high-severity unresolved finding.

**Validation gate:** State backend is encrypted/locked before environment apply.

**Commit checkpoint:** `infra: add secure Terraform state and shared resources`

## Task 11.2: Provision network, EC2 kubeadm nodes, and automated joining

**Classification:** Infrastructure

**Objective:** Build the approved one-control-plane/two-worker cluster topology with private data paths and bounded automated joining.

**Why this task is needed:** This satisfies the self-managed Kubernetes deployment boundary without EKS.

**Dependencies:** Task 11.1.

**Files or directories:**

- Create: `infra/terraform/environment/{network,compute,iam,ssm}.tf`
- Create: `infra/terraform/environment/templates/{control-plane,worker}.sh.tftpl`
- Create: `scripts/validation/verify_node_join.sh`
- Create: `tests/infrastructure/test_node_join.py`

**Tests to write first:**

- No broad SSH/API/RDS exposure, short-lived encrypted join data, least-privilege Parameter Store, bounded worker retry, idempotent rejoin, token expiry, replacement worker, and visible failure logs.

**Detailed implementation steps:**

- [ ] Add static policy checks that reject EKS Terraform resources, EKS
  modules, and EKS kubeconfig assumptions; Amazon EKS is not used.
- [ ] Provision multi-AZ VPC, public NLB path, private node/data paths, security groups, IAM, EC2, and storage.
- [ ] Install pinned containerd/Kubernetes packages.
- [ ] Run `kubeadm init`, install pinned Calico, and publish minimal join material.
- [ ] Make workers retrieve with bounded backoff and verify membership before joining.
- [ ] Invalidate join material and document rotation/replacement.

**Commands to run:**

```bash
terraform -chdir=infra/terraform/environment init -backend=false
terraform -chdir=infra/terraform/environment validate
uv run pytest tests/infrastructure/test_node_join.py -q
bash scripts/validation/verify_node_join.sh
```

**Expected output or observable result:** `kubectl get nodes` shows one control plane and two Ready workers; join material is expired/removed.

**Validation gate:** Kubernetes API and nodes are not broadly public; SSM administration works.

**Commit checkpoint:** `infra: provision automated kubeadm cluster`

## Task 11.3: Provision environment AWS services and secrets boundaries

**Classification:** Infrastructure

**Objective:** Provision RDS, S3, SQS/DLQ, SES, Secrets Manager, Bedrock IAM,
load balancing, and environment isolation without Cognito.

**Why this task is needed:** The deployed workflows depend on isolated managed services and identities.

**Dependencies:** Task 11.2 and Task 0.1 RDS/SMTP decisions.

**Files or directories:**

- Create: `infra/terraform/environment/{database,storage,queue,email,secrets,bedrock,ingress}.tf`
- Create: `tests/infrastructure/test_environment_isolation.py`
- Create: `tests/infrastructure/test_iam_permissions.py`

**Tests to write first:**

- Private RDS, backups/encryption, separate dev/prod
  buckets/queues/DLQs/secrets, API-key pepper/initial-key secret containers
  without values,
  least privilege, cross-environment denial, and sensitive state outputs.

**Detailed implementation steps:**

- [ ] Apply the approved RDS topology with distinct databases/roles/credentials.
- [ ] Create separate dev/prod report buckets and queues.
- [ ] Create separate dev/prod DLQs, secret containers, IAM bindings, and
  release-configuration inputs; never reuse a service credential across
  environments.
- [ ] Create secret containers and External Secrets IAM only; supply values through secure operations.
- [ ] Create separate secret containers for API-key HMAC peppers and initial
  dev/prod keys; deliver them with External Secrets Operator and never place
  raw values in Terraform state or outputs.
- [ ] Create Bedrock and SES policies limited by environment.
- [ ] Document continuous costs and cleanup.

**Commands to run:**

```bash
terraform -chdir=infra/terraform/environment validate
uv run pytest tests/infrastructure/test_environment_isolation.py tests/infrastructure/test_iam_permissions.py -q
```

**Expected output or observable result:** Automated tests prove dev credentials cannot reach prod resources and RDS is private.

**Validation gate:** Security and cost review approves the Terraform plan before apply.

**Commit checkpoint:** `infra: provision isolated application services`

## Task 11.4: Install cluster add-ons and validate workload manifests

**Classification:** Infrastructure

**Objective:** Install pinned cluster add-ons and statically validate the dev
and prod workload definitions without deploying the application stack to
production.

**Why this task is needed:** Cluster capabilities and production-quality
manifests must be ready before GitHub Actions becomes the sole owner of
application release deployment and promotion.

**Dependencies:** Tasks 10.1 and 11.1–11.3.

**Files or directories:**

- Create: `infra/kubernetes/base/`
- Create: `infra/kubernetes/overlays/{dev,prod}/`
- Create: `infra/kubernetes/observability/`
- Create: `tests/infrastructure/test_manifests.py`
- Create: `scripts/validation/verify_cluster_addons.sh`
- Create: `scripts/validation/validate_workload_manifests.sh`

**Tests to write first:**

- Schema/policy validation, namespaces, distinct dev/prod service accounts and
  release configuration, External Secrets, network policies, probes,
  requests/limits, PDBs, production HPA target/metric, CronJob `Forbid`,
  deadlines/history, migration Job, separate Jira scopes, and prod read-only
  Jira config.
- Prove Phase 11 validation does not apply application Deployments, StatefulSets,
  Jobs, CronJobs, Services, or Ingress resources to production.
- Reject any `simulation` namespace or scenario-controller Deployment, Pod,
  Job, CronJob, Service, container, or Kubernetes credential.

**Detailed implementation steps:**

- [ ] Install Calico, NGINX Ingress, metrics-server, External Secrets Operator, Prometheus, Alertmanager, Grafana, Loki, log collector, and OTel collector using pins.
- [ ] Apply namespace foundations, ExternalSecret definitions, NetworkPolicies,
  service accounts, and read-only DevOps RBAC needed before releases.
- [ ] Author dev/prod workload manifests for probes, resources, PDBs, migration
  Job, CronJobs, ingress, and the provisional production HPA without applying
  the application stack.
- [ ] Render both overlays with immutable digest placeholders supplied through
  the release workflow and reject mutable image tags.
- [ ] Validate schemas, policies, namespace isolation, Jira scopes, production
  read-only smoke configuration, and compatibility with installed add-ons.
- [ ] Record installed add-on versions/health and manifest-validation results
  for Phase 12.

**Commands to run:**

```bash
kustomize build infra/kubernetes/overlays/dev | kubeconform -strict -
kustomize build infra/kubernetes/overlays/prod | kubeconform -strict -
uv run pytest tests/infrastructure/test_manifests.py -q
bash scripts/validation/verify_cluster_addons.sh
bash scripts/validation/validate_workload_manifests.sh
```

**Expected output or observable result:** Pinned cluster add-ons are healthy;
both application overlays pass schema, policy, isolation, and immutable-digest
validation; no application workload has been deployed to production.

**Validation gate:** Add-on health and workload-manifest tests pass, the
production namespace contains no application release from Phase 11, and
reviewers confirm GitHub Actions remains the owner of dev deployment and
production promotion.

**Commit checkpoint:** `infra: install addons and validate workload manifests`

## Task 11.5: Implement and rehearse backup and recovery

**Classification:** Security/Hardening

**Objective:** Prove restore procedures for RDS, S3 reports, etcd, scoring configuration, and audit data.

**Why this task is needed:** Backup creation without restore testing does not satisfy resilience requirements.

**Dependencies:** Tasks 11.3–11.4.

**Files or directories:**

- Create: `docs/runbooks/{rds-restore,s3-recovery,etcd-restore,audit-recovery}.md`
- Create: `scripts/validation/rehearse_restore.sh`
- Create: `tests/infrastructure/test_restore_evidence.py`

**Tests to write first:**

- Restore into isolated dev targets, checksum/version verification, audit-chain verification, scoring-version preservation, and no prod overwrite.

**Detailed implementation steps:**

- [ ] Restore an RDS snapshot into an isolated rehearsal database.
- [ ] Recover a versioned report and verify checksum.
- [ ] Restore etcd into a disposable control-plane rehearsal.
- [ ] Verify scoring and audit history consistency.
- [ ] Record timings, owners, evidence, and cleanup.

**Commands to run:**

```bash
bash scripts/validation/rehearse_restore.sh dev
uv run pytest tests/infrastructure/test_restore_evidence.py -q
```

**Expected output or observable result:** All restored artifacts match source checksums/versions and no production resource changes.

**Validation gate:** Operations reviewer signs the restore rehearsal.

**Commit checkpoint:** `docs: add verified backup and recovery runbooks`

---

# Phase 12 — CI/CD deployment, HPA validation, and release promotion

## Task 12.1: Deploy the application stack to dev through GitHub Actions

**Classification:** Infrastructure

**Objective:** Build, scan, and deploy immutable application digests to dev
automatically through the dedicated GitHub Actions workflow.

**Why this task is needed:** Dev must validate the complete release before HPA
tuning or production approval, and GitHub Actions must remain the application
release owner.

**Dependencies:** Phase 11.

**Files or directories:**

- Create: `.github/workflows/deploy-dev.yml`
- Create: `.github/workflows/{terraform-plan,terraform-apply}.yml`
- Create: `scripts/validation/{smoke_dev,record_release}.sh`
- Create: `tests/infrastructure/test_workflow_policies.py`

**Tests to write first:**

- Dev concurrency, OIDC/minimal permissions, immutable digest deployment,
  failed migration, failed readiness, Jira read failure, duplicate trigger,
  embedded UI availability, dev manager API-key authentication, seven-person
  seed verification, and no destructive database rollback.

**Detailed implementation steps:**

- [ ] Build images once, produce SBOM/scans, and push to ECR.
- [ ] Deploy only verified digests, not mutable tags.
- [ ] Run one idempotent bounded migration Job and stop on failure.
- [ ] Run all required dev smoke tests: embedded UI/static assets, API-key
  authentication and scope denial, Agent API, all MCP transports, PostgreSQL,
  S3, SQS/email, Jira read, seven-person dataset, seeded overload detection,
  and simulation without mutation.
- [ ] Use deployment concurrency so only one dev release runs at a time.
- [ ] Record commit, exact digests, manifests, scoring/migration versions,
  actor, times, and dev results as the promotion candidate.
- [ ] Publish GitHub Actions summaries and JUnit-compatible results for
  validation, migrations, rollout, and smoke tests.
- [ ] Upload coverage to Codecov or the approved equivalent and retain
  failed-test diagnostics, security/vulnerability reports, SBOMs, Terraform
  plan summaries, Kubernetes validation, and deployment/smoke-test artifacts.

**Commands to run:**

```bash
actionlint .github/workflows/*.yml
uv run pytest tests/infrastructure/test_workflow_policies.py -q
bash scripts/validation/smoke_dev.sh
```

**Expected output or observable result:** Dev is running exact recorded image
digests and is reported successful only after migration, rollout, readiness,
smoke tests, Prometheus target health, and release metadata pass.

**Validation gate:** The dev workflow is the only application deployment owner;
its failed-deployment rehearsal rolls back only image digests and never runs
destructive database rollback.

**Commit checkpoint:** `ci: deploy immutable releases to dev`

## Task 12.2: Run and record production-shaped HPA validation and tuning

**Classification:** Infrastructure

**Objective:** Exercise the dev-tested release under production-shaped load,
tune resource requests and the provisional HPA, and record scale behavior before
production promotion.

**Why this task is needed:** The final production HPA settings must be based on
measured workload evidence rather than being guessed during cluster setup.

**Dependencies:** Tasks 0.5 and 12.1.

**Files or directories:**

- Create: `tests/infrastructure/test_hpa_behavior.py`
- Create: `tests/performance/hpa_load.js`
- Create: `scripts/validation/verify_hpa.sh`
- Create: `docs/validations/production-hpa-results.md`
- Modify: `infra/kubernetes/overlays/prod/`

**Tests to write first:**

- Baseline resource use, production-shaped request mix, selected CPU or
  bounded-cardinality custom metric, controlled scale-out, maximum replicas,
  stabilization, scale-down, latency/error objectives, and repeatable evidence.

**Detailed implementation steps:**

- [ ] Run the Task 0.5 workload profile against the exact dev-tested digest in
  an isolated production-shaped validation scope that cannot mutate production
  Jira data.
- [ ] Measure baseline CPU/memory, request latency, errors, queue behavior, and
  selected HPA metric.
- [ ] Tune realistic requests/limits, thresholds, minimum/maximum replicas, and
  stabilization windows.
- [ ] Prove scale-out, bounded replicas, stabilization, and scale-down without
  violating the approved latency or error objectives.
- [ ] Apply the measured configuration to the production overlay and rerun
  manifest validation without deploying the application to production.
- [ ] Record commands, release digests, measurements, charts, outcomes, and
  reviewer decision in the HPA validation report.

**Commands to run:**

```bash
uv run pytest tests/infrastructure/test_hpa_behavior.py -q
k6 run tests/performance/hpa_load.js
bash scripts/validation/verify_hpa.sh --environment production-shaped
bash scripts/validation/validate_workload_manifests.sh
```

**Expected output or observable result:** The exact dev-tested release produces
reviewable scale-out, stabilization, and scale-down evidence, and the validated
production overlay contains the measured HPA configuration.

**Validation gate:** Architecture/operations reviewers approve
`docs/validations/production-hpa-results.md`; production promotion remains
blocked until this task passes.

**Commit checkpoint:** `perf: validate and tune production hpa`

## Task 12.3: Promote exact dev-tested digests to production with approval

**Classification:** Infrastructure

**Objective:** Promote the exact release digests validated in dev and Task 12.2
to production through a protected GitHub Actions approval.

**Why this task is needed:** Production must receive no rebuild or unreviewed
artifact, and release authority must remain with the protected CI/CD workflow.

**Dependencies:** Tasks 12.1–12.2.

**Files or directories:**

- Create: `.github/workflows/promote-prod.yml`
- Create: `scripts/validation/smoke_prod.sh`
- Modify: `scripts/validation/record_release.sh`
- Modify: `tests/infrastructure/test_workflow_policies.py`

**Tests to write first:**

- Protected-environment approval, unauthorized promotion, environment
  concurrency, exact digest equality with dev, no rebuild, migration failure,
  readiness failure, non-destructive Jira/production smoke tests,
  previous-digest rollback, and prohibition of destructive database rollback.

**Detailed implementation steps:**

- [ ] Resolve the approved dev release record and reject missing, changed, or
  unvalidated digests.
- [ ] Require the protected production environment approval and
  environment-scoped OIDC role.
- [ ] Promote by digest without rebuilding or retag-based resolution.
- [ ] Run one bounded idempotent migration Job and stop promotion on failure.
- [ ] Verify rollout, readiness, non-destructive production smoke checks,
  Prometheus targets, logs/metrics arrival, and release metadata.
- [ ] Allow automatic image-digest rollback only for clear rollout-health
  failure before business mutations; never run destructive database rollback.
- [ ] Record commit, exact dev/prod digests, manifest/scoring/migration versions,
  HPA validation reference, actor, approval, times, and smoke-test results.

**Commands to run:**

```bash
actionlint .github/workflows/promote-prod.yml
uv run pytest tests/infrastructure/test_workflow_policies.py -q
bash scripts/validation/smoke_prod.sh
```

**Expected output or observable result:** Production runs the exact dev-tested,
HPA-validated digests after protected approval, and success is reported only
after every non-destructive verification and release record passes.

**Validation gate:** Digest equality, protected approval, rollout, migration,
smoke, observability, and metadata evidence pass; GitHub Actions is confirmed as
the sole owner of application release promotion.

**Commit checkpoint:** `ci: promote approved digests to production`

---

# Phase 13 — Final verification and demonstration readiness

## Task 13.1: Complete end-to-end, security, resilience, performance, and accessibility suites

**Classification:** Security/Hardening

**Objective:** Prove every acceptance criterion and controlled failure path with inspectable CI artifacts.

**Why this task is needed:** The system is not implementation-ready for stakeholder acceptance until safety and operational behavior are demonstrated.

**Dependencies:** Phases 1–12.

**Files or directories:**

- Create: `tests/e2e/test_primary_workflow.py`
- Create: `tests/e2e/test_backup_scenario.py`
- Create: `tests/security/test_resilience_matrix.py`
- Create: `tests/performance/test_workloads.py`
- Create: `services/agent-api/tests/ui/test_accessibility_e2e.py`
- Create: `docs/test-mapping.md`

**Tests to write first:**

- Seeded detection through verified reassignment, stale rejection, fallback,
  uncertain visibility, secret/API-key leakage, forged/revoked/cross-environment
  API keys, shutdown during scan/write, duplicate SQS, audit tampering,
  realistic scan duration, concurrent simulation, backlog processing, and
  WCAG-oriented UI checks.

**Detailed implementation steps:**

- [ ] Map every specification requirement to at least one automated test.
- [ ] Run primary deterministic scenario using one correlation ID.
- [ ] Run a safe prepared backup scenario.
- [ ] Measure initial SLOs and record baselines.
- [ ] Upload JUnit, coverage, performance, accessibility, SBOM, scan, Terraform, and smoke summaries.
- [ ] Add a regression test for every significant defect discovered.

**Commands to run:**

```bash
uv run pytest tests/e2e tests/security tests/performance -q
uv run pytest services/agent-api/tests/ui/test_accessibility_e2e.py -q
make check
```

**Expected output or observable result:** Primary scenario completes from scan to verified Jira reassignment; all controlled unsafe attempts fail closed.

**Validation gate:** Stakeholders approve the test mapping and evidence artifacts.

**Commit checkpoint:** `test: complete system acceptance coverage`

## Task 13.2: Prepare deterministic seed, cleanup, readiness, and incident runbooks

**Classification:** MVP

**Objective:** Make the complete demonstration resettable, safe, and operable without production mutation.

**Why this task is needed:** The approved workflow requires repeatable synthetic data, a backup scenario, and explicit operational response.

**Dependencies:** Tasks 3.6 and 13.1.

**Files or directories:**

- Modify: `scripts/jira/{seed_dev,advance_scenario,reset_dev,cleanup_dev,verify_seed}.py`
- Modify: `scripts/scenario/evaluate_results.py`
- Reference: `.github/workflows/run-scenario.yml`
- Reference: `tests/fixtures/scenarios/seven_employee_team.json`
- Create: `scripts/demo/{reset,readiness,primary,backup}.sh`
- Create: `docs/runbooks/{demo-readiness,jira-credential-leak,api-key-compromise,report-url-exposure,cross-environment-access,uncertain-mutation,audit-corruption}.md`
- Create: `tests/e2e/test_demo_reset_and_readiness.py`

**Tests to write first:**

- End-to-end reset invokes the already-verified Task 3.6 scripts, verifies the
  seven-profile/two-account dataset, preserves primary/backup isolation, refuses
  production, and returns actionable readiness failures.

**Detailed implementation steps:**

- [ ] Compose the Task 3.6 reset/verify commands into one safe demo reset path
  and keep their exact project/environment/production guards intact.
- [ ] Make the primary/backup demo scripts invoke the external scenario tooling
  from the workstation or trigger `run-scenario.yml`; never create or invoke a
  simulator pod, Job, CronJob, or namespace.
- [ ] Implement readiness checks for services, dev manager API key,
  lightweight UI, Bedrock/fallback, Jira MCP, seeded dataset, report, email,
  dashboards, and CI.
- [ ] Document incident containment, rotation, reconciliation, evidence preservation, and recovery.

**Commands to run:**

```bash
uv run pytest tests/e2e/test_demo_reset_and_readiness.py -q
bash scripts/demo/reset.sh
bash scripts/demo/readiness.sh
bash scripts/demo/primary.sh
bash scripts/demo/backup.sh
```

**Expected output or observable result:** Repeated reset produces the same expected risks; both scenarios run safely against synthetic dev only.

**Validation gate:** Demonstration readiness checklist passes immediately before stakeholder review.

**Commit checkpoint:** `docs: prepare deterministic demo and incident runbooks`

---

# Phase 14 — Extra-credit skills and optional production hardening

## Task 14.1: Create the workforce-risk triage skill

**Classification:** Stretch

**Objective:** Create a reusable read-only skill for evidence-based employee,
project, alert, and risk-result triage.

**Why this task is needed:** It encodes the specification’s safe investigation
workflow for repeatable use without granting mutation authority.

**Dependencies:** MVP acceptance; Tasks 4.2, 8.1, and 9.1. Use
`superpowers:writing-skills` when executing this task.

**Files or directories:**

- Create: `skills/workforce-risk-triage/SKILL.md`
- Create: `skills/workforce-risk-triage/references/output-schema.md`
- Create: `tests/skills/test_workforce_risk_triage_skill.py`
- Create: `tests/skills/fixtures/triage_cases.yaml`

**Tests to write first:**

- Trigger and non-trigger cases, prerequisites, unauthorized scope,
  protected-characteristic request, missing evidence, unsafe environment,
  approval-bypass request, degraded read, citations, redaction, and exact output
  fields.

**Detailed implementation steps:**

- [ ] Write fixture-driven failing tests that parse the skill and exercise
  allowed and refused scenarios.
- [ ] Define triggers for employee, project, alert, and risk-result
  investigation.
- [ ] Define authenticated read prerequisites, bounded context references,
  eligible snapshot rules, and correlation requirements.
- [ ] Encode read-only boundaries, refusal conditions, typed evidence workflow,
  score/version validation, redaction, degraded behavior, and safe errors.
- [ ] Require outputs containing risk summary, deterministic score/confidence,
  factors, citations, freshness, recommendations, missing data, and correlation
  ID.
- [ ] Verify the skill never implies profile, approval, Jira, or operational
  mutation authority.

**Commands to run:**

```bash
uv run pytest tests/skills/test_workforce_risk_triage_skill.py -q
rg -n 'Trigger|Prerequisites|Boundaries|Refusal|Workflow|Validation|Failure|Expected outputs' skills/workforce-risk-triage/SKILL.md
```

**Expected output or observable result:** Allowed read-only triage produces the
specified evidence-based output; unsafe or unauthorized cases refuse safely.

**Validation gate:** Security/domain reviewers confirm the skill preserves
score immutability, privacy, project scope, and `read degraded; write closed`.

**Commit checkpoint:** `feat: add workforce risk triage skill`

## Task 14.2: Create the deploy-and-verify-environment skill

**Classification:** Stretch

**Objective:** Create a reusable skill that invokes or inspects the approved
deployment path and verifies environment health without ad hoc mutation.

**Why this task is needed:** Deployment readiness requires a repeatable,
approval-aware workflow with observable success criteria.

**Dependencies:** MVP acceptance; Tasks 11.4 and 12.1. Use
`superpowers:writing-skills` when executing this task.

**Files or directories:**

- Create: `skills/deploy-and-verify-environment/SKILL.md`
- Create: `skills/deploy-and-verify-environment/references/release-contract.md`
- Create: `tests/skills/test_deploy_verify_skill.py`
- Create: `tests/skills/fixtures/deployment_cases.yaml`

**Tests to write first:**

- Dev trigger, approved production trigger, unapproved production refusal,
  mutable tag, failed CI, missing migration, environment mismatch, failed
  readiness, safe rollback recommendation, and expected release evidence.

**Detailed implementation steps:**

- [ ] Write failing fixture tests for triggers, gates, refusals, failures, and
  outputs.
- [ ] Require approved commit/digests, CI, environment authorization, migration
  state, release configuration, and read-only diagnostic access.
- [ ] Encode the GitHub Actions plus Helm/manifests workflow, rollout/migration
  observation, smoke tests, Prometheus target verification, and release-record
  validation.
- [ ] Refuse ad hoc AWS/Kubernetes mutation, secret exposure, mutable tags,
  missing gates, and production approval bypass.
- [ ] Require environment, commit, digests, configuration, migration, rollout,
  smoke, observability, release-record, and safe failure outputs.

**Commands to run:**

```bash
uv run pytest tests/skills/test_deploy_verify_skill.py -q
rg -n 'Trigger|Prerequisites|Boundaries|Refusal|Workflow|Validation|Failure|Expected outputs' skills/deploy-and-verify-environment/SKILL.md
```

**Expected output or observable result:** The skill reports success only for an
approved digest whose migration, rollout, smoke tests, targets, and release
record are verified.

**Validation gate:** Delivery/security reviewers confirm it cannot bypass
production approval or execute destructive database rollback.

**Commit checkpoint:** `feat: add environment deployment verification skill`

## Task 14.3: Create the safe Jira reassignment demo skill

**Classification:** Stretch

**Objective:** Create a deterministic dev-only demonstration skill for the
complete detection-to-verified-reassignment workflow.

**Why this task is needed:** The mutating demonstration must be repeatable,
auditable, and structurally incapable of targeting production.

**Dependencies:** MVP acceptance; Tasks 7.2 and 13.2. Use
`superpowers:writing-skills` when executing this task.

**Files or directories:**

- Create: `skills/safe-jira-reassignment-demo/SKILL.md`
- Create: `skills/safe-jira-reassignment-demo/references/demo-contract.md`
- Create: `tests/skills/test_safe_jira_demo_skill.py`
- Create: `tests/skills/fixtures/jira_demo_cases.yaml`

**Tests to write first:**

- Correct dev trigger, production/unknown-scope refusal, missing identity,
  unseeded state, stale/low-confidence proposal, expected-assignee mismatch,
  chat approval, ambiguous mutation, read-back mismatch, audit failure,
  cleanup production refusal, and expected outputs.

**Detailed implementation steps:**

- [ ] Write failing fixture tests for every safety and failure case.
- [ ] Require seeded dev data, verified MCP read/write, manager identity,
  persistence, reset capability, and one correlation ID.
- [ ] Encode scope validation, guarded reset/seed, detection, alert inspection,
  deterministic simulation, proposal creation, explicit approval, one-shot
  execution, read-back, audit display, and guarded cleanup.
- [ ] Refuse production/unknown scopes and every missing authorization,
  freshness, confidence, expected-state, or audit prerequisite.
- [ ] On ambiguity, require `uncertain`, stop automatic action, preserve
  evidence, and select the prepared fallback demonstration.
- [ ] Require readiness, score, explanation, simulation, proposal/approval,
  verified Jira result, audit, cleanup, and correlation outputs.

**Commands to run:**

```bash
uv run pytest tests/skills/test_safe_jira_demo_skill.py -q
rg -n 'Trigger|Prerequisites|Boundaries|Refusal|Workflow|Validation|Failure|Expected outputs' skills/safe-jira-reassignment-demo/SKILL.md
```

**Expected output or observable result:** The normal synthetic dev scenario
completes with exact read-back and audit evidence; unsafe scenarios stop before
mutation or become visibly uncertain.

**Validation gate:** Security/demo reviewers confirm chat cannot approve,
mutation cannot target production, and no ambiguous write is retried.

**Commit checkpoint:** `feat: add safe Jira reassignment demo skill`

## Task 14.4: Optionally adopt Argo CD production hardening

**Classification:** Stretch

**Objective:** Execute the Task 0.5 Argo CD decision without changing the MVP
GitHub Actions plus Helm/manifests deployment path.

**Why this task is needed:** The specification requires an explicit
adopt-or-omit validation and allows Argo CD only as optional hardening.

**Dependencies:** MVP acceptance; Task 0.5 decision; Task 12.3.

**Files or directories:**

- Modify: `docs/validations/argocd-decision.md`
- Create only when decision is `adopt`: `infra/kubernetes/production-hardening/argocd/`
- Create only when decision is `adopt`: `tests/infrastructure/test_argocd_controls.py`

**Tests to write first:**

- For omission: decision record proves no runtime dependency or missing MVP
  evidence.
- For adoption: immutable digests, reviewed environment configuration,
  environment isolation, no secret material, no bypass of CI/approval/migration
  gates, reconciliation health, and rollback-policy preservation.

**Detailed implementation steps:**

- [ ] If decision is `omit`, record rationale, verify Tasks 12.1–12.3 remain
  the complete GitHub Actions deployment and promotion path, run the omission
  check, and finish this task
  without creating Argo CD resources.
- [ ] If decision is `adopt`, pin the Argo CD version in `config/versions.env`
  and extend the compatibility matrix.
- [ ] Configure reconciliation for reviewed production manifests and immutable
  image digests only.
- [ ] Preserve GitHub checks, protected production approval, migration Job,
  smoke tests, release metadata, and rollback rules.
- [ ] Validate authenticated access, least privilege, secrets handling,
  observability, and removal/recovery procedures.

**Commands to run:**

```bash
rg -n '^Decision: (adopt|omit)$' docs/validations/argocd-decision.md
if rg -q '^Decision: adopt$' docs/validations/argocd-decision.md; then uv run pytest tests/infrastructure/test_argocd_controls.py -q; else test ! -e infra/kubernetes/production-hardening/argocd; fi
```

**Expected output or observable result:** Omission leaves a complete,
independent MVP delivery path; adoption adds controlled reconciliation without
bypassing any release gate.

**Validation gate:** Production-hardening reviewer signs the decision and, when
adopted, the reconciliation/security evidence.

**Commit checkpoint:** `docs: record Argo CD hardening outcome`

---

# Phase 15 — Stretch work after MVP acceptance

## Task 15.1: Add optional PDF report rendering

**Classification:** Stretch

**Objective:** Render the existing immutable JSON report as a manager-downloadable PDF without changing report truth.

**Why this task is needed:** PDF is explicitly optional and must never delay JSON MVP completion.

**Dependencies:** MVP acceptance and stakeholder approval.

**Files or directories:**

- Create: `domain/workforce_risk/reports/pdf.py`
- Create: `domain/workforce_risk/tests/test_pdf_report.py`

**Tests to write first:**

- JSON/PDF content parity, accessibility metadata, secret exclusion, deterministic source version, and failure leaving JSON valid.

**Detailed implementation steps:**

- [ ] Render only from a persisted versioned JSON artifact.
- [ ] Store PDF as a separate immutable S3 object/version.
- [ ] Keep JSON as authoritative and tolerate PDF failure.

**Commands to run:**

```bash
uv run pytest domain/workforce_risk/tests/test_pdf_report.py -q
```

**Expected output or observable result:** Authorized users can download a PDF derived from the exact JSON version.

**Validation gate:** PDF adds no new source of truth or MVP dependency.

**Commit checkpoint:** `feat: add optional PDF risk reports`

## Task 15.2: Add weekly trend reporting

**Classification:** Stretch

**Objective:** Aggregate immutable daily snapshots into weekly risk trends.

**Why this task is needed:** Weekly reporting was explicitly deferred and must reuse existing data rather than change scoring.

**Dependencies:** MVP acceptance and sufficient daily history.

**Files or directories:**

- Create: `domain/workforce_risk/reports/weekly.py`
- Create: `domain/workforce_risk/tests/test_weekly_report.py`

**Tests to write first:**

- Version-aware aggregation, missing day, recurrence history, environment isolation, and unchanged historical scores.

**Detailed implementation steps:**

- [ ] Aggregate persisted daily results grouped by scoring version.
- [ ] Explain version changes without comparing incompatible raw scores as equivalent.
- [ ] Store immutable weekly JSON using the existing report pipeline.

**Commands to run:**

```bash
uv run pytest domain/workforce_risk/tests/test_weekly_report.py -q
```

**Expected output or observable result:** Weekly trends are reproducible from immutable daily records.

**Validation gate:** Existing daily-report and scoring behavior remains unchanged.

**Commit checkpoint:** `feat: add weekly workforce risk trends`

## Plan self-review checklist

- [x] Every MVP requirement in `docs/spec.md` maps to a task and validation gate.
- [x] Runtime Jira REST remains absent unless an essential MCP gap is proven;
  Task 3.6 permits official REST only for guarded dev setup/seeding/reset/
  cleanup automation.
- [x] Jira mutation begins only in Task 7.1 after proposal safety in Phase 6.
- [x] Task 4.2 implements the mandatory pre-authenticated Supervisor workflow;
  Task 4.4 adds the four selected extra-credit specialists with deterministic
  degraded fallback. MCP servers remain tools and Workforce Risk MCP retains
  deterministic/state ownership.
- [x] Task 3.5 covers deterministic explicit-pattern Jira comment extraction,
  validated attribution, immutable edit/delete lifecycle, normalized-metadata
  retention, privacy display rules, and no signal for ambiguous content.
- [x] Task 3.5 keeps every normalized comment signal report-only: signals may
  trigger refresh/analysis but cannot affect scores, confidence, candidates, or
  proposal evidence; only corroborated structured/authoritative data can score.
- [x] Protected Agent API→Workforce Risk MCP calls use signed short-lived
  internal authorization context; raw manager API keys never reach MCP, agents,
  or domain tool arguments.
- [x] Tasks 3.2 and 6.2 reject missing, malformed, unknown, expired, revoked,
  wrong-role, cross-environment, and wrong-project API keys and test raw-key/
  digest exclusion across every named storage, telemetry, prompt, MCP, browser,
  audit, report, and response boundary.
- [x] Tasks 2.5, 4.3, 6.3, and 8.1 implement one FastAPI-served lightweight UI;
  no React/Vite/Node toolchain, frontend container, or frontend workload remains.
- [x] Task 3.6 automatically seeds exactly seven synthetic profiles and Jira
  task data, uses `Workforce Employee ID` for general analysis, retains only two
  real synthetic Jira accounts for the controlled assignee write, and refuses
  production cleanup or mutation.
- [x] Task 3.6 runs scenario progression/evaluation only from a workstation or
  `run-scenario.yml`; Task 11.4 rejects every simulation namespace or in-cluster
  simulator workload, and the agent observes scenario changes only through real
  Rovo MCP reads.
- [x] Unit tests deny network and real credentials; the mandatory Agent
  API→Workforce Risk MCP test uses separate processes and Streamable HTTP and
  asserts the complete deterministic response contract and transport proof.
- [x] Task 11.4 installs add-ons and validates workload manifests without
  deploying the application to production; Task 12.1 deploys dev, Task 12.2
  records production-shaped HPA evidence, and Task 12.3 promotes the exact
  dev-tested digests through protected GitHub Actions approval.
- [x] CI publishes Actions summaries, JUnit-compatible results,
  Codecov/equivalent coverage, and every required retained artifact category.
- [x] The no-manual-AWS boundary and scriptable Jira automation boundary are
  mapped to stakeholder decisions and executable tasks.
- [x] The three named Agent Skills and optional Argo CD adopt/omit path are
  planned only after MVP acceptance.
- [x] Every task has classification, objective, rationale, dependencies, exact paths, tests-first, steps, commands, expected result, gate, and commit.
- [x] All interface names are consistent with the stable-interface section.
- [x] No task uses protected/personal data or conversational approval.
- [x] Dev/prod isolation and `read degraded; write closed` remain explicit.
- [x] Placeholder and vague-step scans pass.

## Execution handoff

Implementation must not start until the specification PR, this plan PR, stakeholder approvals, and Phase 0 validations pass.

After those gates pass, choose one execution mode:

1. **Subagent-Driven (recommended):** use `superpowers:subagent-driven-development`, dispatch one fresh implementation agent per task, and perform specification and quality review after each task.
2. **Inline Execution:** use `superpowers:executing-plans` and execute tasks in reviewed batches with checkpoints.
