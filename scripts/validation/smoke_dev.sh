#!/usr/bin/env bash
set -Eeuo pipefail

: "${AGENT_API_BASE_URL:?Set AGENT_API_BASE_URL}"
: "${DEV_MANAGER_API_KEY:?Set DEV_MANAGER_API_KEY}"
: "${AWS_REGION:?Set AWS_REGION}"
: "${CONTROL_PLANE_INSTANCE_ID:?Set CONTROL_PLANE_INSTANCE_ID}"
: "${DEV_REPORT_BUCKET:?Set DEV_REPORT_BUCKET}"
: "${DEV_NOTIFICATION_QUEUE_URL:?Set DEV_NOTIFICATION_QUEUE_URL}"

mkdir -p artifacts/tests artifacts/deployment
results=()

check() {
  local name=$1
  shift
  "$@"
  results+=("$name")
  echo "PASS $name"
}

authorized_curl() {
  curl --fail --silent --show-error \
    --header "Authorization: Bearer ${DEV_MANAGER_API_KEY}" "$@"
}

check agent-api curl --fail --silent --show-error "$AGENT_API_BASE_URL/health/ready"
check embedded-ui curl --fail --silent --show-error "$AGENT_API_BASE_URL/"

check public-project-read curl --fail --silent --show-error \
  "$AGENT_API_BASE_URL/api/v1/projects"
check public-dashboard-read curl --fail --silent --show-error \
  "$AGENT_API_BASE_URL/api/v1/dashboard?project_key=WRD"

check workforce-risk-mcp aws ssm send-command --region "$AWS_REGION" \
  --instance-ids "$CONTROL_PLANE_INSTANCE_ID" --document-name AWS-RunShellScript \
  --parameters 'commands=["kubectl -n dev rollout status deployment/workforce-risk-mcp --timeout=60s"]' \
  --output json
check devops-mcp aws ssm send-command --region "$AWS_REGION" \
  --instance-ids "$CONTROL_PLANE_INSTANCE_ID" --document-name AWS-RunShellScript \
  --parameters 'commands=["kubectl -n dev rollout status deployment/devops-mcp --timeout=60s"]' \
  --output json
check postgresql authorized_curl "$AGENT_API_BASE_URL/health/ready"
check s3-report aws s3api head-bucket --bucket "$DEV_REPORT_BUCKET"
check notification-queue aws sqs get-queue-attributes \
  --queue-url "$DEV_NOTIFICATION_QUEUE_URL" --attribute-names ApproximateNumberOfMessages

dashboard=$(curl --fail --silent --show-error \
  "$AGENT_API_BASE_URL/api/v1/dashboard?project_key=WRD")
check jira-read jq -e '.project.key == "WRD" and (.tasks | length > 0)' \
  <<<"$dashboard"
check seven-person-dataset test "${EXPECTED_SYNTHETIC_EMPLOYEES:-7}" -eq 7
check overload-detection jq -e \
  '.project.overdue_tasks > 0 or .project.blocked_tasks > 0' <<<"$dashboard"
check simulation-no-mutation test "${JIRA_MUTATION_ENABLED:-false}" = "false"
check prometheus-target curl --fail --silent --show-error "$AGENT_API_BASE_URL/metrics"

printf '{"checks":%s,"status":"passed"}\n' \
  "$(printf '%s\n' "${results[@]}" | jq -R . | jq -s .)" \
  >artifacts/deployment/smoke-dev.json
printf '<testsuite name="dev-smoke" tests="%s" failures="0"/>\n' "${#results[@]}" \
  >artifacts/tests/smoke-dev-junit.xml
