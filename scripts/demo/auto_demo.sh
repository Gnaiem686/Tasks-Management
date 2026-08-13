#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SCENARIO="${ROOT_DIR}/tests/fixtures/scenarios/seven_employee_team.json"
STAGE_SECONDS="${DEMO_STAGE_SECONDS:-60}"
JIRA_URL='https://gnaiem686.atlassian.net/issues/?jql=project%20%3D%20WRD'
MANAGER_URL="${AGENT_DEV_URL:-http://127.0.0.1:8000}/"

if [[ ! "${STAGE_SECONDS}" =~ ^[0-9]+$ ]]; then
  echo "DEMO_STAGE_SECONDS must be a non-negative integer" >&2
  exit 2
fi

trap 'echo; echo "Demo stopped. Jira retains the last completed stage."; exit 130' INT TERM

"${ROOT_DIR}/scripts/demo/readiness.sh"
"${ROOT_DIR}/scripts/demo/reset.sh"

echo "Stage complete: balanced"
echo "Jira: ${JIRA_URL}"
echo "Manager UI: ${MANAGER_URL}"

for stage in stalled blocked critical intervention recovery; do
  sleep "${STAGE_SECONDS}"
  "${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/jira/advance_scenario.py" \
    --scenario "${SCENARIO}" --live-mcp --step "${stage}"
  "${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/jira/verify_seed.py" \
    --scenario "${SCENARIO}" --live-mcp --step "${stage}"
  echo "Stage complete: ${stage}"
  echo "Refresh Jira and the Manager UI to observe the new evidence and risk."
done

echo "Automatic demo completed."
echo "Jira: ${JIRA_URL}"
echo "Manager UI: ${MANAGER_URL}"
