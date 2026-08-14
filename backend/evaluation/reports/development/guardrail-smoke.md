# Guardrail evaluation

Qualification: `non_qualifying_offline_guardrail_smoke`.

This report is a non-qualifying guardrail evaluation; inspect the qualification checks in the JSON artifact.

| Cases | Correct | Accuracy |
| --- | --- | --- |
| 12 | 12 | 1 |

## Confusion matrix

| Expected \ Observed | ALLOW | AUDIO_TOO_SHORT | DEADLINE_EXCEEDED | DEPENDENCY_UNAVAILABLE | LOW_STT_CONFIDENCE | NO_RELEVANT_EVIDENCE | PROMPT_INJECTION | RETRIEVAL_DISAGREEMENT | SILENCE | STALE_CORPUS | UNSAFE_REQUEST |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALLOW | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| AUDIO_TOO_SHORT | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| DEADLINE_EXCEEDED | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| DEPENDENCY_UNAVAILABLE | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| LOW_STT_CONFIDENCE | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| NO_RELEVANT_EVIDENCE | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| PROMPT_INJECTION | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| RETRIEVAL_DISAGREEMENT | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| SILENCE | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| STALE_CORPUS | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| UNSAFE_REQUEST | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |

Rows are expected guardrail reasons; columns are observed reasons. ALLOW is used when no guardrail reason applies.

Raw case results and evidence are in the sibling JSONL and CSV artifacts.
