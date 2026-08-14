# MSMARCO-XI Dataset Audit

- Dataset: `ai4bharat/MSMARCO-XI`
- Pinned revision: `bf5cdc1f26e581e519018e434db14edd1b77602b`
- Sampling is a deterministic bounded stream prefix; it is not a random estimate.

## hi / validation

- Physical file: `validation/hinval.parquet`
- Rows sampled: 1 of at most 1
- Schema status: `matched`
- Unique sampled query IDs: 1
- English passage occurrences: 10
- Translated passage occurrences: 10
- Selected/non-selected: 1/9
- Selected ratio: 0.1
- English duplicate rate: 0.0
- Translated duplicate rate: 0.0

### Field completeness

| Field | Missing | Null | Empty | Missing/null rate |
|---|---:|---:|---:|---:|
| `Answer` | 0 | 0 | 0 | 0.0 |
| `Eng_Answer` | 0 | 0 | 0 | 0.0 |
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

| Measure | Count | Min | P50 | P70 | P95 | P100 | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| characters | 10 | 83 | 243 | 313 | 432 | 432 | 261.1 |
| model_token_estimate | 10 | 26 | 71 | 92 | 128 | 128 | 77.7 |
| sentences | 10 | 1 | 2 | 3 | 5 | 5 | 2.6 |
| words | 10 | 13 | 37 | 51 | 73 | 73 | 43.6 |

#### Translated passages

| Measure | Count | Min | P50 | P70 | P95 | P100 | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| characters | 10 | 84 | 245 | 285 | 399 | 399 | 260.0 |
| model_token_estimate | 10 | 63 | 174 | 199 | 285 | 285 | 182.4 |
| sentences | 10 | 1 | 2 | 3 | 5 | 5 | 2.4 |
| words | 10 | 33 | 87 | 95 | 149 | 149 | 92.5 |

### Translation metadata

```json
{
  "parameter_profiles": [
    {
      "count": 1,
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
    "eng_Latn": 1
  },
  "target_lang_counts": {
    "hin_Deva": 1
  },
  "translation_model_counts": {
    "ckpt-3epochs-sft-then-400k-kd": 1
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
