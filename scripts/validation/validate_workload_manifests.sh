#!/usr/bin/env bash
set -Eeuo pipefail

for command in kustomize kubeconform; do
  command -v "$command" >/dev/null || { echo "$command is required" >&2; exit 1; }
done

for environment in dev prod; do
  rendered=$(kustomize build "infra/kubernetes/overlays/$environment")
  printf '%s\n' "$rendered" \
    | kubeconform -strict -exit-on-error -ignore-missing-schemas -

  if grep -E 'image:.*:(latest|main|master|dev)([[:space:]]|$)' <<<"$rendered"; then
    echo "mutable image reference detected in $environment" >&2
    exit 1
  fi
  if grep -Ei 'namespace:[[:space:]]*simulation|scenario-controller|jira_seed|kubeconfig' <<<"$rendered"; then
    echo "forbidden in-cluster scenario resource detected" >&2
    exit 1
  fi
done

echo "Both workload overlays passed schema, immutable image, and simulator-boundary checks"
