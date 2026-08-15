# Rejected router v5 experiment

This report is retained for regression evidence only. It used the same 500-query
final fixture as the prior v4 baseline, but Unicode-aware intent routing activated
an unvalidated native-Hindi short-factual policy.

- v4 baseline Recall@10: 84.13%
- rejected v5 Recall@10: 79.63%

The result was inspected and rejected before deployment. Any later evaluation on
the same final fixture is post-hoc regression confirmation, not a fresh untouched
held-out claim.
