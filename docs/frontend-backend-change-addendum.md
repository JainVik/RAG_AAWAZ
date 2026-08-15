# Frontend requirements addendum

This file contains only the frontend corrections and additions caused by the latest backend,
dataset, retrieval, calibration, guardrail, and evaluation work. It supplements
`frontend-product-contract.md` and `frontend-functional-requirements.md`; it does not replace them.

The frontend remains a two-page application:

1. Voice RAG Workspace (`/ask`)
2. Evaluation & System Evidence (`/evidence`)

No additional page is required for these changes.

## Corrections to existing requirements

### Readiness terminology

- Render `GET /ready` as **Backend operationally ready**, not **Submission ready** or **All final
  benchmarks passed**.
- Keep process liveness, backend operational readiness, and evaluation qualification as three
  separate states.
- A healthy Qdrant collection, valid index, frozen thresholds, and verified Sarvam smoke prove that
  the backend can serve requests. They do not prove that voice latency or every guardrail benchmark
  is qualifying.
- A global green status may mean operationally ready only when every required `/ready` check passes.
  It must not imply overall benchmark acceptance.

### Language selector and API enum

- `Auto` remains the default language hint.
- The complete backend language enum is:
  `as`, `bn`, `gu`, `hi`, `en`, `kn`, `ml`, `mr`, `ne`, `or`, `pa`, `sa`, `ta`, `te`, `ur`,
  `hi-en`, and `unknown`.
- The structured registry covers Assamese, Bengali, Gujarati, Hindi, English, Kannada, Malayalam,
  Marathi, Nepali, Odia, Punjabi, Sanskrit, Tamil, Telugu, Urdu, and Hindi-English code-mixed input.
- The current built and qualifying retrieval corpus is Hindi/English aligned. Hindi and English may
  be presented as validated corpus languages.
- Other accepted languages must be labelled **Not benchmarked** or **Experimental**, or remain
  disabled until a matching corpus/index and qualifying evaluation exist. Acceptance by the API is
  not equivalent to production-validated RAG support.
- Hindi-English code mixing continues through `Auto`; it does not require a separate primary
  selector option.
- Language/VAD confidence must never be displayed as speech-recognition confidence. When recognition
  confidence is absent, render **Recognition confidence unavailable**.

### Technology and feature labels

The frontend must use the implemented stack and must not repeat labels from the reference
screenshots:

- Dense model: `intfloat/multilingual-e5-small`
- Dense dimension: 384
- Dense distance: cosine
- Sparse retrieval: character n-grams, not BM25
- Vector database: Qdrant
- Speech-to-text: Sarvam `saaras:v3-realtime`, not Saarika v2
- Answer generation: extractive by default, with optional configured local generation
- No Gemini provider label
- No 3072-dimensional embedding label
- No cross-encoder/reranker label
- No TTS stage or synthesized-answer control

### Chunk-strategy labels

Only these five actual representations may appear:

- Atomic
- Sentence window
- Semantic section
- Parent-child
- Bilingual paired

Do not substitute the screenshot strategies such as recursive, metadata-aware, sliding-window,
overlap-aware, or fixed-size chunking. Do not show invented per-strategy accuracy or an interactive
strategy selector. Runtime routing is automatic.

### Latency claims

- Label retrieval-evaluation latency as **Direct retrieval evaluation latency**.
- Never present direct retrieval latency as post-final-audio voice latency.
- Do not show `128 ms`, `<200 ms achieved`, an SLA-compliant badge, or any aggregate voice
  percentile until a qualifying real-provider voice report supplies it.
- A single request timing must never be rendered as P50, P70, P95, P99, or P100.
- Every aggregate latency display needs its measurement scope, sample count, timing coverage, and
  qualification state.

### Guardrail claims

- The current live-ready report may be described as **13/13 observed cases correct** only when loaded
  from the sanitized report.
- It must simultaneously be labelled **Non-qualifying** because required active supported-query and
  live-corpus contradiction evidence is incomplete.
- Do not reduce this result to **Guardrails 100% passed** or use it as a global success badge.

## Additions to the Evaluation & System Evidence page

### Dataset audit section

Add a read-only dataset audit group containing fields supplied by a sanitized audit artifact:

