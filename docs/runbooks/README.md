# Workforce platform operational runbooks

These runbooks handle platform-health alerts only. Employee and project risk
alerts stay in the manager inbox and email workflow. Every response begins by
confirming the environment and correlation references in protected logs. Never
paste credentials, raw Jira content, employee details, or JWTs into an incident.

Runbooks are linked from Prometheus alert rules and are intended to be published
at the configured authenticated internal runbook URL during deployment.
