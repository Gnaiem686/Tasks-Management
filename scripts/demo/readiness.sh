#!/usr/bin/env bash
set -euo pipefail

PROJECT_KEY="WRD"
API_BASE_URL="${AGENT_DEV_URL:-http://127.0.0.1:8000}"

if [[ "${APP_ENVIRONMENT:-dev}" == "prod" ]]; then
  echo "REFUSED: the synthetic Jira demo cannot target production" >&2
  exit 2
fi

for variable in ATLASSIAN_MCP_AUTHORIZATION DEV_MANAGER_API_KEY; do
  if [[ -z "${!variable:-}" ]]; then
    echo "NOT READY: ${variable} is required" >&2
    exit 1
  fi
done

curl --fail --silent --show-error "${API_BASE_URL}/health/ready" >/dev/null
echo "READY: local Agent API"
echo "READY: guarded Jira MCP credentials for ${PROJECT_KEY}"
if [[ -n "${BEDROCK_MODEL_ID:-}" ]]; then
  echo "READY: Bedrock requested with model ${BEDROCK_MODEL_ID}"
else
  echo "DEGRADED: Bedrock is not configured; deterministic fallback will be used"
fi

