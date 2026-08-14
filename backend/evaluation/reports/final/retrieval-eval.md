# Retrieval evaluation

Qualification: **qualifying**

| Queries | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 | Hit coverage | Retrieval completion | Request failures | Configuration failures |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 500 | 0.267 | 0.706333 | 0.843333 | 0.453252 | 0.546878 | 0.848 | 1 | 0 | 0 |

## Per-language metrics

| Language | Queries | Recall@10 | MRR@10 | nDCG@10 |
| --- | --- | --- | --- | --- |
| hi | 500 | 0.843333 | 0.453252 | 0.546878 |

## Per-category metrics

| Category | Queries | Recall@10 | MRR@10 | nDCG@10 |
| --- | --- | --- | --- | --- |
| code_mixed | 2 | 0.5 | 0.25 | 0.315465 |
| general | 494 | 0.845479 | 0.454961 | 0.548708 |
| short_factual | 4 | 0.75 | 0.34375 | 0.436535 |

Raw row-level results are in the sibling JSONL and CSV artifacts. Hardware, package, corpus, cache, and concurrency metadata are in the JSON summary.
