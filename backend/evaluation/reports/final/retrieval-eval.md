# Retrieval evaluation

Qualification: **qualifying**

| Queries | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 | Hit coverage | Retrieval completion | Request failures | Configuration failures |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 500 | 0.267 | 0.704333 | 0.841333 | 0.453349 | 0.546468 | 0.846 | 1 | 0 | 0 |

## End-to-end retrieval latency

| Samples | Mean (ms) | P50 (ms) | P70 (ms) | P95 (ms) | P100 (ms) |
| --- | --- | --- | --- | --- | --- |
| 500 | 305.089253 | 291.5212 | 302.3119 | 372.7973 | 627.6572 |

## Per-language metrics

| Language | Queries | Recall@10 | MRR@10 | nDCG@10 |
| --- | --- | --- | --- | --- |
| hi | 500 | 0.841333 | 0.453349 | 0.546468 |

## Per-category metrics

| Category | Queries | Recall@10 | MRR@10 | nDCG@10 |
| --- | --- | --- | --- | --- |
| general | 496 | 0.84207 | 0.454233 | 0.547355 |
| short_factual | 4 | 0.75 | 0.34375 | 0.436535 |

Raw row-level results are in the sibling JSONL and CSV artifacts. Hardware, package, corpus, cache, and concurrency metadata are in the JSON summary.
