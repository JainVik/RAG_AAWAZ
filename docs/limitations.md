# Known limitations and open acceptance gaps

## Environment blockers on the current machine

- Docker is not installed, so the pinned Qdrant 1.19.0 container, live dense/sparse upsert, schema
  readiness, and query latency have not been exercised locally.
- `SARVAM_API_KEY` is not configured. No real beta realtime handshake, human microphone request,
  recognition result, or credentialed Sarvam smoke artifact exists. The real voice acceptance
  criterion therefore remains blocked.
- The first cold MSMARCO-XI Hindi validation row is slow because the physical file contains one
  giant nested Parquet row group. A pinned one-row live audit and leak-free 10-passage validation
  corpus completed, but that sample is only a plumbing/schema smoke and is not statistically
  representative.
- The exact pinned E5 revision is cached and passed a real CPU + qdrant-client local-engine smoke.
  No 10,000-passage corpus or Qdrant **server** index has yet been built on this checkout.

## Evidence still required for submission

- Held-out retrieval report over at least 500 distinct queries.
- At least four measured chunk/retrieval ablations and a data-backed default selection.
- Reference versus ONNX/int8 embedding quality/latency comparison; quantization is not enabled by
  assumption.
- At least 100, target 300, distinct real voice requests with Hindi/English/code-mixed and
  clean/noisy groups, including a target of 60 human recordings.
- Raw voice latency with P50/P70/P95/P100=max, warm/cold separation, concurrency 1, and coverage.
- Full guardrail confusion matrix including contradictory evidence and forced dependency/deadline
  cases.
- A successful real microphone-to-Sarvam-to-final-harness demo.

## Product limitations

- Human voice fixtures and raw request rows may contain biometric or transcript data. They live in
  a gitignored private directory by default. Collection requires speaker consent, minimal scripted
  content, opaque identifiers, and a deliberate de-identification/release review before sharing.

- The static MSMARCO-derived corpus cannot answer current events, live prices, or office-holder
  questions; the freshness gate intentionally abstains.
- The safety gate is a narrow transparent ruleset, not a comprehensive safety classifier.
- Saaras realtime does not expose transcription confidence. Stability, local audio checks, empty
  finals, and provider errors are used. Its current realtime events supply language/VAD confidence,
  not recognition confidence; the adapter therefore leaves `Transcript.confidence=None` rather
  than substituting either field. The low-recognition-confidence production gate is covered by
  deterministic injected tests only and has not been validated with a credentialed provider event.
- Character hash collisions are deterministic and aggregated but remain possible.
- Extractive mode prioritizes verifiable grounding and latency over fluent synthesis.
- The optional local llama adapter intentionally falls back to extractive mode until a concrete
  quantized model passes grounding and CPU latency measurements.
- Marathi code paths exist, but Marathi is not a supported submission claim until the Hindi/English
  core and benchmarks pass.
- The ablation runner currently measures quality and query latency through one shared collection
  with per-configuration filters. Separately supplied build artifacts substantiate only bytes and
  build time; they do not demonstrate per-collection query behavior. Ablation reports therefore
  remain intentionally nonqualifying until each configuration is built and queried as its own
  measured collection.
- A cold-start latency artifact is an exactly-one-request integrity check, not a primary latency
  result. Even a valid cold compatibility fingerprint cannot satisfy the 100-request minimum or
  replace the warm final report.

## Highest-value next step

Install Docker, build a 10,000-passage Hindi training corpus and a separately held-out validation
fixture/index, then run the 500-query retrieval baseline and freeze development thresholds. Next,
configure a local Sarvam beta credential and record the first end-to-end microphone smoke before
claiming voice readiness or latency.
