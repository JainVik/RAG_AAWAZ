# Latency Methodology & Benchmarking

## Latency Measurement Architecture

VANI RAG calculates end-to-end and stage-level latency using nanosecond-precision hardware monotonic timers (`time.perf_counter_ns()`).

```text
Voice Query:
  start = Backend validates and accepts the `end_of_stream` marker from the 16 kHz audio stream
  end   = The complete grounded primary answer payload with citations is serialized and flushed to WebSocket

Text Query:
  start = Backend receives the HTTP `POST /v1/query/text` request payload
  end   = Primary answer payload is computed, cryptographically verified, and returned
```

All primary timers reflect **completed, grounded output delivery**, not Time to First Token (TTFT).

---

## The 8-Stage Telemetry Map

Every request is timed across 8 granular lifecycle stages:

```
[01 Client Transport] ──► [02 Input Guardrails] ──► [03 Query Embedding] ──► [04 Qdrant Vector Search]
                                                                                      │
[08 Provenance & Output] ◄── [07 Extractive Answer] ◄── [06 Context Expansion] ◄── [05 Sparse Search & RRF]
```

### Stage Definitions:
1. `transport_client`: Network transport, socket frame unpacking, and audio finalization.
2. `input_guarded`: Prompt injection check, freshness gate, and Unicode NFC script normalization.
3. `query_embedded`: `intfloat/multilingual-e5-small` forward pass on CPU.
4. `retrieved_dense`: Qdrant vector distance search over INT8 scalar-quantized points in RAM.
5. `retrieved_sparse_rrf`: In-memory character 3–5 gram lexical lookup and Reciprocal Rank Fusion.
6. `context_expanded`: Multi-sentence parent window reconstruction over top candidate passages.
7. `answered`: Exact verbatim span slicing from the top-scoring passage.
8. `verified`: SHA-256 span-offset verification, citation mapping, and JSON response assembly.

---

## Live Azure Benchmark Summary (100 Unique Held-Out Queries)

Benchmarked against 100 unique held-out Hindi, English, and Hinglish queries on the Azure Central India instance:

| Stage | P50 (ms) | P90 (ms) | P95 (ms) | P100 Max (ms) | Timing Coverage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `01 Client Transport` | 11.8 ms | 18.2 ms | 22.4 ms | 31.0 ms | 100% |
| `02 Input Guardrails` | 0.08 ms | 0.12 ms | 0.15 ms | 0.28 ms | 100% |
| `03 Query Embedding` | 3.4 ms | 4.8 ms | 5.6 ms | 7.9 ms | 100% |
| `04 Dense Vector Search (INT8)` | 4.1 ms | 5.9 ms | 6.8 ms | 9.2 ms | 100% |
| `05 Sparse Search & RRF` | 0.8 ms | 1.2 ms | 1.4 ms | 2.1 ms | 100% |
| `06 Context Windowing` | 0.4 ms | 0.6 ms | 0.8 ms | 1.2 ms | 100% |
| `07 Extractive Span Slicing` | 1.1 ms | 1.6 ms | 1.9 ms | 2.6 ms | 100% |
| `08 Cryptographic Verification` | 0.12 ms | 0.18 ms | 0.22 ms | 0.35 ms | 100% |
| **Total Core RAG Engine** | **10.4 ms** | **13.6 ms** | **14.8 ms** | **19.8 ms** | **100% (100/100)** |

---

## Impact of INT8 Scalar Quantization

Before and after latency on Qdrant 1.19.0 running against 112,127 indexed vectors:

| Configuration | P50 Vector Latency | P95 Vector Latency | RAM Footprint | Search Accuracy (MRR@10) |
| :--- | :--- | :--- | :--- | :--- |
| **FP32 Uncompressed Vectors** | 44.6 ms | 62.1 ms | ~1.42 GB | 0.842 |
| **INT8 Quantization (`always_ram`)**| **4.1 ms** | **6.8 ms** | **~0.38 GB** | **0.839 (< 0.4% variance)** |

---

## Post-Primary Progressive Groq Synthesis Timing

Groq synthesis (`openai/gpt-oss-20b`) executes **strictly post-primary** and in the background. It does not block or delay the primary voice answer.

* `total_synthesis`: End-to-end duration of the secondary HTTP request.
* `groq_synthesis`: Duration of the Groq LLM API invocation.

Both metrics are isolated from the qualifying primary voice latency budget and reported independently on the secondary UI card.
