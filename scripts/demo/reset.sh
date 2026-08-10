#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SCENARIO="${ROOT_DIR}/tests/fixtures/scenarios/seven_employee_team.json"

"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/jira/reset_dev.py" \
  --scenario "${SCENARIO}" --live-mcp
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/jira/verify_seed.py" \
  --scenario "${SCENARIO}" --live-mcp

echo "Jira scenario reset to balanced."
echo "Open: https://gnaiem686.atlassian.net/issues/?jql=project%20%3D%20WRD%20AND%20labels%20%3D%20%22workforce-scenario%3Aseven-person%3Av1%22"

