# Daily Platform Alert Repeat Design

## Objective

Reduce repeated platform-health email notifications while preserving immediate visibility of newly detected failures.

## Selected behavior

- Alertmanager continues to group alerts by `environment`, `owner`, and `severity`.
- A newly firing alert group is sent immediately after the existing 30-second grouping delay.
- A genuinely new alert added to an existing group may be reported after the existing five-minute group interval.
- An unchanged firing alert group is repeated no more than once every 24 hours.
- Resolved notifications remain enabled.
- `Watchdog` and `InfoInhibitor` remain routed to the null receiver.
- Workforce business-risk alerts remain outside Alertmanager and SNS.

## Implementation boundary

Change only the Alertmanager `repeat_interval` from `4h` to `24h` in the AWS kube-prometheus-stack values. Do not modify the Workforce Risk Manager UI, application services, scoring, Jira integration, Bedrock behavior, or business-risk alerting.

## Failure behavior

Alertmanager retains its existing grouping, retry, and SNS delivery behavior. A failure to send one notification must remain visible through Alertmanager logs and notification failure metrics; the repeat-interval change must not hide new alert groups.

## Verification

- A configuration test asserts `group_wait: 30s`, `group_interval: 5m`, and `repeat_interval: 24h`.
- Existing SNS receiver, IAM identity, null-route, and resolved-notification tests remain green.
- The rendered live Alertmanager configuration is inspected after deployment.
- No controlled failure injection is required because only the repeat schedule changes.
