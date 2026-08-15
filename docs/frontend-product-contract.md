# Frontend product contract

The complete page/control/API specification is in
[`frontend-functional-requirements.md`](frontend-functional-requirements.md). This document remains
the shorter product rationale and truthfulness policy.

This records what a future interface should expose from the implemented backend. The reference
screenshots are inspiration for information hierarchy only. Their layout, branding, components,
copy, metrics, providers, and feature set must not be copied.

## MVP: one focused voice workspace

The first frontend should be a single responsive workspace, not a large administration suite:

1. A compact readiness strip sourced from `GET /health` and `GET /ready`.
2. One microphone control plus an optional text-input fallback for development.
3. A live transcript area driven by version-1 `stt_partial` WebSocket events.
4. A clear pipeline state label driven by `pipeline_state` events.
5. One authoritative primary result card for `answer` or `error`, plus an adjacent Groq synthesis
   or fixed no-call status card when the backend offers synthesis or the primary has no answer.
6. Exact citations showing passage/chunk identity, cited text, representation coordinate system,
   and dense/sparse scores when present.
7. A visibly different abstain/repeat/deadline state; never style it as a successful answer.
8. An optional collapsed diagnostics drawer containing response timings and evidence agreement.

This is enough for the judged voice flow and makes the important backend behaviour inspectable
without overwhelming the user.

## Truthful data mapping

| UI element | Backend source | Rule |
|---|---|---|
| Process online | `GET /health` | Means process liveness only. |
| Submission ready | `GET /ready` | Show each actual readiness check; never replace `not_ready` with a green badge. |
| Transcript | `stt_partial`, then terminal `payload.transcript` | A partial can be revised and can never authorize the final answer. |
| Answer status | `payload.state`, `payload.guardrail` | Preserve repeat, abstain, deadline, and dependency states. |
| Evidence | `payload.citations` | Display exact returned spans; do not manufacture titles or confidence. |
| Latency | `payload.timings_ms` | Label the scope. P100 comes only from a qualifying report, not one request. |
| Synthesis availability | `payload.synthesis` | An offer is redeemed only after the primary result renders. Missing/null never calls synthesis; completed primary results stay single-card, while no-answer outcomes use the fixed status mapping. |
| Synthesis result | `POST /v1/query/synthesis` | Keep status/citations separate; show `total_synthesis`, never merge it into primary latency. |
| Aggregate health | `GET /metrics` | Privacy-safe process aggregates only; this is not query history. |
| Corpus provenance | Manifests or a future read-only endpoint | Never expose/index query, `Answer`, or relevance fields as source text. |

## WebSocket flow

The client sends JSON text frames with a required `version: "1"`:

- `start`: request ID, `pcm_s16le`, 16 kHz, and a language hint or `unknown`;
- ordered `audio_chunk`: monotonic sequence and base64 PCM;
- `end_of_stream`: starts the primary server latency clock.

The server returns typed `stt_partial`, `pipeline_state`, `answer`, or `error` events. The client
must stop recording on its own duration cap, send `end_of_stream`, handle reconnect as a new
session, and include the configured bearer token. Audio and transcripts are not persisted by
default.

An eligible completed answer may carry an opaque, short-lived synthesis offer. The client first
renders the primary Evidence answer, then posts only the primary request ID and that token to
`/v1/query/synthesis`. The secondary Groq card is adjacent on wide layouts and stacked after
Evidence on narrow layouts. Its
`completed`, `abstained`, `timed_out`, `unavailable`, or `grounding_failed` status cannot alter the
primary result. Non-completed primary states, including abstention and deadline fallback, never
request Groq synthesis.

A primary evidence abstention with no answer/offer/result still renders the Groq-branded card with
the title/status `Out of context` and the explanation `Groq was not invoked because no verified
corpus evidence was available.` Repeat, unsafe/block, dependency, deadline, and failed outcomes use
`Not generated` with outcome-specific copy. These are frontend-authored statuses, not Groq output;
they show no model badge or generated timing and never call the synthesis endpoint or Groq.

When this opt-in feature is enabled and requested, the backend sends the final
question/transcript and selected evidence to Groq. Raw audio, partial transcripts, and credentials
are excluded. This third-party processing must be disclosed to the operator/user; the Groq key
remains backend-only.

## Features intentionally excluded from the MVP

- No copied dashboard/sidebar or visual system from the references.
- No Gemini, TTS, cross-encoder, BM25, 3072-dimensional embedding, or badges for unused providers:
  those are not this backend's implemented stack. The Groq label appears only on the implemented
  optional synthesis card.
- No fabricated retrieval accuracy, confidence, latency, corpus count, or "all systems online"
  state. Empty or unmeasured values must say `Not measured`.
- No query-history screen until there is an explicit consent, retention, deletion, and redaction
  design. The backend intentionally retains no raw queries, transcripts, or audio in metrics.
- No browser corpus ingestion, reindex button, threshold sliders, prompt editor, or production
  settings panel. Builds and frozen calibration are provenance-bound CLI workflows.
- No arbitrary chunk-strategy selector in the judged path. The Tide Router owns routing;
  comparisons belong in generated evaluation reports.

## Latency presentation

The main result view emphasizes five measured sequential stages: input safety, hybrid retrieval,
evidence selection, extractive answer assembly, and grounding verification. It may show their
per-request subtotal only when all five measurements exist. The canonical full
`total_after_final_audio` measurement remains visible as a secondary value and links to the Evidence
page. Optional Groq synthesis is timed separately and never contributes to the primary subtotal.

The Evidence page owns detailed overall and per-stage percentiles. Current-process `/metrics` values
must be labelled operational, mixed text/voice, reset-on-restart, and non-qualifying. Artifact-backed
retrieval and voice benchmark cards remain separate, including explicit missing/non-qualifying
states.

## Useful second phase

After the voice workspace is stable, add a read-only engineering/evidence view that loads sanitized
JSON reports and manifests. It may show chunk counts by the five real strategies, Recall/MRR/nDCG,
P50/P70/P95/P100=max, timing coverage, guardrail confusion counts, and readiness provenance. Every
card must include sample count and qualification status. Development smoke data must be visibly
labelled non-qualifying.

## Visual direction

Use a distinct, restrained visual system with strong Indic-script legibility, keyboard operation,
screen-reader labels, visible focus, high contrast, and reduced-motion support. Prioritize the
microphone, transcript, terminal decision, and citations. Secondary engineering details should be
collapsed or placed in the later evidence view.
