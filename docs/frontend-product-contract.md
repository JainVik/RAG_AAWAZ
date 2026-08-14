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
5. One terminal result card for `answer` or `error`.
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

## Features intentionally excluded from the MVP

- No copied dashboard/sidebar or visual system from the references.
- No Gemini, TTS, cross-encoder, BM25, 3072-dimensional embedding, or provider badges: those are
  not this backend's implemented stack.
- No fabricated retrieval accuracy, confidence, latency, corpus count, or "all systems online"
  state. Empty or unmeasured values must say `Not measured`.
- No query-history screen until there is an explicit consent, retention, deletion, and redaction
  design. The backend intentionally retains no raw queries, transcripts, or audio in metrics.
- No browser corpus ingestion, reindex button, threshold sliders, prompt editor, or production
  settings panel. Builds and frozen calibration are provenance-bound CLI workflows.
- No arbitrary chunk-strategy selector in the judged path. The Tide Router owns routing;
  comparisons belong in generated evaluation reports.

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
