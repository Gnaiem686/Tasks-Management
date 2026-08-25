# Kubernetes and ingress health

1. Confirm the environment, affected node or deployment, and failure duration.
2. Inspect node readiness and pressure, pod events/restarts, unavailable replicas, and ingress errors.
3. Use the read-only DevOps MCP for evidence; it cannot restart, scale, deploy, or roll back.
4. Perform changes only through the approved cluster administration or release workflow.
5. Resolve after readiness, replica availability, and ingress objectives remain stable.
