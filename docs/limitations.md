# Known limitations and open acceptance gaps

## Current local evidence boundary

- Docker Desktop and pinned Qdrant 1.19.0 are available. The active collection is green with
  112,114 points, and live dense/sparse readiness plus the 500-query held-out retrieval path have
  been exercised.
- A local Sarvam key and strict credentialed realtime smoke artifact exist. This proves a successful
  provider session begin/final/end, but it is not the required 100/300-request full voice benchmark.
- The first cold MSMARCO-XI Hindi validation row is slow because the physical file contains one
  giant nested Parquet row group. A pinned 20-row live audit is retained; despite the completed
  10,005-document validation corpus, that profiler sample itself is only a plumbing/schema smoke
  and is not statistically representative.
- The exact pinned E5 revision is cached and built into the 10,005-document, 112,114-vector server
  index. Direct retrieval averages about 305 ms and P95 about 373 ms on the current CPU, so the
  under-200-ms final-audio target still requires measured speculative overlap/fallback evidence.

## Evidence still required for submission

- Corpus scaling comparison across at least two independently built sizes; only the qualifying
  10,005-document baseline exists today.
- At least four measured chunk/retrieval ablations and a data-backed default selection.
- Reference versus ONNX/int8 embedding quality/latency comparison; quantization is not enabled by
  assumption.
- At least 100, target 300, distinct real voice requests with Hindi/English/code-mixed and
  clean/noisy groups, including a target of 60 human recordings.
- Raw voice latency with P50/P70/P95/P100=max, warm/cold separation, concurrency 1, and coverage.
- Active-pipeline supported/contradiction guardrail cases. The current live-ready report is 13/13
  and includes active unsupported evidence, but is intentionally nonqualifying without the other
  two scopes.
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
- Optional Groq `openai/gpt-oss-20b` synthesis is a post-primary fluent rendering, not an
  alternative source of truth. It is disabled by default, is not called for abstentions or other
  non-completed outcomes, and may independently time out, become unavailable, or fail grounding
  while the primary extractive result remains usable.
- Enabling and requesting Groq synthesis discloses the final question/transcript and selected
  evidence to a third-party processor. It does not disclose raw audio, partial transcripts,
  credentials, or unrelated corpus passages. Operators must separately review and disclose Groq's
  applicable retention, regional, privacy, and contractual terms before enabling the feature.
- No qualifying aggregate Groq latency or generation-quality benchmark is currently claimed.
  `total_synthesis` is a per-request post-primary duration and must not be mixed with the qualifying
  voice timer or presented as a percentile.
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

Create a consented, de-identified voice manifest with at least 100 distinct recordings (target
300, including the required language/noise/length/human slices), then run the cold integrity capture
and warm primary benchmark against the current live backend. In parallel, build one larger nested
corpus/collection and use `compare_corpus_sizes.py` before selecting a production corpus size.
