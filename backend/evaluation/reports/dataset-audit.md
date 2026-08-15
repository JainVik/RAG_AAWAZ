# MSMARCO-XI Dataset Audit

- Dataset: `ai4bharat/MSMARCO-XI`
- Pinned revision: `bf5cdc1f26e581e519018e434db14edd1b77602b`
- Sampling is a deterministic bounded stream prefix; it is not a random estimate.

## hi / validation

- Physical file: `validation/hinval.parquet`
- Rows sampled: 20 of at most 20
- Schema status: `matched`
- Unique sampled query IDs: 20
- Duplicate query-ID rows: 0
- Query types: `{"DESCRIPTION": 11, "ENTITY": 1, "NUMERIC": 8}`
- English passage occurrences: 200
- Translated passage occurrences: 200
- Selected/non-selected: 8/192
- Selected ratio: 0.04
- English duplicate rate: 0.0
- Translated duplicate rate: 0.0
- Canonical passages reused across queries: 0

### Field completeness

| Field | Missing | Null | Empty | Missing/null rate |
|---|---:|---:|---:|---:|
| `Answer` | 0 | 0 | 0 | 0.0 |
| `Eng_Answer` | 0 | 0 | 1 | 0.0 |
| `Eng_Query` | 0 | 0 | 0 | 0.0 |
| `meta` | 0 | 0 | 0 | 0.0 |
| `meta.frequency_penalty` | 0 | 0 | 0 | 0.0 |
| `meta.max_tokens` | 0 | 0 | 0 | 0.0 |
| `meta.model_name` | 0 | 0 | 0 | 0.0 |
| `meta.presence_penalty` | 0 | 0 | 0 | 0.0 |
| `meta.temperature` | 0 | 0 | 0 | 0.0 |
| `meta.top_p` | 0 | 0 | 0 | 0.0 |
| `passages` | 0 | 0 | 0 | 0.0 |
| `passages.English_passages` | 0 | 0 | 0 | 0.0 |
| `passages.Translated_passages` | 0 | 0 | 0 | 0.0 |
| `passages.is_selected` | 0 | 0 | 0 | 0.0 |
| `query` | 0 | 0 | 0 | 0.0 |
| `query_id` | 0 | 0 | 0 | 0.0 |
| `query_type` | 0 | 0 | 0 | 0.0 |
| `source_lang` | 0 | 0 | 0 | 0.0 |
| `target_lang` | 0 | 0 | 0 | 0.0 |

### Passage length distributions

Token method: unicode_subword_heuristic_v1: Latin/alphanumeric runs=ceil(chars/4), non-Latin runs=ceil(chars/2), punctuation=1; this is an estimate, not a model tokenizer

#### English passages

| Measure | Count | Min | P50 | P70 | P75 | P90 | P95 | P99 | P100 | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| characters | 200 | 56 | 289 | 318 | 328 | 392 | 473 | 580 | 696 | 289.995 |
| model_token_estimate | 200 | 17 | 84 | 95 | 99 | 120 | 139 | 160 | 202 | 86.67 |
| sentences | 200 | 1 | 3 | 4 | 5 | 6 | 7 | 9 | 11 | 3.675 |
| words | 200 | 12 | 49 | 56 | 59 | 69 | 83 | 103 | 127 | 50.44 |

#### Translated passages

| Measure | Count | Min | P50 | P70 | P75 | P90 | P95 | P99 | P100 | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| characters | 200 | 63 | 285 | 329 | 342 | 415 | 466 | 554 | 762 | 292.265 |
| model_token_estimate | 200 | 41 | 204 | 234 | 240 | 286 | 320 | 392 | 528 | 205.985 |
| sentences | 200 | 1 | 4 | 5 | 5 | 7 | 9 | 12 | 16 | 4.105 |
| words | 200 | 23 | 103 | 119 | 124 | 149 | 166 | 203 | 274 | 105.7 |

#### English queries

| Measure | Count | Min | P50 | P70 | P75 | P90 | P95 | P99 | P100 | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| characters | 20 | 23 | 33 | 40 | 41 | 46 | 51 | 52 | 52 | 35.4 |
| model_token_estimate | 20 | 6 | 9 | 11 | 12 | 13 | 14 | 15 | 15 | 10.1 |
| sentences | 20 | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 2 | 1.05 |
| words | 20 | 4 | 6 | 6 | 7 | 8 | 9 | 9 | 9 | 6.15 |

