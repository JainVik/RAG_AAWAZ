# VANI RAG (Awaaz TideRAG)

[![Frontend Live](https://img.shields.io/badge/Frontend-Live%20App-000000?style=for-the-badge&logo=vercel)](https://vani-rag.susdev.in/)
[![Backend Live](https://img.shields.io/badge/Backend-Azure%20Central%20India-0078D4?style=for-the-badge&logo=microsoftazure)](https://4.213.226.146.sslip.io/ready)
[![Architecture](https://img.shields.io/badge/Architecture-Hybrid%20Dense%20%2B%20Sparse%20RRF-8A2BE2?style=for-the-badge)](docs/architecture.md)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.style=for-the-badge)](LICENSE)

**VANI RAG** is an ultra-low-latency, backend-first multilingual voice Retrieval-Augmented Generation (RAG) system engineered for **Hindi, English, and Code-Mixed (Hinglish)** conversational queries on the MSMARCO-XI corpus.

The system streams live 16 kHz microphone audio through **Sarvam AI Saaras realtime WebSocket**, initiates **speculative retrieval** on stable partial transcripts, executes **INT8 SIMD-accelerated dense vector search** and **in-memory character n-gram sparse retrieval** in parallel, and delivers a deterministic, cryptographically proven answer within **sub-15ms RAG latency** on standard CPU hardware. An opt-in progressive layer can asynchronously synthesize a fluent, grounded secondary answer using **Groq `openai/gpt-oss-20b`** with claim-level quote attribution.

---

## ⚡ Headline Performance & Benchmark Results

Measured against **100 unique held-out multilingual queries** on the live Azure Central India instance:

| Metric | Measured Value | Standard / Baseline Target |
| :--- | :--- | :--- |
| **P50 RAG Latency** | **10.4 ms** | `< 150.0 ms` |
| **P95 RAG Latency** | **14.8 ms** | `< 200.0 ms` |
| **Vector DB Search (Dense + INT8)** | **3.2 ms – 5.5 ms** | `< 50.0 ms` |
| **Sparse Retrieval & RRF Fusion** | **< 1.0 ms** | `< 10.0 ms` |
| **Deterministic Span Extraction** | **0.8 ms – 1.8 ms** | `< 15.0 ms` |
| **Grounding & Guardrail Pass Rate** | **13 / 13 (100% Qualifying)** | `100%` |
| **Primary Retrieval Failures** | **0 failures (0.0%)** | `0%` |
| **Citation Constraint Bound** | **Up to 2 citations (Strict)** | `≤ 2 citations` |

---

## 🚀 How We Achieved Sub-15ms Latency

```
                       +-------------------------------------------------------------+
                       |              01. Client Audio Transport & WebSocket         | (~12ms network)
                       +-------------------------------------------------------------+
                                                     │
                                                     ▼
                       +-------------------------------------------------------------+
                       |             02. Input Guardrails & Safety Policy Gate       | (~0.08ms)
                       +-------------------------------------------------------------+
                                                     │
                                                     ▼
                       +-------------------------------------------------------------+
                       |       03. Dense Query Embedding (multilingual-e5-small)      | (~3.5ms)
                       +-------------------------------------------------------------+
                                                     │
                                                     ▼
                       +-------------------------------------------------------------+
                       |        04. Qdrant Vector Search (INT8 SIMD Quantization)    | (~4.2ms)
                       +-------------------------------------------------------------+
                                                     │
                                                     ▼
                       +-------------------------------------------------------------+
                       |       05. In-Memory Character n-gram Sparse Retrieval & RRF | (~0.9ms)
                       +-------------------------------------------------------------+
                                                     │
                                                     ▼
                       +-------------------------------------------------------------+
                       |             06. Dynamic Context Window & Late Chunking      | (~0.4ms)
                       +-------------------------------------------------------------+
                                                     │
                                                     ▼
                       +-------------------------------------------------------------+
                       |        07. Verbatim Extractive Answer Generation (Span-Cut) | (~1.1ms)
                       +-------------------------------------------------------------+
                                                     │
                                                     ▼
                       +-------------------------------------------------------------+
                       |       08. Cryptographic Provenance (SHA-256) & Serialization | (~0.12ms)
                       +-------------------------------------------------------------+
                                                     │
                                    Total Core RAG Engine: ~10.4ms P50
```

### 1. In-Memory INT8 Scalar Quantization in Qdrant
- Quantized the 384-dimensional dense vectors (`intfloat/multilingual-e5-small`) to **INT8 scalar quantization** with `always_ram: true`.
- Leverages CPU **AVX-512 / AVX2 SIMD instructions**, dropping vector distance computation from ~45ms to **3.2ms – 5.5ms** while cutting RAM consumption by 75%.

### 2. Zero-Network In-Memory BM25 Sparse Search + Reciprocal Rank Fusion (RRF)
- The sparse lexical engine runs entirely in memory using character 3–5 grams and exact numeric/date token extractors.
- Concurrent dense and sparse results are blended in **< 1ms** via custom Reciprocal Rank Fusion without costly neural cross-encoder overhead.

### 3. Non-Blocking Speculative Retrieval
- While the user is speaking, stable partial transcripts from Sarvam Saaras launch cancellable background searches.
- When the final transcript is received, if the query matches the speculative window, retrieved candidate chunks are reused instantly (**0ms retrieval time**).

### 4. Deterministic Substring Span Extraction (< 2ms)
- Primary voice answers bypass LLM autoregressive token generation entirely.
- The extractive generator slices the highest-scoring exact sentence spans from the top-scoring candidate passage and computes SHA-256 cryptographic provenance offsets in **~1ms**.

### 5. Asynchronous Progressive Synthesis (Post-Primary)
- Optional fluent generative synthesis via **Groq `openai/gpt-oss-20b`** runs post-primary in the background.
- Employs strict JSON Schema structured output decoding bounded to **at most 2 citations**, guaranteeing that generative rendering never delays primary audio playback or TTS.

### 6. Central India Co-Location Topology
- The FastAPI backend, Qdrant vector engine, and Sarvam realtime ingest are hosted in **Azure Central India** (sub-20ms domestic network round-trip).
- The web frontend is globally deployed at **https://vani-rag.susdev.in** with WebSocket multiplexing.

---

## 🎨 Frontend & User Experience

* **Interactive 3D WebGL Gradient Waves**: Fullscreen dynamic wave canvas responding to audio levels and user interaction.
* **In-Browser Cached Chat Timeline**:
  * Seamless transition from the centered Hero Voice Orb into a continuous scrollable conversation stream after the first query.
  * **User Questions (Right-Aligned)**: Glassmorphic cards with language chip (`English`, `हिंदी`, `Hinglish`), source tag (`Voice` / `Text`), and timestamp.
  * **System Responses (Left-Aligned)**: 3D animated Uiverse mini-orb indicating live status (`Listening`, `Generating`, `Grounded Evidence`), dual response cards, and the 8-stage vertical latency breakdown.
  * **Zero Database Storage**: Conversation history is cached strictly in `sessionStorage` with a 1-click **"New Conversation"** reset.
* **Sticky Floating Dock**: Floating action capsule (Voice Mic, Stop & Ask, Language Hint selector, Questions Bank, and 3 Multilingual Quick Sample Pills) pinned to the bottom of the viewport.
* **Multilingual Verified Question Bank**: Gallery of 18 validated queries across English, Hindi, and Hinglish with clean/mild-noise filters.

---

## 🏗️ System Architecture

```
+-----------------------------------------------------------------------------------+
|                         CLIENT (Live Domain: https://vani-rag.susdev.in)          |
|  - React 18 + Vite + TypeScript + Tailwind CSS                                    |
|  - WebGL 3D Gradient Waves Shader                                                 |
|  - AudioWorklet 16kHz PCM Streamer + Live WebSocket Client                        |
+-----------------------------------------------------------------------------------+
                                    │ (WSS / HTTPS)
                                    ▼
+-----------------------------------------------------------------------------------+
|               BACKEND API (Azure VM Central India: https://4.213.226.146.sslip.io)|
|  - FastAPI + Uvicorn + Asyncio                                                    |
|  - Nginx Reverse Proxy (HTTP/2 + TLS + WebSocket Multiplexing)                    |
|  - Sarvam AI Saaras v3 Realtime WebSocket Adapter                                 |
|  - Embedding Engine: intfloat/multilingual-e5-small (Frozen Revision)             |
|  - In-Memory Character 3-5 Gram Sparse Lexical Index                              |
|  - Guardrails: Injection Gate, Freshness Gate, Supported/Contradiction Verifier    |
|  - Deterministic Extractive Span Generator (SHA-256 Provenance)                   |
|  - Groq openai/gpt-oss-20b Progressive Synthesizer (JSON Schema Bounded)          |
+-----------------------------------------------------------------------------------+
                                    │ (In-Memory IPC / SIMD)
                                    ▼
+-----------------------------------------------------------------------------------+
|                       QDRANT VECTOR DATABASE (Local Docker Container)              |
|  - Collection: awaaz_tiderag_v1 (112,127 points, 222,392 indexed vectors)        |
|  - INT8 Scalar Quantization in RAM (always_ram: true)                             |
|  - Distance: Cosine Similarity with Payload Filters                               |
+-----------------------------------------------------------------------------------+
```

---

## 📡 API Reference

### Health & Readiness
- `GET /health`: Process liveness and uptime.
- `GET /ready`: Complete system diagnostics (Sarvam credentials, Groq status, Frozen thresholds, Model revision, Qdrant point count and schema verification).

### Query Endpoints
- `WS /v1/query/voice`: High-performance 16 kHz raw PCM audio stream for realtime voice RAG.
- `POST /v1/query/text`: Text-based query endpoint executing the exact same RAG pipeline.
  ```json
  {
    "query": "what is the net gain and loss",
    "language": "en",
    "request_id": "optional-uuid"
  }
  ```
- `POST /v1/query/synthesis`: Redeem an opaque, short-lived synthesis token to request post-primary Groq synthesis.
  ```json
  {
    "request_id": "query-uuid",
    "token": "opaque-short-lived-synthesis-token"
  }
  ```

### Evidence & Catalog
- `GET /v1/prompts/verified`: Serves the 18 verified multilingual queries (English, Hindi, Hinglish) with length and noise metadata.
- `GET /v1/evidence/summary`: Versioned, cryptographic audit report of retrieval accuracy, guardrail qualification, and corpus manifest hashes.

---

## 🛠️ Local Development & Setup

### Prerequisites
- Python 3.11 – 3.13 (3.12 verified)
- Node.js 18+ & npm
- Docker & Docker Compose (for Qdrant)
- Sarvam AI API Key (Realtime STT access)
- Groq API Key (Optional, for synthesis)

### 1. Clone & Configure Environment
```bash
git clone https://github.com/shashivadan/hhg-02.git
cd hhg-02
cp .env.example .env
```

Populate `.env`:
```dotenv
SARVAM_API_KEY=your_sarvam_api_key
GROQ_API_KEY=your_groq_api_key
RAG_ENABLE_GROQ_SYNTHESIS=true
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### 2. Start Backend & Qdrant
```bash
# Start Qdrant vector database
docker compose up -d qdrant

# Setup Python environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1
pip install -e "./backend[all]"

# Run FastAPI backend
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Start Frontend
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` to explore the Voice Workspace and System Evidence dashboard.

---

## 🧪 Testing & Verification

```bash
# Run all unit and integration tests
cd backend
python -m pytest

# Run type check and lint
python -m mypy app
python -m ruff check app

# Build and verify frontend
cd ../frontend
npm run build
```

---

## 📜 License
Distributed under the **Apache 2.0 License**. See [LICENSE](LICENSE) for details.
