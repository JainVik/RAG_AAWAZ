# Local E5 + Qdrant-client smoke

This is a **non-qualifying development smoke**, not a Qdrant server, retrieval-quality, or
submission-latency claim. It used the real pinned `intfloat/multilingual-e5-small` Torch model on
CPU and qdrant-client 1.19.0's in-memory engine over the retained 10-passage live Hindi validation
sample.

| Query view | First relevant rank | Hybrid retrieval | Agreement | Top raw dense similarity |
| --- | ---: | ---: | ---: | ---: |
| English | 1 | 36.109 ms | 0.828 | 0.913 |
| Hindi translation | 1 | 28.022 ms | 0.502 | 0.853 |

Thirty-one atomic-English, atomic-Hindi, and bounded-paired points were embedded and upserted in
2,087.618 ms. The full machine, revision, checksums, raw values, and limitations are in the sibling
JSON artifact. A qualifying result still requires the pinned Qdrant server, at least 500 distinct
held-out queries, frozen development thresholds, zero failures, and retained raw rows.
