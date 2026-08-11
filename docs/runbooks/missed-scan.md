# Missed scheduled scan

1. Confirm the affected environment and latest `scan_run` state.
2. Check CronJob scheduling, active-job concurrency, pod logs, and Jira read health.
3. Do not block interactive deterministic analysis while the scan is repaired.
4. If evidence is stale, keep stale warnings visible and prohibit proposals.
5. Trigger one authenticated manual scan only after the active-job check passes.
6. Resolve after a completed or explicitly degraded scan restores freshness.
