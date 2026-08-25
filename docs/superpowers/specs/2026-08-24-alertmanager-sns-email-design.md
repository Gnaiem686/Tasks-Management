# Alertmanager SNS Email Design

## Scope

Send platform-health alerts produced by Prometheus and grouped by Alertmanager to `gnaiem686@gmail.com` through Amazon SNS. This feature does not send workforce business-risk alerts and does not change the Workforce Risk Manager UI, scoring, Jira evidence, LangGraph, or Bedrock behavior.

## Selected architecture

```text
Prometheus alert rule
  -> Alertmanager grouping/inhibition
  -> Amazon SNS topic
  -> confirmed email subscription
  -> gnaiem686@gmail.com
```

Terraform owns one encrypted regional SNS topic, the email subscription, and a least-privilege IAM role that permits only `sns:Publish` to that topic. The self-managed Kubernetes OIDC provider permits only the Alertmanager service account in the `monitoring` namespace to assume that role. Alertmanager uses its native `sns_configs` receiver with AWS SigV4 and the existing grouping and inhibition rules.

## Alert behavior

- Only Prometheus platform-health alerts are routed to SNS.
- Alertmanager groups alerts by `environment`, `owner`, and `severity` and retains the existing repeat interval.
- Both firing and resolved notifications are sent.
- Workforce business-risk alerts remain in the manager inbox and are not routed through SNS.
- The subscription is not active until the recipient clicks the AWS confirmation link.

## Safety and failure behavior

- SNS uses server-side encryption and is not publicly publishable.
- Alertmanager receives no general AWS permissions; it can publish only to the configured topic.
- A failed SNS publish remains visible in Alertmanager logs and metrics. It does not affect the Workforce Risk Manager application.
- No secret is stored in Git. The SNS topic ARN and IAM role ARN are non-secret deployment configuration.
- Alert grouping and inhibition prevent one infrastructure failure from producing excessive duplicate email.

## Validation

- Terraform formatting, validation, and static policy tests must pass.
- Rendered monitoring configuration must contain the SNS receiver, correct region, topic ARN placeholder replacement, and the projected OIDC token.
- Alertmanager configuration validation must pass before deployment.
- After deployment, the SNS subscription must be confirmed.
- A controlled `Watchdog`/test platform alert must reach the target mailbox, followed by a resolved notification when the test alert is removed.

