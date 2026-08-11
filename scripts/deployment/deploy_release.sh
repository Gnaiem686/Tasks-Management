#!/usr/bin/env bash
set -Eeuo pipefail

: "${RELEASE_DIRECTORY:?Set RELEASE_DIRECTORY}"
: "${RELEASE_NAMESPACE:?Set RELEASE_NAMESPACE}"
export KUBECONFIG=/etc/kubernetes/admin.conf

kubectl create namespace "$RELEASE_NAMESPACE" --dry-run=client -o yaml \
  | kubectl apply --server-side -f -

kubectl apply --server-side --dry-run=server -f "$RELEASE_DIRECTORY/foundation.yaml"
kubectl apply --server-side --dry-run=server -f "$RELEASE_DIRECTORY/migration.yaml"
kubectl apply --server-side --dry-run=server -f "$RELEASE_DIRECTORY/application.yaml"

kubectl apply --server-side -f "$RELEASE_DIRECTORY/foundation.yaml"
kubectl -n "$RELEASE_NAMESPACE" wait \
  --for=condition=Ready externalsecret/application-secrets --timeout=120s

if kubectl -n "$RELEASE_NAMESPACE" get job/database-migration >/dev/null 2>&1; then
  active=$(kubectl -n "$RELEASE_NAMESPACE" get job/database-migration \
    -o jsonpath='{.status.active}')
  if [[ "$active" == "1" ]]; then
    echo "A database migration is already active; refusing concurrent migration" >&2
    exit 1
  fi
  kubectl -n "$RELEASE_NAMESPACE" delete job/database-migration --wait=true
fi

kubectl apply --server-side -f "$RELEASE_DIRECTORY/migration.yaml"
kubectl -n "$RELEASE_NAMESPACE" wait \
  --for=condition=complete job/database-migration --timeout=600s

kubectl apply --server-side -f "$RELEASE_DIRECTORY/application.yaml"
for deployment in agent-api workforce-risk-mcp devops-mcp notification-worker; do
  kubectl -n "$RELEASE_NAMESPACE" rollout status \
    "deployment/$deployment" --timeout=300s
done
