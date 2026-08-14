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
| Deadline | Absolute monotonic expiration and 170 ms optional cutoff | cited `DEADLINE_FALLBACK` or explicit `DEADLINE_EXCEEDED` |

The safety gate is deliberately conservative and rule-based; it is not described as a complete
content-safety classifier. Thresholds are calibrated on a development split, written to a frozen
artifact with the fixture hash, then loaded unchanged for final evaluation. Code rejects attempts
to freeze from a split named `final`.

The guardrail suite must include supported, unsupported, stale, unsafe, injection, silence,
low-confidence, contradictory-evidence, dependency-failure, and forced-deadline cases. Reports show
a full expected-reason versus observed-reason confusion matrix and representative failures.

