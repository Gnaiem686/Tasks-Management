#!/usr/bin/env bash
set -Eeuo pipefail

required_versions=(
  CALICO_VERSION INGRESS_VERSION METRICS_SERVER_VERSION
  EXTERNAL_SECRETS_VERSION PROMETHEUS_STACK_VERSION GRAFANA_VERSION
  LOKI_VERSION OTEL_COLLECTOR_VERSION
)
for key in "${required_versions[@]}"; do
  value=${!key:-}
  if [[ -z "$value" || "$value" == *latest* || "$value" == *"*"* ]]; then
    echo "$key must contain an exact reviewed version, never latest or a wildcard" >&2
    exit 1
  fi
done

kubectl rollout status daemonset/calico-node -n kube-system --timeout=5m
kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=5m
kubectl rollout status deployment/metrics-server -n kube-system --timeout=5m
kubectl rollout status deployment/external-secrets -n external-secrets --timeout=5m
kubectl rollout status deployment/prometheus-operator -n monitoring --timeout=5m
kubectl rollout status statefulset/loki -n monitoring --timeout=5m
kubectl rollout status deployment/otel-collector -n monitoring --timeout=5m
kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes >/dev/null

echo "Pinned cluster add-ons are healthy"
