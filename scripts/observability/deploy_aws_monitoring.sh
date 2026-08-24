#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIRECTORY=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
PROJECT_ROOT=$(cd "$SCRIPT_DIRECTORY/../.." && pwd -P)
EBS_DIRECTORY="$PROJECT_ROOT/infra/kubernetes/observability/ebs"
RENDER_DIRECTORY="$PROJECT_ROOT/artifacts/observability"
RENDERED_VALUES="$RENDER_DIRECTORY/kube-prometheus-stack-values.rendered.yaml"

# shellcheck source=/dev/null
source "$EBS_DIRECTORY/versions.env"

require_value() {
  local name=$1
  if [[ -z "${!name:-}" ]]; then
    echo "Required value is missing: $name" >&2
    exit 2
  fi
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command is missing: $1" >&2
    exit 2
  }
}

require_value "PLATFORM_ALERT_TOPIC_ARN"
require_value "ALERTMANAGER_SNS_ROLE_ARN"
require_value "AWS_REGION"
require_value "KUBE_PROMETHEUS_STACK_CHART_VERSION"
require_command helm
require_command kubectl
require_command sed

[[ "$PLATFORM_ALERT_TOPIC_ARN" =~ ^arn:aws[a-zA-Z-]*:sns:[a-z0-9-]+:[0-9]{12}:[A-Za-z0-9_.-]+$ ]] || {
  echo "PLATFORM_ALERT_TOPIC_ARN is not a valid SNS topic ARN" >&2
  exit 2
}
[[ "$ALERTMANAGER_SNS_ROLE_ARN" =~ ^arn:aws[a-zA-Z-]*:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$ ]] || {
  echo "ALERTMANAGER_SNS_ROLE_ARN is not a valid IAM role ARN" >&2
  exit 2
}
[[ "$AWS_REGION" =~ ^[a-z]{2}-[a-z]+-[0-9]+$ ]] || {
  echo "AWS_REGION is not valid" >&2
  exit 2
}

mkdir -p "$RENDER_DIRECTORY"
sed \
  -e "s|WORKFORCE_PLATFORM_ALERT_TOPIC_ARN|$PLATFORM_ALERT_TOPIC_ARN|g" \
  -e "s|WORKFORCE_ALERTMANAGER_SNS_ROLE_ARN|$ALERTMANAGER_SNS_ROLE_ARN|g" \
  -e "s|WORKFORCE_AWS_REGION|$AWS_REGION|g" \
  "$EBS_DIRECTORY/kube-prometheus-stack-values.yaml" > "$RENDERED_VALUES"

if grep -q 'WORKFORCE_.*_ARN\|WORKFORCE_AWS_REGION' "$RENDERED_VALUES"; then
  echo "Rendered monitoring values contain unresolved placeholders" >&2
  exit 1
fi

kubectl apply -f "$EBS_DIRECTORY/storage-class.yaml"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
helm repo update prometheus-community
helm upgrade --install workforce-monitoring \
  prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --version "$KUBE_PROMETHEUS_STACK_CHART_VERSION" \
  --values "$RENDERED_VALUES" \
  --wait \
  --timeout 15m
kubectl apply -f "$PROJECT_ROOT/infra/kubernetes/observability/prometheus-rules.yaml"
kubectl apply -f "$EBS_DIRECTORY/grafana-public-ingress.yaml"

kubectl -n monitoring rollout status statefulset/alertmanager-workforce-monitoring-kube-alertmanager --timeout=5m
kubectl -n monitoring get pods -l app.kubernetes.io/name=alertmanager
