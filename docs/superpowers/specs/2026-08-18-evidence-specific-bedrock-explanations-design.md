# Evidence-Specific Bedrock Explanations Design

## Problem

Bedrock receives the deterministic score, factors, and evidence references, but its current instructions permit generic answers such as “other factors mitigate the risk.” Such answers are valid but do not explain which work-planning factors support or limit the result.

## Selected approach

Keep deterministic scoring unchanged and enrich the allowlisted model payload with deterministic explanation guidance. The Agent API will derive strongest contributing factors and low- or zero-contribution factors before invoking Bedrock. Bedrock remains responsible only for detailed natural-language explanation, uncertainty, and recommendations.

Prompt-only changes were rejected because they do not make relevant factor groupings explicit. Fully deterministic prose was rejected because managers requested natural Bedrock answers.

## Data flow

The model payload will retain the overall score, level, confidence, scoring version, factor records, missing evidence, and safe evidence references. It will also include:

- `strongest_contributors`: positive-risk factors ordered by deterministic contribution;
- `mitigating_factors`: factors whose low or zero contribution helps explain why total risk remains limited;
- explicit response requirements derived from the manager's question.

The payload may contain factor contribution values for model reasoning, but the manager-facing answer must state only the overall score such as `22/100`. It must not disclose factor contribution points or construct additional numeric scores.

## Bedrock behavior

The system prompt will require a detailed answer that:

1. Directly answers the manager's exact question.
2. States the unchanged overall risk result when relevant.
3. Names the strongest supplied contributors and explains their effect.
4. Names supplied low-impact factors that limit the result when relevant.
5. Identifies missing evidence or uncertainty.
6. Gives a practical first management action.
7. Uses only supplied deterministic evidence and citations.

The answer may vary naturally in structure and wording. It is not forced into fixed headings.

## Validation and fallback

Existing validation continues to reject changed scores, changed risk levels, unknown citations, and invented candidates. Additional validation will reject empty or generic answers that fail to mention any supplied factor when factor evidence exists. Factor recognition will accept the canonical underscore name or its human-readable space-separated form.

Invalid output follows the existing bounded retry policy and circuit breaker. Exhausted attempts use the deterministic fallback. The governing behavior remains `read degraded; write closed`.

## Testing and acceptance

Unit tests will prove:

- factor guidance is derived deterministically and ordered consistently;
- an overdue-task question can explain why total overload risk remains low;
- multiple high-risk contributors are explained;
- missing evidence is represented;
- generic output is rejected;
- only the overall score may appear in manager-facing prose;
- score, risk-level, citation, candidate, retry, and fallback safety remain intact.

Acceptance requires a live Employee 3 question to return a Bedrock answer that names actual contributors and limiting factors instead of referring vaguely to “other factors.”
