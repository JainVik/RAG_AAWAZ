# VANI RAG System Architecture

## Overview & Design Intent

**VANI RAG** (Awaaz TideRAG) is an ultra-low-latency, CPU-first multilingual voice Retrieval-Augmented Generation system. It is designed to deliver deterministic, grounded answers in **sub-15ms RAG latency** across Hindi, English, and Hinglish.

The system uses frozen pretrained representations (`intfloat/multilingual-e5-small` and Sarvam AI Saaras) alongside deterministic orchestration. It does not perform online training, fine-tuning, or unverified black-box generation on the primary critical path.

---

## High-Level Execution Pipeline

```
Browser Microphone (16 kHz PCM AudioWorklet)
  │
  ▼ (WebSocket /v1/query/voice)
Sarvam Saaras Realtime WebSocket Adapter
  │
  ├──► Revisable `transcript.partial` ──► Stability Filter ──► Background Speculative Retrieval
  │
  └──► Authoritative `transcript.final`
        │
        ▼
01. Client Transport & Audio Finalization (~12ms network RTT)
        │
        ▼
02. Input Guardrails & Safety Policy Gate (< 0.1ms)
        ├──► Prompt Injection Classifier
        ├──► Temporal / Out-of-Scope Freshness Gate
        └──► Script & Language Normalization (NFC / Devanagari / Latin)
        │
        ▼
03. Query Embedding Engine (~3.5ms on CPU)
        └──► `query: ` prefixed intfloat/multilingual-e5-small (384-dim dense vector)
        │
        ▼
04. Quantized Qdrant Vector Retrieval (~4.2ms)
        └──► INT8 Scalar Quantization in RAM (`always_ram: true`, AVX-512 / AVX2 SIMD)
        │
        ▼
05. In-Memory Lexical Sparse Search & Hybrid RRF (~0.9ms)
        ├──► Character 3–5 grams + exact numeric/date token match
        └──► Client-side Weighted Reciprocal Rank Fusion (RRF) & parent deduplication
        │
        ▼
06. Dynamic Context Window & Late Chunking (~0.4ms)
        └──► Multi-sentence boundary reconstruction over top-ranked parents
        │
        ▼
07. Deterministic Extractive Answer Generation (~1.1ms)
        └──► Exact verbatim sentence span extraction bounded to ≤ 2 citations
        │
        ▼
08. Cryptographic Provenance & Serialization (< 0.2ms)
        └──► SHA-256 span-offset verification and JSON serialization
        │
        ▼
Primary Grounded Evidence Answer Delivered to Client (< 15ms Core RAG)
        │
        ▼ (Asynchronous & Post-Primary)
Optional Progressive Groq Synthesis (`POST /v1/query/synthesis`)
        └──► Groq `openai/gpt-oss-20b` with strict JSON Schema and max 2 citations
```

---

## 8-Stage Latency Breakdown & Specifications

Every query response returns a microsecond-precision `timings_ms` telemetry map that tracks the exact breakdown:

| Stage ID | Stage Name | Target Budget | Typical Latency | Implementation Details |
| :--- | :--- | :--- | :--- | :--- |
| **01** | `transport_client` | `< 25.0 ms` | **12.0 ms** | Network transport RTT and 16kHz audio serialization. |
| **02** | `input_guarded` | `< 1.0 ms` | **0.08 ms** | Deterministic injection rules, freshness filter, and NFC normalization. |
| **03** | `query_embedded` | `< 8.0 ms` | **3.5 ms** | CPU-optimized PyTorch inference with `multilingual-e5-small`. |
| **04** | `retrieved_dense` | `< 10.0 ms` | **4.2 ms** | Qdrant INT8 scalar-quantized vector distance search with `always_ram: true`. |
| **05** | `retrieved_sparse_rrf`| `< 2.0 ms` | **0.9 ms** | In-memory character n-gram scoring and weighted Reciprocal Rank Fusion. |
| **06** | `context_expanded` | `< 1.5 ms` | **0.4 ms** | Request-time sentence windowing over retrieved parent chunks. |
| **07** | `answered` | `< 5.0 ms` | **1.1 ms** | Deterministic span-cut extraction from top evidence passage. |
| **08** | `verified` | `< 1.0 ms` | **0.12 ms** | SHA-256 cryptographic verification and serialization. |

---

## Key Performance Engineering Techniques

### 1. In-Memory INT8 Scalar Quantization in Qdrant
* Standard FP32 384-dimensional dense vectors require heavy memory bandwidth and CPU cache misses.
* By enabling **INT8 scalar quantization** with `always_ram: true`, vector search executes directly in CPU L3 cache via SIMD (AVX-512 / AVX2), reducing query time from **~45ms to 3.2ms – 5.5ms**.

### 2. Speculative Retrieval on Streaming Speech
* When streaming audio over WebSocket to Sarvam Saaras, stable intermediate partial transcripts trigger speculative search branches in the background.
* If the final transcript matches the speculative query, the pre-computed candidates are re-used instantly (**0ms retrieval overhead**).

### 3. In-Memory Sparse Lexical Search + RRF
* Rather than making separate network calls for BM25, sparse vectors are indexed in memory using character 3–5 grams and exact date/numeric token hashing.
* Dense and sparse ranking streams are fused client-side via Reciprocal Rank Fusion:
  $$\text{Score}(d) = \frac{w_{\text{dense}}}{60 + \text{rank}_{\text{dense}}(d)} + \frac{w_{\text{sparse}}}{60 + \text{rank}_{\text{sparse}}(d)}$$

### 4. Deterministic Extractive Answer Engine
* Voice agents cannot tolerate the 800ms – 2500ms TTFT (Time to First Token) of LLM generation.
* VANI RAG primary answers are extracted directly from the verified source passage, producing a 100% grounded response with exact span citations in **~1.1ms**.

### 5. Progressive Asynchronous Groq Grounded Synthesis
* For users desiring conversational prose, the backend offers an opaque, short-lived synthesis token upon primary answer completion.
* The frontend asynchronously calls `POST /v1/query/synthesis` to trigger Groq `openai/gpt-oss-20b`.
* The prompt is bounded by JSON Schema to output at most **2 citations** with exact support quotes, ensuring strict fidelity without blocking the primary voice audio.

---

## Deployment Topology

```
                      [ User Browser / Mobile Client ]
                                     │
                                     ├──► HTTPS (Static Assets, WebGL Shader)
                                     ▼
                     [ Global Edge CDN / Vercel ]
                     - Live Domain: https://vani-rag.susdev.in
                     - In-Browser Session Cache (sessionStorage)
                     - Zero Backend Polling
                                     │
                                     ├──► WSS / HTTPS (Central India Domestic RTT < 20ms)
                                     ▼
               [ Azure Central India Virtual Machine ]
               - Host: 4.213.226.146.sslip.io (Ubuntu 24.04 LTS)
               - Nginx Reverse Proxy (TLS + HTTP/2 + WebSocket multiplexing)
               - FastAPI Application Server (Uvicorn Systemd Service)
               - Qdrant 1.19.0 Vector Database (INT8 Quantized Collection in RAM)
```
