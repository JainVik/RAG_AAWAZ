# Retrieval evaluation

Qualification: **qualifying**

| Queries | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 | Hit coverage | Retrieval completion | Request failures | Configuration failures |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 500 | 0.245 | 0.647333 | 0.796333 | 0.419519 | 0.508526 | 0.802 | 1 | 0 | 0 |

## End-to-end retrieval latency

| Samples | Mean (ms) | P50 (ms) | P70 (ms) | P95 (ms) | P100 (ms) |
| --- | --- | --- | --- | --- | --- |
| 500 | 287.270836 | 284.357 | 289.5802 | 303.7433 | 497.2792 |

## Per-language metrics

| Language | Queries | Recall@10 | MRR@10 | nDCG@10 |
| --- | --- | --- | --- | --- |
| hi | 500 | 0.796333 | 0.419519 | 0.508526 |

## Per-category metrics

| Category | Queries | Recall@10 | MRR@10 | nDCG@10 |
| --- | --- | --- | --- | --- |
| descriptive | 18 | 0.888889 | 0.538889 | 0.629857 |
| general | 275 | 0.83697 | 0.437286 | 0.532255 |
| short_factual | 207 | 0.7343 | 0.385536 | 0.466452 |

Raw row-level results are in the sibling JSONL and CSV artifacts. Hardware, package, corpus, cache, and concurrency metadata are in the JSON summary.
