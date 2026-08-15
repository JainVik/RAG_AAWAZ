# Awaaz TideRAG

Awaaz TideRAG is a backend-first Hindi/English/code-mixed voice RAG system for HH Goa 2026. It
streams microphone audio through Sarvam's current Saaras realtime WebSocket API, starts
speculative retrieval from stable partial transcripts, performs parallel dense and character
n-gram sparse retrieval in Qdrant, and returns an exact cited answer or a structured abstention
before an absolute deadline.

This repository contains implementation, deterministic tests, and local integration evidence. The
pinned Qdrant server holds 112,114 points from 10,005 validation passages, the credentialed Sarvam
realtime smoke is verified, and a zero-failure qualifying 500-query held-out retrieval run is
retained under `backend/evaluation/reports/final/`. It does **not** yet claim the complete
submission benchmark: corpus scaling, separate-collection ablations, and the 100/300-request real
voice latency study remain outstanding. See
[`docs/requirements-traceability.md`](docs/requirements-traceability.md) for the evidence boundary.
The future screen scope and exact backend-to-UI mapping are in
[`docs/frontend-product-contract.md`](docs/frontend-product-contract.md); the supplied screenshots
are reference material only, not a design to reproduce.

## What is distinctive

- Stable, revisable Sarvam partials launch cancellable speculative searches; only the final
  transcript can authorize an answer.
- One canonical English passage hash links aligned Hindi and English text without indexing any
  query, answer, or relevance label.
- Atomic, sentence-window, semantic-section, parent-child, and bilingual dense views coexist with
  deterministic character 3–5-gram sparse vectors.
- A deterministic Tide Router selects strategies from query length, script mixture, question form,
  numbers/dates, and genuine STT confidence only when a provider supplies it.
- Dense/sparse overlap is retained as both ranking evidence and a guardrail signal.
- Late chunking is performed at request time over only a few retrieved parents.
- A typed async harness has explicit states, deadlines, cancellation, bounded retry, circuit
  breakers, stage timings, grounding verification, and distinct failure reasons.

## No training or fine-tuning

This project does not train a model. Corpus cleaning/chunking/embedding is dataset ingestion;
held-out Recall/MRR/nDCG is retrieval evaluation; freezing development-set thresholds is
configuration calibration. Saaras and `multilingual-e5-small` remain pretrained/frozen. There are
no training scripts, checkpoints, learned classifiers, or fine-tuned retrievers/generators.

## Prerequisites

- Python 3.11–3.13 (3.12 is the verified local runtime)
- Docker with Compose for Qdrant 1.19.0
- 32 GB RAM recommended for the target corpus
- A Sarvam API key with beta realtime access for the real voice smoke/demo

Never paste a key into chat or commit it. Copy `.env.example` to `.env` and populate it locally.

## Setup

Linux/macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e "./backend[all]"
cp .env.example .env
docker compose up -d qdrant
make test
```

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\backend[all]"
Copy-Item .env.example .env
docker compose up -d qdrant
Set-Location backend
python -m pytest
```

`make` is only a convenience layer. Every command below has a direct Python equivalent.

Download the exact frozen E5 revision used by configuration before an offline build or demo. This
warms the Hugging Face cache; the runtime still verifies the configured repository and revision:

```bash
hf download intfloat/multilingual-e5-small \
  --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3
# equivalent convenience target
make download-e5
```

## Phase 1: audit the live dataset

MSMARCO-XI's live repository does not match its legacy loader example. The implementation pins
revision `bf5cdc1f26e581e519018e434db14edd1b77602b` and opens explicit three-letter Parquet files.
The live field is `Answer` (singular, capitalized), and `passages` contains parallel
`English_passages`, `Translated_passages`, and `is_selected` arrays.

```bash
make audit-data
# or
cd backend
python scripts/inspect_dataset.py --languages hi --splits train validation --max-rows 500
```

The source files each contain one very large row group. A cold first row can take several minutes
even with a small output batch; the batch bounds memory but cannot change the remote physical
layout. Reports are deterministic JSON and Markdown in `backend/evaluation/reports/`.
For a restartable Google Colab Free version of the audit/corpus/initial-index workflow, see
[docs/colab-offline-workflow.md](docs/colab-offline-workflow.md).

## Phase 2–3: build the corpus and Qdrant index

