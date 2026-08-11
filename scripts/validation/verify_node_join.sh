#!/usr/bin/env bash
set -Eeuo pipefail

: "${AWS_REGION:?Set AWS_REGION}"
: "${JOIN_PARAMETER_NAME:?Set JOIN_PARAMETER_NAME}"

nodes=$(kubectl get nodes -o json)
ready=$(jq '[.items[] | select(any(.status.conditions[]; .type == "Ready" and .status == "True"))] | length' <<<"$nodes")
control_planes=$(jq '[.items[] | select(.metadata.labels["node-role.kubernetes.io/control-plane"] != null)] | length' <<<"$nodes")
workers=$((ready - control_planes))

test "$ready" -eq 3
test "$control_planes" -eq 1
test "$workers" -eq 2

if aws ssm get-parameter --region "$AWS_REGION" --name "$JOIN_PARAMETER_NAME" >/dev/null 2>&1; then
  echo "Join parameter must be deleted after the bootstrap window" >&2
  exit 1
fi

echo "Verified one Ready control-plane node, two Ready worker nodes, and expired join material"
