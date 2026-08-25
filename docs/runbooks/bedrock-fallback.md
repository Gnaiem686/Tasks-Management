# Bedrock fallback elevation

1. Confirm deterministic risk endpoints remain healthy and scores are unchanged.
2. Inspect regional Bedrock access, throttling, latency, schema failures, and circuit state.
3. Keep the deterministic fallback explanation active; do not make the API unready solely for Bedrock failure.
4. Confirm prompts and token metrics contain no work-item content or sensitive labels.
5. Resolve after validated structured responses recover within the retry budget.
