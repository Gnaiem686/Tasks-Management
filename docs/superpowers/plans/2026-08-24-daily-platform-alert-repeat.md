# Daily Platform Alert Repeat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send new grouped platform failures immediately while limiting unchanged-alert reminder emails to one every 24 hours.

**Architecture:** Preserve the existing Alertmanager → SNS email integration and its grouping boundaries. Change only Alertmanager's repeat interval in the AWS kube-prometheus-stack values, protect it with a focused configuration test, then deploy the exact monitoring configuration through the existing SSM/Helm path.

**Tech Stack:** Prometheus Alertmanager, kube-prometheus-stack 88.5.3, Amazon SNS, pytest, Helm, Kubernetes, AWS Systems Manager.

## Global Constraints

- Keep `group_by: [environment, owner, severity]`.
- Keep `group_wait: 30s` so a new alert group is delivered promptly.
- Keep `group_interval: 5m` so genuinely new alerts in an existing group are not hidden for a day.
- Set `repeat_interval: 24h` so unchanged firing groups repeat no more than daily.
- Keep resolved notifications enabled.
- Keep `Watchdog` and `InfoInhibitor` on the null receiver.
- Do not modify the Workforce Risk Manager UI, application services, scoring, Jira integration, Bedrock behavior, or business-risk alerting.

---

### Task 1: Limit unchanged platform-alert reminders to once daily

**Files:**
- Modify: `tests/observability/test_alertmanager_sns.py`
- Modify: `infra/kubernetes/observability/ebs/kube-prometheus-stack-values.yaml`

**Interfaces:**
- Consumes: the existing `alertmanager.config.route` configuration.
- Produces: an Alertmanager route with immediate new-group delivery and a 24-hour repeat interval.

- [ ] **Step 1: Write the failing configuration test**

Extend `test_alertmanager_routes_platform_alerts_to_sns` with exact timing assertions:

```python
route = config["route"]
assert route["group_wait"] == "30s"
assert route["group_interval"] == "5m"
assert route["repeat_interval"] == "24h"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/observability/test_alertmanager_sns.py::test_alertmanager_routes_platform_alerts_to_sns -q
```

Expected: FAIL because the current repeat interval is `4h` rather than `24h`.

- [ ] **Step 3: Make the minimal configuration change**

In `infra/kubernetes/observability/ebs/kube-prometheus-stack-values.yaml`, preserve the existing route and change only:

```yaml
repeat_interval: 24h
```

- [ ] **Step 4: Run focused and regression verification**

Run:

```bash
.venv/bin/pytest tests/infrastructure tests/observability -q
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy domain packages services tests
bash -n scripts/observability/deploy_aws_monitoring.sh
git diff --check
git diff --name-only -- services domain packages
```

Expected: all tests, formatting, lint, typing, and shell checks pass; the final command prints nothing because application logic is unchanged.

- [ ] **Step 5: Commit and merge through the existing dev gate**

Run:

```bash
git add tests/observability/test_alertmanager_sns.py infra/kubernetes/observability/ebs/kube-prometheus-stack-values.yaml
git commit -m "fix: repeat platform alert emails daily"
git push -u origin fix/daily-platform-alert-repeat
gh pr create --base dev --head fix/daily-platform-alert-repeat --title "fix: repeat platform alert emails daily"
gh pr checks --watch
gh pr merge --merge
```

Expected: required CI passes and the PR is merged into `dev`.

- [ ] **Step 6: Deploy and inspect the live configuration**

Package the existing monitoring deployment inputs, send the checksum-verified bundle to control plane `i-000d88bff2eaf32e2` through AWS Systems Manager, and run:

```bash
export KUBECONFIG=/etc/kubernetes/admin.conf
export PLATFORM_ALERT_TOPIC_ARN=arn:aws:sns:us-east-1:228281126655:workforce-risk-platform-alerts
export ALERTMANAGER_SNS_ROLE_ARN=arn:aws:iam::228281126655:role/workforce-risk-alertmanager-sns
export AWS_REGION=us-east-1
bash scripts/observability/deploy_aws_monitoring.sh
```

Then inspect the generated configuration:

```bash
secret_name=$(kubectl -n monitoring get secret -o name | grep alertmanager-workforce-monitoring-kube-alertmanager-generated | head -1 | cut -d/ -f2)
kubectl -n monitoring get secret "$secret_name" -o jsonpath='{.data.alertmanager\.yaml\.gz}' \
  | base64 -d \
  | gzip -dc \
  | grep -E 'group_wait:|group_interval:|repeat_interval:'
```

Expected:

```text
group_wait: 30s
group_interval: 5m
repeat_interval: 24h
```

Also verify the Alertmanager pod is ready and has no new configuration errors:

```bash
kubectl -n monitoring get pod alertmanager-workforce-monitoring-kube-alertmanager-0
kubectl -n monitoring logs alertmanager-workforce-monitoring-kube-alertmanager-0 -c alertmanager --since=5m
```

Expected: pod is `2/2 Running`; logs contain no configuration-loading or notification errors caused by the change.
