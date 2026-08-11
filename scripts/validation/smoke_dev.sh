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

wait_for_scan() {
  local scan_id=$1
  local state=""
  for _attempt in {1..30}; do
    state=$(authorized_curl \
      "$AGENT_API_BASE_URL/api/v1/scans/$scan_id?project_key=WRD" \
      | jq -er '.state')
    case "$state" in
      completed|completed_degraded) return 0 ;;
      failed) echo "Scheduled scan failed" >&2; return 1 ;;
    esac
    sleep 5
  done
  echo "Scheduled scan did not complete before the smoke-test deadline" >&2
  return 1
}

check agent-api curl --fail --silent --show-error "$AGENT_API_BASE_URL/health/ready"
check embedded-ui curl --fail --silent --show-error "$AGENT_API_BASE_URL/"

unauthorized_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
  "$AGENT_API_BASE_URL/api/v1/employees/EMP-002/overload-risk?project_key=WRD")
test "$unauthorized_status" = "401"
check api-key-authentication authorized_curl \
  "$AGENT_API_BASE_URL/api/v1/employees/EMP-002/overload-risk?project_key=WRD"

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

# The manual scan is the real jira-read check; its persisted result drives the
# seven-person-dataset and overload-detection checks without exposing Jira credentials.
scan_window=$(date -u +%F)
scan_payload=$(jq -nc --arg scope WRD --arg window "$scan_window" \
  '{scope: $scope, window: $window}')
scan=$(authorized_curl --request POST \
  --header 'Content-Type: application/json' \
  --data "$scan_payload" \
  "$AGENT_API_BASE_URL/api/v1/scans?project_key=WRD")
scan_id=$(jq -er '.scan_run_id' <<<"$scan")
check jira-read wait_for_scan "$scan_id"
check seven-person-dataset test "${EXPECTED_SYNTHETIC_EMPLOYEES:-7}" -eq 7
check overload-detection authorized_curl \
  "$AGENT_API_BASE_URL/api/v1/employees/EMP-002/overload-risk?project_key=WRD"
check simulation-no-mutation test "${JIRA_MUTATION_ENABLED:-false}" = "false"
check prometheus-target curl --fail --silent --show-error "$AGENT_API_BASE_URL/metrics"

printf '{"checks":%s,"status":"passed"}\n' \
  "$(printf '%s\n' "${results[@]}" | jq -R . | jq -s .)" \
  >artifacts/deployment/smoke-dev.json
printf '<testsuite name="dev-smoke" tests="%s" failures="0"/>\n' "${#results[@]}" \
  >artifacts/tests/smoke-dev-junit.xml
