# Requirements traceability

Status is evidence-based:

- **Unit-pass**: implementation exists and deterministic local tests pass.
- **Implemented / integration pending**: code exists, but the required live dependency or corpus
  evidence has not run.
- **Blocked**: an exact external prerequisite is absent on this machine.
- **Evaluation pending**: the reproducible runner exists, but no qualifying raw report exists.

A README statement alone never changes a requirement to complete.

## Progress checklist

- [x] Phase 0 — typed skeleton, configuration, APIs, logging, tests, container definitions
- [x] Phase 1 — exact-schema streaming audit and leak-free resumable corpus tooling
- [x] Phase 2 — deterministic canonical corpus contracts and frozen E5/Qdrant baseline code
- [x] Phase 3 — multi-view chunking, sparse encoding, routing, fusion, parent deduplication
- [x] Phase 4 — late evidence selection, extractive generation, citations, guardrails
- [x] Phase 5 — typed deadline harness, retries, cancellation, breakers, telemetry
- [x] Phase 6 — current Sarvam realtime adapter, partial stability, speculative retrieval, voice API
- [ ] Phase 7 — live CPU/Qdrant/Sarvam profiling and evidence-backed optimization
- [ ] Phase 8 — qualifying corpus, retrieval, ablation, voice, and guardrail reports

## Mandatory judging requirements

| Requirement | Status | Implementation | Tests / evidence | Demo step |
|---|---|---|---|---|
| Real spoken question is transcribed by Sarvam on the judged path | **Blocked** — no key/beta smoke | `app/api/voice_ws.py`, `app/stt/sarvam_realtime.py` | Wire/fake tests pass; no `data/sarvam-smoke.json` | Main voice path 1–4 |
| Extensively engineered and compared chunking | **Implemented; comparison pending** | `app/ingestion/chunk_factory.py`, `app/embeddings/sparse_char_ngram.py`, `scripts/run_ablation.py` | Chunk/sparse tests pass; shared filtered-collection ablation is intentionally nonqualifying for per-collection behavior | Show a future separate-collection ablation table before demo |
| Complete final response target under 200 ms from final frame | **Evaluation pending** | `core/deadlines.py`, `api/voice_ws.py`, `harness/orchestrator.py` | Deadline/voice schema tests; no real voice raw run | Point out end marker and completed payload |
| P50, P70, P100=max over distinct queries | **Evaluation pending** | `app/evaluation/metrics.py`, `scripts/run_latency_benchmark.py` with required-stage/counter coverage | Metric tests plus `test_latency_benchmark.py`; total-only timing is rejected | Pre-demo benchmark evidence |
| Proper typed harness with states/deadlines/retry/cancel/breakers/recovery | **Unit-pass** | `domain/models.py`, `harness/*`, Qdrant/Sarvam adapters | `test_harness.py`, `test_circuit_breaker.py`, provider/store failure tests | Reliability evidence 1–3 |
| Guardrails visibly know when not to answer | **Unit-pass; full eval pending** | `guardrails/*`, deadline fallback in orchestrator | `test_guardrails.py`, `test_harness.py`, audio/voice tests | Guardrail cases 1–5 |

## Data and leakage

| Requirement | Status | Implementation | Tests / evidence |
|---|---|---|---|
| Audit actual schema before choosing thresholds | **Live smoke complete; representative audit pending** | `ingestion/dataset_audit.py`, `scripts/inspect_dataset.py` | tests plus `dataset-audit-smoke.{json,md}` from one pinned Hindi validation row |
| Stream explicit pinned MSMARCO-XI files, not 55+ GB download | **Unit-pass** | pinned revision and `hf://.../{hin,mar}*.parquet` mapping | URI/schema tests; official footer/schema verification documented |
| Record nulls, lengths, selection, duplicates, languages, malformed rows | **Live smoke complete; scale pending** | audit accumulator and deterministic JSON/Markdown writer | one-row live report plus audit fixture tests |
| Canonical ID is SHA-256 of normalized English passage | **Unit-pass** | `ingestion/normalize.py`, `deduplicate.py` | corpus/chunk tests |
| Keep all candidates for a selected query row | **Unit-pass** | `ingestion/corpus_writer.py` row-level sampling | `test_corpus_writer.py` |
| Query/Answer/Eng_Answer/labels never enter text, vectors, payload | **Unit-pass** | strict `CorpusDocument`/`Chunk` schemas, whitelist writer, Qdrant full payload | corpus leakage and Qdrant payload tests |
| Evaluation query/relevance/answers are physically separate | **Unit-pass** | `evaluation-fixtures.jsonl` writer | corpus writer tests |
| Sampling and artifacts are deterministic/resumable | **Unit-pass** | fixed seed, sorted IDs, checksums, byte-offset checkpoint | corpus writer recovery/determinism tests |

