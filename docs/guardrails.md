# Guardrails

Guardrails return a decision, a specific reason enum, bounded evidence metadata, and a safe user
message. Unsupported, unsafe, stale, and dependency-failed requests are not collapsed into one
generic refusal.

| Gate | Signals | Terminal reason / behavior |
|---|---|---|
| Audio | Empty/quiet PCM, invalid width, less than 250 ms | `SILENCE`, `INVALID_AUDIO`, `AUDIO_TOO_SHORT`; ask to repeat |
| STT | Provider error, empty final; provider recognition confidence only if genuinely supplied | `LOW_STT_CONFIDENCE` or dependency state; never substitute VAD/language confidence |
| Safety | Narrow documented patterns for explicit serious-harm facilitation | `UNSAFE_REQUEST`; limitations remain explicit |
| Injection | Requests to ignore system rules, reveal hidden instructions, or override guardrails | `PROMPT_INJECTION`; evidence remains untrusted data |
| Freshness | Today/current/latest/live prices/current office-holder terms in English/Hindi | `STALE_CORPUS`; static corpus warning/abstention |
| Answerability | Frozen score, margin, and branch-agreement thresholds | `NO_RELEVANT_EVIDENCE` or `RETRIEVAL_DISAGREEMENT` |
| Grounding | Citation on each final extract; normalized answer containment in exact cited spans | `UNSUPPORTED_CLAIM`; fallback or abstain |
| Optional synthesis | Strict output schema, offered evidence IDs, verbatim support quotes, and normalized claim support | Secondary `grounding_failed` or `abstained`; primary result is unchanged |
| Deadline | Absolute monotonic expiration and 170 ms optional cutoff | cited `DEADLINE_FALLBACK` or explicit `DEADLINE_EXCEEDED` |

The safety gate is deliberately conservative and rule-based; it is not described as a complete
content-safety classifier. Thresholds are calibrated on a development split, written to a frozen
artifact with the fixture hash, then loaded unchanged for final evaluation. Code rejects attempts
to freeze from a split named `final`.

For the current 10k index, 518 development rows selected a raw-dense threshold of `0.85302633` but
zero score-margin and branch-agreement minima. That is the measured result of the present negative
set, not proof that those two signals are unnecessary. Add realistic high-similarity hard negatives
and re-freeze before claiming margin/disagreement calibration; do not impose an unmeasured floor
that would collapse answer coverage.

The guardrail suite must include supported, unsupported, stale, unsafe, injection, silence,
low-confidence, contradictory-evidence, dependency-failure, and forced-deadline cases. Reports show
a full expected-reason versus observed-reason confusion matrix and representative failures.
The retained live-ready run is 13/13 correct and includes an active-pipeline unsupported query. It
remains nonqualifying because the bundled fixture lacks successful active-pipeline supported and
contradiction rows; its synthetic conflict case remains a deterministic regression test, not
live-corpus contradiction evidence.

Groq progressive synthesis is never an answerability fallback. The backend creates an offer only
after the primary response reaches `COMPLETED`; abstentions and every other non-completed outcome
make no Groq request. Returned claim evidence IDs and exact support quotes are checked against the
bounded offered passages. Invalid, invented, or unsupported model output fails only the secondary
card and cannot weaken the verified primary answer.

The frontend maps a no-answer evidence abstention to a fixed Groq-branded `Out of context` card;
repeat, unsafe/block, dependency, deadline, and failed outcomes map to `Not generated`. This UI copy
is not provider output and does not weaken the no-offer/no-call rule above.