Start with 10,000 unique passages; increase only after the baseline succeeds:

```bash
cd backend
python scripts/build_corpus.py \
  --language hi --split train --target-unique-passages 10000 --seed 2026
python scripts/build_index.py
```

Corpus artifacts live under `backend/data/corpus/`:

- `corpus.jsonl`: strict passage-only whitelist;
- `evaluation-fixtures.jsonl`: query/answer/relevance data, physically separate;
- `corpus-manifest.json`: provenance, counts, and checksums;
- resumable partial/checkpoint files while a build is in progress.

Index artifacts live under `backend/data/index/`, including deterministic chunk JSONL, resume
checkpoint, index manifest, and a fitted sparse state when sparse retrieval is enabled. Qdrant
receives the configured named vectors plus complete payloads with deterministic IDs. An
incompatible existing collection is rejected, never silently recreated.

## Run the API

```bash
make dev
# or, from backend/
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Endpoints:

- `GET /health`: process liveness only;
- `GET /ready`: frozen model, manifest, Qdrant schema/count, and Sarvam configuration;
- `POST /v1/query/text`: development/evaluation path through the same post-transcription harness;
- `WS /v1/query/voice`: judged audio path;
- `GET /metrics`: aggregate privacy-safe metrics.

Production configuration requires `RAG_API_TOKEN`; send it as an `Authorization: Bearer` token to
both text and voice endpoints. `RAG_VOICE_API_TOKEN` may override it for voice. Keep the process on
loopback behind a TLS reverse proxy that enforces rate/concurrency limits; the application also
bounds query/frame sizes, idle gaps, total audio, and total voice-session wall time.

Text smoke request:

```bash
curl -s http://127.0.0.1:8000/v1/query/text \
  -H 'content-type: application/json' \
  -d '{"query":"गोवा कब राज्य बना?","language":"hi"}'
```

The voice socket uses version `1` JSON events. Start with mono raw signed 16-bit PCM at 16 kHz,
send monotonic base64 `audio_chunk` events, then `end_of_stream`. The latter is the primary latency
start. Server events are `stt_partial`, `pipeline_state`, `answer`, and `error`.

## Tests and evaluation

```bash
make test
make lint
make typecheck
make eval-retrieval
make eval-guardrails
make ablation
make benchmark
```

The runners retain raw rows and generate Markdown under `backend/evaluation/reports/`. Default
submission runs enforce at least 500 held-out retrieval queries and 100 distinct voice requests;
small smoke modes must be explicitly enabled and are labelled non-qualifying. P100 is always the
actual maximum. Coverage is reported beside latency. Voice raw rows preserve the complete server
`timings_ms` object; the summary reports each numeric stage plus speculative-retrieval launched and
reused counters. Failed requests and missing timings remain in the denominator. Qualification
also requires the canonical provider/internal timing fields and complete, consistent binary
speculative counters; a response containing only the total cannot qualify.

Current retained retrieval evidence is qualifying for the active 10,005-document index: 500/500
requests completed with zero failures, Recall@5 `0.7043`, Recall@10 `0.8413`, MRR@10 `0.4533`,
and nDCG@10 `0.5465`. Direct retrieval latency on this CPU is mean `305 ms`, P50 `292 ms`, P95
`373 ms`, and P100 `628 ms`; it is not evidence for the separate post-final-audio `<200 ms` voice
target.

### Strict real-Sarvam prerequisite

The credentialed smoke is an explicit prerequisite, not a test that silently skips. Supply a
headerless mono signed 16-bit little-endian PCM file at 16 kHz and keep the key only in the process
environment:

```bash
export SARVAM_API_KEY='<local secret>'
cd backend
python scripts/run_sarvam_smoke.py \
  --pcm /absolute/path/to/distinct-speech.pcm \
  --output data/sarvam-smoke.json
```

PowerShell uses the same runner after setting `$env:SARVAM_API_KEY` locally. The Make equivalent is
`make sarvam-smoke SARVAM_PCM=evaluation/fixtures/sarvam-smoke.pcm`. A successful artifact must be
present before `/ready` reports Sarvam ready and before the voice benchmark accepts the backend as
real-provider evidence. A fake provider remains limited to deterministic protocol/failure tests.

### Development artifacts versus final evidence

Use clearly named development outputs while iterating. These commands are useful engineering
checks and are deliberately non-qualifying:

```bash
make eval-guardrails-smoke
make benchmark-text-smoke
cd backend
python scripts/run_retrieval_eval.py --limit 20 --allow-small-smoke \
  --output-prefix evaluation/reports/development/retrieval-smoke