## Chunking, embeddings, and retrieval

| Requirement | Status | Implementation | Tests / evidence |
|---|---|---|---|
| Atomic passage baseline | **Unit-pass** | `ChunkFactory.atomic` | chunk tests |
| Boundary-aware 2–3 sentence windows with one-sentence overlap | **Unit-pass** | exact Latin/Indic sentence spans and default 3/1 windows | span/overlap test |
| Semantic sections only for meaningful long passages | **Unit-pass; quality pending** | adjacent sentence cosine breaks, min-sentence bypass, cap | semantic bypass/span tests |
| Parent-child retrieval and final parent deduplication | **Unit-pass** | `parent_children`, `parent_dedup.py` | parent dedup test |
| English/Hindi/bounded paired views share semantic identity | **Unit-pass; default pending** | bilingual chunk metadata and canonical IDs | bilingual identity test |
| Character 3–5-grams plus exact number/date features | **Unit-pass** | deterministic BLAKE2b TF-IDF sparse encoder/state | sparse deterministic/round-trip tests |
| Frozen multilingual E5 with query/passage prefixes | **Local live-model smoke; server index pending** | `embeddings/dense.py` | pinned revision cached; real CPU/local-Qdrant smoke report plus unit tests |
| ONNX/int8 only after quality comparison | **Evaluation pending** | backend selection hook; ablation artifact import | no paired reference/quantized report |
| Named dense/sparse Qdrant collection and filter payload indexes | **Local-client smoke; server blocked** | `retrieval/qdrant_store.py` | mock tests plus real qdrant-client in-memory dense/sparse round trip; Docker absent |
| Deterministic complete upsert, resume, metadata/version validation | **Unit-pass; live blocked** | Qdrant store and `scripts/build_index.py` | store/index tests; no live point count |
| Deterministic no-LLM query router | **Unit-pass** | `retrieval/router.py` | English/factual/code-mixed route tests |
| Concurrent dense/sparse retrieval and weighted RRF | **Unit-pass; live blocked** | `retrieval/hybrid.py`, `fusion.py` | deterministic fusion/branch score tests |
| Agreement is exposed and used by answerability | **Unit-pass; calibration pending** | fusion agreement and agreement guard | agreement/gate tests |
| Request-time late chunking over retrieved parents is timed | **Unit-pass** | `retrieval/late_chunking.py`, `EVIDENCE_SELECTED` stage | harness/span tests |

## Voice and speculative retrieval

| Requirement | Status | Implementation | Tests / evidence |
|---|---|---|---|
| Current Saaras realtime endpoint/auth/wire fields are verified | **Unit-pass; real smoke blocked** | beta endpoint, subscription-key header, typed query/events | official docs + Sarvam adapter wire tests |
| No mock substitution in final path | **Unit-pass by configuration** | default services create only real Sarvam provider with key | `/ready` false without key; fake injected only in tests |
| Recognition confidence is not fabricated from provider metadata | **Unit-pass; provider gate validation blocked** | Sarvam language/VAD confidence is kept distinct and `Transcript.confidence=None` | adapter tests; low-confidence gate uses deterministic injected transcripts only |
| PCM validation, silence/short/invalid gates | **Unit-pass** | `guardrails/audio_gate.py`, voice input size/sequence validation | voice/audio tests |
| Partial stability debounce with generation IDs | **Unit-pass** | `stt/stability.py` | stability tests |
| New partial cancels/invalidates stale speculative search | **Unit-pass** | speculative controller cancellation/current-generation check | stale generation tests |
| Similar final may reuse; changed final retrieves immediately | **Unit-pass** | normalized edit threshold and bounded wait | reuse/mismatch tests |
| Final answer never uses a partial alone | **Unit-pass** | orchestrator rejects non-final transcript | harness and stability tests |
| Primary latency starts at backend end-of-stream receipt | **Unit-pass by code; measurement pending** | deadline constructed exactly on validated marker; raw rows retain all server timings | voice API test, `test_latency_benchmark.py`, methodology |

## Generation, guardrails, and reliability