- dataset ID and pinned revision;
- source split and target language;
- audited row count and candidate-passage count;
- schema-match status;
- malformed-row and duplicate-query counts;
- selected-passage ratio;
- query-type distribution;
- artifact identity and audit scope.

The current 20-row Hindi validation audit must be labelled **Live sample audit** or **Smoke audit**,
not a full-dataset certification. Its values must be loaded from evidence and not hardcoded.

### Retrieval evaluation details

The retrieval group additionally shows:

- Recall@1, Recall@5, Recall@10, MRR@10, and nDCG@10;
- evaluated query count;
- failure count and completion coverage;
- held-out split verification;
- corpus/index/model/router/threshold provenance verification;
- direct-retrieval P50, P70, P95, and max only when present in the report;
- a visible distinction between quality metrics and latency metrics.

The present qualifying artifact contains 500 held-out queries with zero execution failures and full
completion. Current metric values are evidence data, not component constants.

### Corpus and index facts

The evidence view supports these manifest-backed fields:

- document count;
- evaluation-fixture count;
- indexed point/chunk count;
- Qdrant collection status and schema status;
- dense model, revision, dimension, and distance;
- sparse representation and version;
- enabled representation flags;
- corpus and index build IDs;
- manifest/checksum verification.

The current baseline contains 10,005 documents and 112,114 indexed points/chunks. These values must
come from the evidence response and must not be hardcoded into the layout.

### Corpus-scaling evidence

Add a read-only corpus-scaling group with these states:

- `not_measured`
- `partial`
- `qualifying`
- `invalid`

When several independently built and qualifying corpora are available, it may compare corpus size,
collection identity, quality, latency, index bytes, and build duration. Until then, show the
10,005-document index as the available baseline and **Corpus-size recommendation pending**.

Do not recommend or fabricate 25k, 50k, or 100k results. The comparison workflow is a backend CLI
workflow and must not become a browser button.

### Guardrail evidence details

Show:

- qualification status;
- sample count;
- execution scope per category;
- passed and failed categories;
- execution-failure count;
- explicit failed qualification checks;
- artifact identity.

Observed correctness and qualification must be displayed separately.

### Voice latency pending state

Until the required real-provider benchmark exists, render:

> Qualifying voice latency run pending

The pending state may explain that the final run requires the prescribed sample count and coverage
across human/synthetic audio, supported language mixes, noise conditions, duration classes, cold and
warm operation, transcript matching, completed/evidence responses, canonical stage timing coverage,
and zero request failures.

Do not expose local audio filenames, absolute paths, transcripts from private recordings, or API
credentials.

### Operational readiness versus benchmark qualification

The evidence page must render two separate summaries:

1. **Operational readiness** — based on `/health` and `/ready`, including Qdrant, index/model,
   threshold binding, Sarvam credentialed smoke, runtime identity, and deadline configuration.
2. **Evaluation qualification** — based independently on retrieval, guardrail, voice latency,
   ablation, dataset audit, and corpus-scaling artifacts.

An operationally ready system may legitimately contain pending or non-qualifying evaluation groups.

## Addition to the sanitized evidence endpoint

Extend the planned `GET /v1/evidence/summary` contract with two optional top-level groups:

```text
dataset_audit
corpus_scaling
```

Every evidence group, including these additions, must include when applicable:

- `status`;
- `qualifying`;
- `sample_count`;
- `source_artifact_sha256`;
- `failed_checks`;
- measurement scope/provenance.

Missing or invalid artifacts return `not_measured` or `invalid`; the frontend must never replace
them with sample values. The endpoint must expose only allowlisted summaries and must exclude raw
queries, answers, transcripts, audio paths, absolute filesystem paths, secrets, and arbitrary report
contents.

## Changes that do not require frontend controls

The following backend improvements require evidence labels or metadata at most; they do not require
new interactive frontend controls:

- expanded dataset profiling;
- deterministic development/final fixture partitioning;
- frozen-threshold provenance and integrity validation;
- Qdrant collection/schema/checksum validation;
- corpus-size comparison CLI;
- Colab/cloud build workflow;
- index build and calibration commands;
- voice benchmark runner;
- separate-collection ablation workflow.

These remain backend, build, or evaluation operations. The browser only displays their sanitized
results.
