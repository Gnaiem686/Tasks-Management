# Jira integration circuit open

1. Confirm the circuit belongs to the affected environment and Jira dependency.
2. Inspect authentication, latency, rate-limit, schema, and transport diagnostics.
3. Keep read responses explicitly degraded where confidence permits.
4. Keep proposal creation, approval, and execution closed until required evidence is current.
5. Restore service credentials through the secret-management process if required.
6. Resolve only after bounded probes succeed; never force the circuit closed around authentication failures.
