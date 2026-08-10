#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SCENARIO="${ROOT_DIR}/tests/fixtures/scenarios/seven_employee_team.json"

"${ROOT_DIR}/scripts/demo/readiness.sh"
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/jira/advance_scenario.py" \
  --scenario "${SCENARIO}" --live-mcp --step backup_demo
echo "Backup scenario applied safely to synthetic WRD data."
