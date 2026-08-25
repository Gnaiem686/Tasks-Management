# Notification queue backlog

1. Check queue age, visible messages, in-flight messages, worker readiness, and DLQ.
2. Confirm SES health and bounded worker retry behavior.
3. Do not delete messages or purge queues; preserve idempotency and delivery history.
4. Scale or restart only through the approved operational release process.
5. Resolve after queue age returns below the objective and sampled alerts are delivered once.
