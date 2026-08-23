# Risk Semantics and Dashboard Correction

## Goal

Make WFD dashboard calculations and Bedrock explanations agree with structured
Jira evidence and authoritative local workforce capacity.

## Decisions

- Visible scored levels are Low, Medium, and High; deterministic Critical is
  presented as High without changing the stored score.
- Missing required evidence is Insufficient data, never employee risk.
- Local WFD demo capacity is authoritative configuration: Mohammad Gnaiem 24h,
  Mohammad 28h, emmpone1 24h, and gnaiem 26h.
- A completed task has zero effective remaining workload. A non-zero raw Jira
  remaining estimate is preserved as a data-quality finding.
- Only the downstream side of `A blocks B` counts as a blocked task. The
  upstream task is recorded as blocking downstream work.
- Normal attention lists exclude completed work. Completed work with stale
  estimates appears only as a data-quality finding.
- The UI says `due within 7 days`, hides Jira account IDs, and distinguishes
  risk from missing-data warnings.
- Bedrock explains the deterministic classification and concrete task facts; it
  cannot strengthen Insufficient data into Low, Medium, or High.

## Validation

Unit tests cover effective remaining work, dependency direction, attention
filtering, local profile loading, visible level mapping, and model-output
validation. The current code runs locally only; no push or AWS deployment is
part of this change.
