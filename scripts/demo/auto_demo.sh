#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SCENARIO="${ROOT_DIR}/tests/fixtures/scenarios/seven_employee_team.json"
STAGE_SECONDS="${DEMO_STAGE_SECONDS:-60}"
JIRA_URL='https://gnaiem686.atlassian.net/issues/?jql=project%20%3D%20WRD'
MANAGER_URL="${AGENT_DEV_URL:-http://127.0.0.1:8000}/"

run_scan() {
  local stage="$1" response scan_id state
  response=$(curl --fail --silent --show-error \
    --request POST "${AGENT_DEV_URL}/api/v1/scans?project_key=WRD" \
    --header "Authorization: Bearer ${DEV_MANAGER_API_KEY}" \
    --header "Content-Type: application/json" \
    --data "{\"scope\":\"WRD\",\"window\":\"demo-${stage}-$(date -u +%s)\"}")
  scan_id=$(jq -er '.scan_run_id' <<<"${response}")
  for _ in {1..30}; do
    state=$(curl --fail --silent --show-error \
      "${AGENT_DEV_URL}/api/v1/scans/${scan_id}?project_key=WRD" \
      --header "Authorization: Bearer ${DEV_MANAGER_API_KEY}" | jq -er '.state')
    [[ "${state}" =~ ^completed ]] && return 0
    [[ "${state}" == failed ]] && return 1
    sleep 1
  done
  return 1
}

if [[ ! "${STAGE_SECONDS}" =~ ^[0-9]+$ ]]; then
  echo "DEMO_STAGE_SECONDS must be a non-negative integer" >&2
  exit 2
fi

trap 'echo; echo "Demo stopped. Jira retains the last completed stage."; exit 130' INT TERM

"${ROOT_DIR}/scripts/demo/readiness.sh"
"${ROOT_DIR}/scripts/demo/reset.sh"
run_scan balanced

echo "Stage complete: balanced"
echo "Jira: ${JIRA_URL}"
echo "Manager UI: ${MANAGER_URL}"

for stage in stalled blocked critical intervention recovery; do
  sleep "${STAGE_SECONDS}"
  "${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/jira/advance_scenario.py" \
    --scenario "${SCENARIO}" --live-mcp --step "${stage}"
  "${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/jira/verify_seed.py" \
    --scenario "${SCENARIO}" --live-mcp --step "${stage}"
  run_scan "${stage}"
  echo "Stage complete: ${stage}"
  echo "Refresh Jira and the Manager UI to observe the new evidence and risk."
done

echo "Automatic demo completed."
echo "Jira: ${JIRA_URL}"
echo "Manager UI: ${MANAGER_URL}"
