# Secret-handling rules

Secrets never enter Git, checked-in YAML, browser code, logs, traces, reports,
ordinary Terraform variables, or non-sensitive outputs.

Configuration stores references only. Supported reference schemes are
`secretsmanager://`, `k8s-secret://`, and `env://`; production delivery will use
the approved External Secrets Operator integration.

The following values are secrets:

- Atlassian API tokens and complete authorization headers;
- application API keys and the HMAC pepper used to verify them;
- database credentials;
- AWS credentials other than short-lived workload identity;
- presigned report URLs while valid.

Unit tests run without real credentials and with network access disabled. Test
fixtures use unmistakably synthetic placeholder values.

The Jira `Workforce Employee ID` raw field identifier remains an explicit
deferred validation. Dev and prod reference
`JIRA_WORKFORCE_EMPLOYEE_FIELD_ID`; services must fail closed if the reference
cannot be resolved to a `customfield_<number>` value.
