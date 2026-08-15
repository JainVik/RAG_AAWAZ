# Chunking and index representations

## Why multiple representations exist

MS MARCO passages range from fragments to multi-sentence text. One global token splitter would
either duplicate short passages or cut meaningful sentence boundaries. TideRAG therefore builds
several independently selectable views and chooses among them with a deterministic query router.
Every view must earn its place in retrieval ablation; none is assumed to be the final default.

## Strategies

### Atomic passage

The normalized passage is indexed intact. This is the quality and index-size baseline and is the
preferred view for many descriptive questions.

### Boundary-aware sentence window

Latin `.?!` and Indic `।॥` sentence endings are recognized without rewriting the parent. The
default window is three sentences with one-sentence overlap. Start/end offsets point exactly into
the chosen English or translated parent. A single-sentence passage keeps the same exact span but
is emitted as a distinct sentence-window representation with a strategy-specific chunk ID.

### Semantic section

This view is skipped unless at least four meaningful sentences exist and an offline sentence
embedder is available. Adjacent cosine similarities are calculated once during corpus building;
locally low similarities create boundaries. The current explicit build default caps emitted
sections at 180 words and records that value in the index manifest. It remains an ablation input,
not a data-backed final choice. If semantic embeddings are not configured, the factory emits no
falsely labelled semantic chunks.

### Parent-child

Sentence-window children are indexed for precision. Hits preserve `parent_id`; final fusion
deduplicates by that identity, and request-time late chunking selects a bounded window from the
parent text.

### Bilingual pair

English-only, translated-only, and bounded translated-English pair views all share the canonical
English passage hash. A pair is capped at 800 representation characters by default. Its top-level
span addresses the paired representation, while metadata separately records translated/English
source spans and their spans inside the representation. Which dense text is used by default must
be selected by the ablation report.

### Character n-gram sparse vector

After NFC and whitespace normalization, character 3–5 grams are deterministically hashed with
BLAKE2b. Exact number/date tokens receive their own features. Corpus document frequencies produce
TF-IDF-like weights, hash collisions are summed, indices are sorted, and vectors are L2-normalized.
When enabled, the fitted sparse state is versioned and saved with the index manifest. A
`RAG_ENABLE_SPARSE=false` build instead emits a dense-only manifest and Qdrant schema with no
sparse-state requirement. This view is intended to recover names, code-mixing, spelling
variations, and modest STT errors.

## Feature flags

The five dense representations are independently controlled by
`RAG_ENABLE_ATOMIC_CHUNKS`, `RAG_ENABLE_SENTENCE_WINDOW_CHUNKS`,
`RAG_ENABLE_SEMANTIC_CHUNKS`, `RAG_ENABLE_PARENT_CHILD_CHUNKS`, and
`RAG_ENABLE_BILINGUAL_PAIRED_CHUNKS`. Configuration validation requires at least one of them.
`RAG_ENABLE_SPARSE` controls whether the sparse query branch runs, and
`RAG_ENABLE_LATE_CHUNKING` controls request-time evidence-window selection. `--no-semantic`
remains a build-only override and is intersected with the semantic setting. Index manifests and
evaluation report metadata record the effective flags and enabled dense strategies.

## Required measurements

`build_index.py` records, per representation, chunk count, average characters/words, duplicate
rate, wall build time, and bytes written. `run_ablation.py` adds Recall@1/5/10, MRR@10, nDCG@10,
and retrieval latency. Exact per-configuration Qdrant bytes/build time require independent
collection-build artifacts; the current shared filtered-collection comparison is deliberately
nonqualifying for per-collection behavior. A submitted default is not considered selected until
those reports exist over held-out queries.

## Span invariants

- Monolingual `chunk.text == parent_text[span_start:span_end]`.
- Window overlap occurs only on full sentences.
- All children retain canonical and parent IDs.
- Parent deduplication happens after fusion.
- Query, answer, and label text is absent from every chunk and vector input.

These invariants are enforced in `tests/test_chunk_factory.py` and the corpus leakage tests.
