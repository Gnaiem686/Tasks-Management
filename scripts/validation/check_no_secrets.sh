#!/usr/bin/env bash
set -euo pipefail

scan_root="${1:-.}"

if [[ ! -d "$scan_root" ]]; then
  echo "Secret scan target is not a directory" >&2
  exit 2
fi

secret_pattern='(?ix)(
  (?:ATLASSIAN|JIRA)[A-Z0-9_]*(?:TOKEN|API_KEY)\s*[:=]\s*
    (?!replace|example|dummy|synthetic|test|<|\$\{)[A-Za-z0-9._-]{20,}
  |\bAKIA[0-9A-Z]{16}\b
  |\bgh[pousr]_[A-Za-z0-9]{30,}\b
  |-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----
)'

mapfile -t matching_files < <(
  rg --files-with-matches --pcre2 --hidden \
    --glob '!.git/**' \
    --glob '!.venv/**' \
    --glob '!.worktrees/**' \
    --glob '!.env.example' \
    --glob '!uv.lock' \
    "$secret_pattern" "$scan_root" || true
)

if (( ${#matching_files[@]} > 0 )); then
  for file in "${matching_files[@]}"; do
    printf 'Possible secret detected in %s\n' "$file" >&2
  done
  exit 1
fi

echo "No possible secrets found"
