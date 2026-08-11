# Agent API server failures

1. Exclude expected 4xx responses and inspect the server/dependency outcome series.
2. Follow protected logs and traces using a correlation ID.
3. Check process health, dependency readiness, and workflow completion separately.
4. Preserve safe error codes in user responses; do not expose internal diagnostics.
5. Roll back only through the approved immutable-image release process when warranted.