#### Translated queries

| Measure | Count | Min | P50 | P70 | P75 | P90 | P95 | P99 | P100 | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| characters | 20 | 19 | 37 | 40 | 41 | 49 | 57 | 58 | 58 | 37.05 |
| model_token_estimate | 20 | 14 | 27 | 30 | 31 | 34 | 42 | 43 | 43 | 27.1 |
| sentences | 20 | 1 | 1 | 1 | 1 | 1 | 2 | 4 | 4 | 1.2 |
| words | 20 | 8 | 14 | 16 | 17 | 17 | 21 | 23 | 23 | 14.15 |

#### English answers

| Measure | Count | Min | P50 | P70 | P75 | P90 | P95 | P99 | P100 | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| characters | 19 | 12 | 18 | 18 | 37 | 126 | 196 | 196 | 196 | 40.315789 |
| model_token_estimate | 19 | 4 | 6 | 6 | 12 | 39 | 54 | 54 | 54 | 12.421053 |
| sentences | 19 | 1 | 1 | 1 | 1 | 1 | 2 | 2 | 2 | 1.052632 |
| words | 19 | 3 | 3 | 4 | 6 | 22 | 30 | 30 | 30 | 6.947368 |

#### Translated answers

| Measure | Count | Min | P50 | P70 | P75 | P90 | P95 | P99 | P100 | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| characters | 20 | 20 | 20 | 36 | 41 | 148 | 232 | 7515 | 7515 | 419.1 |
| model_token_estimate | 20 | 14 | 14 | 24 | 25 | 103 | 165 | 5223 | 5223 | 291.8 |
| sentences | 20 | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 2 | 1.05 |
| words | 20 | 7 | 7 | 14 | 14 | 56 | 80 | 2857 | 2857 | 158.45 |

#### Passages per query

| Measure | Count | Min | P50 | P70 | P75 | P90 | P95 | P99 | P100 | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| candidate_passages | 20 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10.0 |

#### Selected passages per query

| Measure | Count | Min | P50 | P70 | P75 | P90 | P95 | P99 | P100 | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| selected_passages | 20 | 0 | 0 | 0 | 1 | 1 | 2 | 2 | 2 | 0.4 |

### Corpus scaling estimates

These are sample extrapolations with explicit heuristic assumptions, not measured Qdrant or embedding benchmarks.

| Target passages | Estimated vectors | Dense bytes | Sparse bytes | Payload bytes | Qdrant bytes | Embedding seconds | Upsert seconds |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10000 | 123800 | 190156800 | 253542400 | 61910250 | 572164330 | 4952.0 | 123.8 |
| 25000 | 309500 | 475392000 | 633856000 | 154775625 | 1430410825 | 12380.0 | 309.5 |
| 50000 | 619000 | 950784000 | 1267712000 | 309551250 | 2860821650 | 24760.0 | 619.0 |
| 100000 | 1238000 | 1901568000 | 2535424000 | 619102500 | 5721643300 | 49520.0 | 1238.0 |

Assumptions:

```json
{
  "dense_value_bytes": 4,
  "dense_vector_size": 384,
  "embedding_vectors_per_second": 25.0,
  "hnsw_multiplier": 1.35,
  "note": "Planning estimates extrapolated from the bounded sample. HNSW, sparse, embedding, and upsert factors are explicit heuristics, not measured results.",
  "sparse_bytes_per_vector": 2048,
  "upsert_points_per_second": 1000.0
}
```

### Translation metadata

```json
{
  "parameter_profiles": [
    {
      "count": 20,
      "settings": {
        "frequency_penalty": 0,
        "max_tokens": 4096,
        "model_name": "ckpt-3epochs-sft-then-400k-kd",
        "presence_penalty": 0,
        "temperature": 0,
        "top_p": 1
      }
    }
  ],
  "source_lang_counts": {
    "eng_Latn": 20
  },
  "source_target_pair_counts": {
    "eng_Latn->hin_Deva": 20
  },
  "target_lang_counts": {
    "hin_Deva": 20
  },
  "translation_model_counts": {
    "ckpt-3epochs-sft-then-400k-kd": 20
  }
}
```

### Malformed or short examples

```json
{
  "example_limit": 20,
  "examples": [],
  "examples_recorded": 0
}
```
