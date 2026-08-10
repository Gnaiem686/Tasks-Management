#!/usr/bin/env bash
set -euo pipefail

PROJECT_KEY="WRD"
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SCENARIO="${ROOT_DIR}/tests/fixtures/scenarios/seven_employee_team.json"
API_BASE_URL="${AGENT_DEV_URL:-http://127.0.0.1:8000}"
WINDOW="primary-demo-$(date -u +%Y%m%dT%H%M%SZ)"

"${ROOT_DIR}/scripts/demo/readiness.sh"
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/jira/advance_scenario.py" \
  --scenario "${SCENARIO}" --live-mcp --step primary_demo
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/jira/verify_seed.py" \
  --scenario "${SCENARIO}" --live-mcp

response=$(curl --fail --silent --show-error \
  --request POST "${API_BASE_URL}/api/v1/scans?project_key=${PROJECT_KEY}" \
  --header "Authorization: Bearer ${DEV_MANAGER_API_KEY}" \
  --header "Content-Type: application/json" \
  --header "X-Correlation-ID: demo-${WINDOW}" \
  --data "{\"scope\":\"${PROJECT_KEY}\",\"window\":\"${WINDOW}\"}")
scan_id=$(jq -er '.scan_run_id' <<<"${response}")

for _ in {1..20}; do
  state=$(curl --fail --silent --show-error \
    "${API_BASE_URL}/api/v1/scans/${scan_id}?project_key=${PROJECT_KEY}" \
    --header "Authorization: Bearer ${DEV_MANAGER_API_KEY}" | jq -er '.state')
  case "${state}" in
    completed|completed_degraded) break ;;
    failed) echo "Demo scan failed" >&2; exit 1 ;;
  esac
  sleep 1
done

echo "Demo scan ${scan_id}: ${state}"
echo "Jira: https://gnaiem686.atlassian.net/issues/?jql=project%20%3D%20WRD%20AND%20labels%20%3D%20%22workforce-scenario%3Aseven-person%3Av1%22"
echo "Manager UI: ${API_BASE_URL}/"

