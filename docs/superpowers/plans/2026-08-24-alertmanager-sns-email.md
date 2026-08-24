# Alertmanager SNS Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Prometheus platform-health alerts by email through Alertmanager and Amazon SNS without changing application behavior.

**Architecture:** Terraform provisions an encrypted SNS topic, email subscription, and narrow OIDC IAM role. The kube-prometheus-stack Alertmanager uses its native SNS receiver and a projected Kubernetes service-account token to publish notifications.

**Tech Stack:** Terraform 1.10.5, AWS SNS/IAM/OIDC, kube-prometheus-stack, Prometheus Alertmanager, Kubernetes.

## Global Constraints

- Do not modify Workforce Risk Manager UI, scoring, Jira, LangGraph, or Bedrock logic.
- Do not route workforce business-risk alerts through Alertmanager.
- Send platform alerts only to `gnaiem686@gmail.com`.
- Never commit AWS credentials or tokens.
- The recipient must confirm the AWS SNS email subscription before delivery testing.

---

### Task 1: Provision the platform-alert SNS boundary

**Files:**
- Create: `infra/terraform/environment/platform_alerts.tf`
- Modify: `infra/terraform/environment/variables.tf`
- Modify: `infra/terraform/environment/outputs.tf`
- Test: `tests/infrastructure/test_platform_alerting.py`

**Interfaces:**
- Consumes: the existing Kubernetes OIDC provider and cluster issuer locals.
- Produces: `platform_alert_topic_arn` and `alertmanager_sns_role_arn` Terraform outputs.

- [ ] **Step 1: Write failing infrastructure tests**

Assert that Terraform defines an encrypted SNS topic, confirmed-target email subscription configuration, an OIDC trust restricted to `system:serviceaccount:monitoring:workforce-alertmanager`, and an IAM policy containing only `sns:Publish` to the topic.

- [ ] **Step 2: Verify the test fails**

Run: `uv run pytest tests/infrastructure/test_platform_alerting.py -q`

Expected: FAIL because `platform_alerts.tf` does not exist.

- [ ] **Step 3: Add the minimal Terraform resources**

Create the SNS topic, email subscription, OIDC trust policy, IAM role/policy, variables, and outputs. Keep the endpoint as a validated Terraform variable supplied by CI.

- [ ] **Step 4: Verify tests and Terraform validation**

Run: `uv run pytest tests/infrastructure/test_platform_alerting.py -q`

Run: `terraform -chdir=infra/terraform/environment fmt -check -recursive && terraform -chdir=infra/terraform/environment validate`

Expected: all tests pass and Terraform exits 0.

- [ ] **Step 5: Commit checkpoint**

Run: `git add infra/terraform/environment tests/infrastructure/test_platform_alerting.py && git commit -m "feat: provision platform alert email topic"`

### Task 2: Configure Alertmanager to publish through SNS

**Files:**
- Modify: `infra/kubernetes/observability/ebs/kube-prometheus-stack-values.yaml`
- Create: `scripts/observability/deploy_aws_monitoring.sh`
- Test: `tests/observability/test_alertmanager_sns.py`

**Interfaces:**
- Consumes: Terraform outputs `platform_alert_topic_arn` and `alertmanager_sns_role_arn`.
- Produces: a rendered kube-prometheus-stack release with `workforce-platform-sns` as its Alertmanager receiver.

- [ ] **Step 1: Write failing monitoring tests**

Assert that Alertmanager routes to an SNS receiver, sends resolved events, uses `us-east-1`, projects the OIDC token, and receives only the role/topic values supplied during deployment.

- [ ] **Step 2: Verify the test fails**

Run: `uv run pytest tests/observability/test_alertmanager_sns.py -q`

Expected: FAIL because no SNS receiver is configured.

- [ ] **Step 3: Add the minimal Alertmanager configuration and deployment script**

Configure `sns_configs`, service-account identity, AWS role/token environment, and safe placeholder substitution. Validate required values before running `helm upgrade --install`.

- [ ] **Step 4: Verify monitoring tests**

Run: `uv run pytest tests/observability/test_alertmanager_sns.py tests/observability -q`

Expected: all observability tests pass.

- [ ] **Step 5: Commit checkpoint**

Run: `git add infra/kubernetes/observability/ebs scripts/observability tests/observability && git commit -m "feat: route platform alerts through sns"`

### Task 3: Wire CI variables and deploy

**Files:**
- Modify: `.github/workflows/terraform-plan.yml`
- Modify: `.github/workflows/terraform-apply.yml` only if the reviewed-plan workflow needs the new variable during apply.
- Modify: `.github/workflows/deploy-dev.yml` only to run the monitoring deployment script with Terraform-owned ARNs.

**Interfaces:**
- Consumes: GitHub environment variable `PLATFORM_ALERT_EMAIL` and Terraform outputs.
- Produces: repeatable dev deployment and recorded validation evidence.

- [ ] **Step 1: Add failing workflow-policy assertions**

Extend `tests/infrastructure` to require the non-secret alert email variable and monitoring deployment validation without exposing credentials.

- [ ] **Step 2: Verify failure, then minimally wire workflows**

Run: `uv run pytest tests/infrastructure -q`

Expected before wiring: FAIL on missing variable/deployment step. Expected after wiring: PASS.

- [ ] **Step 3: Run the complete focused verification**

Run: `uv run pytest tests/infrastructure tests/observability -q`

Run: `terraform -chdir=infra/terraform/environment fmt -check -recursive && terraform -chdir=infra/terraform/environment validate`

Expected: zero failures and exit code 0.

- [ ] **Step 4: Merge and deploy through existing gates**

Push a feature branch, merge it into `dev`, run the reviewed environment Terraform plan/apply, and run the monitoring Helm deployment. Do not deploy application image changes because none are required.

- [ ] **Step 5: Confirm and test delivery**

Confirm the SNS subscription using the email from AWS. Fire a controlled test platform alert, verify receipt, remove the test alert, and verify the resolved email. Capture Alertmanager/SNS status without exposing sensitive data.

- [ ] **Step 6: Commit checkpoint**

Run: `git add .github/workflows tests && git commit -m "ci: deploy platform alert notifications"`