| Requirement | Status | Implementation | Tests / evidence |
|---|---|---|---|
| Required extractive answer uses one/two retrieved sentences | **Unit-pass** | `generation/grounded_generator.py` | exact-grounding/harness tests |
| Exact passage IDs/spans and per-branch scores are cited | **Unit-pass** | `Citation`, Qdrant decoding, late spans | response schema and store tests |
| Every final factual sentence is supported | **Unit-pass for extractive mode** | normalized combined-citation containment | supported/unsupported grounding tests |
| Optional llama never weakens SLA/grounding | **Unit-pass by disabled fallback** | feature placeholder delegates to extractive until measured | no generative SLA claim |
| Silence/invalid/too-short/low-confidence are distinct | **Unit-pass; real low-confidence event blocked** | audio and transcript gates | guardrail/voice injection tests; provider exposes no recognition confidence |
| Safety is narrow and limitations explicit | **Unit-pass** | documented rules | safe/unsafe tests; `docs/guardrails.md` |
| Prompt injection cannot override harness/context | **Unit-pass** | input regex gate; retrieved text never executed | injection test |
| Static corpus refuses current/live questions | **Unit-pass** | English/Hindi freshness patterns | stale query tests |
| Low score/margin/branch disagreement abstains | **Unit-pass; thresholds pending** | answerability/agreement gates | gate tests; no final frozen thresholds artifact |
| Deadline returns verified answer, cited evidence, or abstention | **Unit-pass** | optional cutoff and terminal fallback states | forced deadline schema test |
| Sarvam and Qdrant have bounded retry/breakers | **Unit-pass** | provider retry classification, shared breakers, store wrapper | provider/store/circuit tests |
| Failures never collapse into generic HTTP 500 | **Unit-pass** | structured query responses and WS error events | API/dependency tests |
| Logs/metrics retain no audio, query, transcript, or secret | **Unit-pass by schema; review pending** | log redaction, bounded aggregate recorder | metrics/API tests; manual code review |

## APIs, evaluation, and delivery evidence

| Requirement | Status | Implementation | Tests / evidence |
|---|---|---|---|
| `/health`, `/ready`, text, voice WS, `/metrics` | **Unit-pass** | `app/api/*`, `app/main.py`, `app/services.py` | API and voice contract tests |
| Retrieval Recall@1/5/10, MRR@10, nDCG@10 on >=500 | **Evaluation pending** | evaluation metrics/runner | metric unit tests; no qualifying raw run |
| At least four chunk/retrieval ablations | **Evaluation pending** | ablation runner configurations | shared filtered collection is nonqualifying; separate artifacts prove bytes/build only |
| Voice target 300, minimum 100 distinct requests | **Blocked / evaluation pending** | voice benchmark runner with non-primary cold integrity linkage | no clips/key/run |
| Human/synthetic and clean/noisy groups are labelled | **Evaluation pending** | voice fixture manifest fields/runner | no qualifying fixture manifest |
| Guardrail confusion counts and failures | **Offline smoke 12/12; qualifying eval pending** | guardrail runner/confusion metric | retained `guardrail-eval.{jsonl,csv,json,md}`, explicitly non-qualifying without corpus |
| Hardware/OS/package/model/corpus/Qdrant/cache/concurrency recorded | **Implemented; report pending** | common reporting utility and manifests | runner tests/help; no qualifying report |
| P100 is actual observed maximum; no outlier clipping | **Unit-pass** | nearest-rank metric special-cases 100=max; server stages aggregate separately | telemetry/evaluation and focused latency tests |
| Cold-start evidence cannot inflate primary qualification | **Unit-pass; live evidence pending** | exactly-one-request checks, fresh `/ready` process ID/zero prior voice count, compatibility fingerprint | `test_latency_benchmark.py`; no live cold/warm pair |
| Thresholds freeze on development before final evaluation | **Unit-pass; calibration pending** | `evaluation/thresholds.py`, calibration CLI | rejects final split; round-trip test |
| No model training/fine-tuning exists or is claimed | **Unit-pass by repository audit** | only ingestion/eval/frozen adapters | no train/checkpoint code; README separation |
| Clean-checkout documented commands pass | **Partially verified** | pinned `pyproject`, Compose, Makefile, README | Python tests/lint/types pass; Docker/Make unavailable here |

## Local command evidence

The current checkout has executed these commands successfully on Windows 11, Python 3.12.10,
11th Gen Intel Core i7-1185G7 (4 cores/8 threads), and 31.4 GB RAM:

```text
python -m pytest backend/tests -q
python -m ruff check backend/app backend/tests
python -m mypy backend/app
python -m pip check
```

Additional retained smoke evidence includes a pinned one-row live dataset audit, a deterministic
10-passage leak-free corpus, a 12-case offline guardrail report, and a real pinned-E5 +
qdrant-client local-engine report. Docker/Qdrant-server, real Sarvam, and qualifying evaluation
commands remain intentionally absent until they actually run.
