# Awaaz TideRAG architecture

## Design intent

Awaaz TideRAG is a CPU-first multilingual retrieval system. It uses frozen pretrained
components and deterministic orchestration; it does not train or fine-tune any model. The
runtime knowledge base contains passage text only. Queries, answers, and relevance labels
remain in separate evaluation artifacts.

```text
Browser microphone
  -> backend WebSocket (versioned events, PCM validation)
  -> Sarvam saaras:v3-realtime
       -> revisable transcript.partial events
       -> stability detector -> cancellable speculative retrieval
       -> authoritative transcript.final
  -> injection / safety / freshness gates
  -> deterministic Tide Router
  -> query: prefix -> multilingual-e5-small -> Qdrant named dense vector
  -> char 3–5 grams + exact number/date features -> Qdrant named sparse vector
  -> client-side weighted RRF + branch agreement -> parent deduplication
  -> request-time sentence windows over only the retrieved parents
  -> score / margin / agreement answerability gates
  -> exact evidence extraction with passage IDs and spans
  -> normalized span-containment verification
  -> primary complete answer, cited evidence fallback, or explicit abstention
       -> completed/eligible only: opaque short-lived synthesis offer
       -> separate HTTP request -> Groq openai/gpt-oss-20b
       -> grounded-claim/citation validation -> independent secondary result
```

Dense and sparse Qdrant queries are separate concurrent branches. This deliberately keeps each
branch's rank and score so agreement can be measured and used as a guardrail. Qdrant's server-side
fusion is not used on this path because a fused response does not retain both branch scores.

## Voice protocol

The backend accepts version `1` WebSocket events:

- `start`: request ID, `pcm_s16le`, 16 kHz, language;
- `audio_chunk`: monotonic sequence number and base64 PCM;
- `end_of_stream`: defines the primary latency start;
- server `stt_partial`, `pipeline_state`, `answer`, and `error` events.

The backend—not the browser—holds the Sarvam key. The provider adapter uses the current beta
`wss://api.sarvam.ai/speech-to-text-realtime/ws` endpoint, `saaras:v3-realtime`, URL query
configuration, and the `API-SUBSCRIPTION-KEY` handshake header. Audio is sent as JSON
`audio_input` frames. Sarvam does not document a recognition-confidence value for partial or
final transcripts, so the adapter leaves it unset. Language identification and VAD confidence
are not misrepresented as transcription confidence.

The realtime endpoint and event shapes were checked against the official
[Sarvam realtime guide](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-api)
and [WebSocket reference](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe/realtime/ws).

## Corpus identities and representations

`canonical_doc_id` is `sha256(NFC-and-whitespace-normalized English passage)`. Aligned translated
text shares this identity. A central language registry covers English plus all 14 MSMARCO-XI
Indic targets, records script ambiguity explicitly, and uses a provider/fixture hint when scripts
such as Devanagari are shared by multiple languages. `ChunkFactory` can emit these independently
flaggable views:

1. atomic English and translated passages;
2. language-aware sentence windows;
3. offline semantic sections for sufficiently long passages;
4. sentence children that return/deduplicate to parents;
5. bounded translated-English paired text;
6. deterministic hashed character 3–5-gram sparse vectors with exact number/date features.

Every monolingual chunk retains an exact character span into its source parent. Paired chunks
retain separate component-span metadata.

## Orchestration and failure states

The custom async harness uses Pydantic contracts, absolute monotonic deadlines, recorded stage
transitions, cancellation, bounded retries, and circuit breakers. Normal states are
`STT_FINAL -> INPUT_GUARDED -> RETRIEVED -> EVIDENCE_SELECTED -> ANSWERED -> VERIFIED -> COMPLETED`.
Terminal alternatives are `ABSTAINED`, `NEEDS_REPEAT`, `UNSAFE`, `DEADLINE_FALLBACK`,
`DEPENDENCY_UNAVAILABLE`, and `FAILED`.

At the fallback threshold, optional work stops. If verified evidence exists, the response is the
direct cited span. Otherwise the backend abstains. No partial transcript can become an answer.

## Progressive synthesis

Groq synthesis is disabled by default and is outside the primary deadline controller. A completed,
verified primary result may register a bounded server-side context and return an opaque offer token.
The frontend renders the primary Evidence card immediately, then presents that token to
`POST /v1/query/synthesis`. The browser never receives the Groq key and never sends content
directly to Groq.

The context store is in-memory, expires entries after `RAG_SYNTHESIS_CONTEXT_TTL_S`, and is bounded
by `RAG_SYNTHESIS_CONTEXT_MAX_ENTRIES`. Provider work is capped by `GROQ_MAX_CONCURRENCY`. These
bounds prevent the optional path from becoming an unbounded history or starving the primary query
pipeline.

Only completed grounded answers are eligible. Abstentions, unsafe/repeat decisions, deadline
fallbacks, dependency failures, and failed primary requests neither create an offer nor call Groq.
Without an offer, the frontend may still render a Groq-branded fixed status card: evidence
abstentions show `Out of context`, while unsafe/repeat, dependency, deadline, and failed outcomes
show `Not generated`. These are local presentation states, not Groq responses.
The model receives the final question/transcript plus only the selected evidence, and returned
source references must resolve to that evidence. A timeout, unavailable provider, invalid output,
or grounding failure produces an independent secondary status; it cannot mutate a successful
primary response.

Primary `total_after_final_audio` timing ends before progressive synthesis. The synthesis endpoint
reports `total_synthesis` separately, with `groq_synthesis` identifying only the provider-call
portion. See [Optional Groq progressive synthesis](groq-progressive-synthesis.md).

## Qdrant contract

The pinned production contract is Qdrant server/client 1.19.0. It uses `query_points` (the old
high-level `search` API has been removed), named dense and sparse vectors, payload indexes on the
strategy and representation-language filter fields, deterministic full-point upserts, and
collection metadata describing the
schema and encoders. Existing incompatible collections fail readiness; startup never silently
recreates them. See the official [collection](https://qdrant.tech/documentation/manage-data/collections/),
[point](https://qdrant.tech/documentation/manage-data/points/), and
[hybrid query](https://qdrant.tech/documentation/search/hybrid-queries/) documentation.

## Privacy boundaries

- Raw audio is held only for per-request validation and then cleared; it is not persisted by
  default.
- Raw query/transcript text and credentials are redacted from structured logs.
- `/metrics` contains aggregate states, reasons, timings, and speculative reuse only.
- Searchable payload schemas have no query, answer, or relevance fields.
- Retrieved passages are evidence data, never executable instructions.
- When optional Groq synthesis is both enabled and requested, the final question/transcript and
  selected passages cross the Groq third-party boundary. Raw audio, revisable partials, provider
  frames, credentials, and unrelated passages do not. Operators must disclose and approve this
  processing before enabling it.