```

Final evidence is a separate workflow:

1. Build the validation corpus and its active Qdrant index, deterministically partition query
   content into disjoint development/final fixtures, measure development retrieval signals, and
   freeze thresholds from development data only:

   ```bash
   make build-corpus CORPUS_LANGUAGE=hi CORPUS_SPLIT=validation CORPUS_TARGET_PASSAGES=10000
   make build-index
   make partition-evaluation
   make score-development
   make calibrate-thresholds
   ```

   `partition-evaluation` keeps duplicate normalized query content on the same side, requires all
   500 final rows to carry non-empty relevance labels, and writes a hash-bound partition manifest.
   Partitioned MSMARCO-XI rows are explicitly answerable. The score
   step appends `evaluation/fixtures/development-unanswerable.jsonl`, a development-only set of
   explicit private, secret, live, missing-document, and future-information negatives. It exports
   measured raw-dense similarity/margin/agreement rows; calibration consumes those rows and writes
   the exact frozen-threshold path loaded by the runtime. Start Qdrant before the index, scoring,
   calibration, or evaluation steps. If the generated final partition contains fewer than 500
   distinct queries, increase `CORPUS_TARGET_PASSAGES` and rebuild; the evaluator fails closed.

   Run the final retrieval evaluation only after freezing thresholds:

   ```bash
   make eval-retrieval
   ```

   It uses `data/evaluation/partition/final-fixtures.jsonl`, the source corpus manifest, and the
   partition manifest; it rejects development/final ID or normalized-content overlap and any
   active-index/runtime mismatch.
   After independently building and evaluating a larger corpus in a distinct Qdrant collection,
   compare compatible reports with:

   ```bash
   cd backend
   python scripts/compare_corpus_sizes.py \
     evaluation/reports/final/retrieval-10k.json \
     evaluation/reports/final/retrieval-25k.json
   ```

   The comparison is nonqualifying unless both inputs are qualifying and bind the same final
   fixture/model/router/deadline/cache policy while using different corpus manifests and
   collections.
2. Create the gitignored `backend/evaluation/private/voice-latency.jsonl` with at least 303
   distinct PCM clips:
   three warmups plus the 300-request target. Include explicit distinct expected transcripts,
   Hindi/English/code-mixed, clean/noisy, short/long, and human/synthetic labels (target at least
   60 human recordings).
   Obtain explicit consent from every speaker, remove names and unrelated speech, use opaque clip
   IDs/relative paths, and inspect transcripts before release. Raw JSONL/CSV and audio are ignored
   recursively by default but retained locally for audit. Publish them only after de-identification
   and an intentional consent/release review; sanitized JSON/Markdown summaries remain publishable.
3. Run the credentialed Sarvam smoke above and start the API on `127.0.0.1:8000`.
4. Restart the backend immediately before `make benchmark-cold`. This produces exactly one
   fail-closed cold integrity report and is never the primary qualifying result. The pre-request
   `/ready` capture must expose a fresh process ID/start time and zero prior voice requests.
5. Without changing the fixture, backend/index, deadline, audio chunk/pacing, cache, concurrency,
   or trailing-silence policy, run `make benchmark-final`. The warm report links and verifies the
   cold report's compatibility fingerprint and the same backend process ID; do not restart between
   the cold capture and warm primary run.
6. Run the 500-query retrieval, guardrail, and ablation CLIs against their final fixtures and keep
   every JSONL/CSV/JSON/Markdown bundle.

A qualifying 500-query retrieval artifact is retained on this checkout. Qualifying final voice,
corpus-scaling, guardrail, and separate-collection ablation evidence is still pending. Do not
rename development smoke output as final evidence.

## Documentation

- [Architecture](docs/architecture.md)
- [Chunking](docs/chunking.md)
- [Latency methodology](docs/latency-methodology.md)
- [Guardrails](docs/guardrails.md)
- [Requirements traceability](docs/requirements-traceability.md)
- [Demo script](docs/demo-script.md)
- [Known limitations](docs/limitations.md)
