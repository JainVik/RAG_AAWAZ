# Frontend functional requirements

Status: functional scope for the final frontend. Visual styling is intentionally left open for the
separate style specification.

The reference screenshots are idea references only. We may use the same *kind* of useful
information when it exists in this application, but we will not copy their layout, branding,
component design, wording, providers, or invented values. If the finished interface resembles a
reference in an ordinary way, that is acceptable; the implementation and visual system must still
be our own.

## 1. Exact product scope

The frontend has **two primary pages**:

| Route | Page | Purpose |
|---|---|---|
| `/ask` | Voice RAG Workspace | Ask by voice or text, follow the live pipeline, receive an answer or a truthful fallback, and inspect exact citations. |
| `/evidence` | Evaluation & System Evidence | Show measured retrieval quality, corpus/index facts, readiness, provenance, and only those latency/guardrail results that actually exist. |

`/` redirects to `/ask`. A not-found route is required but is not a product page. Dialogs and
drawers do not count as additional pages.

There will be no separate Dashboard, Query History, Sources, Chunking Engine, Analytics, Settings,
Developer Panel, or Ingestion page in the first complete application. The useful parts of those
ideas are included within the two pages below. This keeps the judged voice workflow prominent and
avoids a large admin interface whose buttons would not have real backend behavior.

## 2. Global application shell

The visual layout may use a top navigation, sidebar, or another original navigation pattern. It
must contain:

- a project-name/logo area;
- navigation links for `Ask` and `Evidence`;
- a compact readiness control with `Checking`, `Ready`, or `Not ready` status;
- a skip-to-content link and a visible keyboard focus state;
- a system-checks dialog or drawer opened by the readiness control.

The system-checks view displays the real `GET /health` and `GET /ready` results. It must distinguish
process liveness from submission readiness. It includes one `Refresh status` button. A failed or
503 readiness response must never be rendered as green/online.

The frontend must not show Gemini, TTS, a reranker, BM25, 3072-dimensional vectors, or any other
provider/feature that this backend does not implement. The actual stack is Sarvam realtime speech,
multilingual E5-small 384-dimensional dense embeddings, a character n-gram sparse vector,
client-side reciprocal-rank fusion, Qdrant, and extractive grounded answers with optional local
generation only when configured.

## 3. Page 1: Voice RAG Workspace (`/ask`)

### 3.1 Page purpose

This is the default and acceptance-critical experience. Voice is primary. Text is a clearly
labelled fallback for accessibility, development, and deterministic testing.

### 3.2 Input mode and language

Required controls:

- `Voice` and `Text` mode tabs;
- a language-hint selector with `Auto` (default), `Hindi`, `English`, and `Marathi`;
- Hindi-English code-mixed speech is handled through `Auto`; it is not presented as a separate
  user-facing language choice;
- `Reset conversation` clears only the current in-memory result and returns to idle.

The language selector supplies a hint; final detected language comes from the server. The client
must not claim that language detection is certain.

### 3.3 Voice input panel

Required controls and behavior:

| State | Primary control | Secondary control | Required feedback |
|---|---|---|---|
| Idle | `Start recording` | none | Microphone availability and short instruction. |
| Requesting permission | disabled button | `Cancel` | Permission request in progress. |
| Recording | `Stop & ask` | `Cancel` | Recording timer and `Listening` status. |
| Sending/processing | disabled | `Cancel request` where cancellation is still possible | Live transcript and pipeline state. |
| Terminal | `Ask another question` | none | Answer, fallback, repeat request, or error. |

Functional rules:

- Request microphone access only after the user presses `Start recording`.
- Capture mono audio and convert it to 16 kHz signed 16-bit little-endian PCM before transport.
- Stream ordered chunks over one WebSocket request; do not buffer the whole recording before
  starting transcription.
- Stop automatically at the server-compatible 60-second audio cap and send end-of-stream.
- `Cancel` stops media tracks, closes the socket, cancels pending work, and discards the current
  audio without producing an answer.
- A reconnect starts a new request ID and a new session. It must not replay uncertain audio into an
  old session.
- Handle denied permission, absent microphone, unsupported browser audio, disconnect, idle
  timeout, invalid audio, silence, and too-short audio as distinct visible states.
- Do not store raw audio in local storage, IndexedDB, analytics, or a history list.

### 3.4 Text fallback panel

Required controls:

- a labelled multiline input with a 4,096-character limit and visible remaining/used count near
  the limit;
- `Send question`;
- `Clear`;
- `Ctrl+Enter` or `Cmd+Enter` submits, while ordinary Enter remains available for multiline input.

The request uses `POST /v1/query/text`. Empty input, validation errors, unauthorized responses, and
dependency failures must use the same terminal-state language as voice. The page labels this mode
`Text test mode` so it is not presented as evidence that the voice path succeeded.

### 3.5 Live transcript

The transcript area must:

- show the latest `stt_partial` text as revisable text, not as a committed final transcript;
- replace it with terminal `payload.transcript` after the answer event;
- display the final returned language;
- show `Recognition confidence unavailable` when confidence is `null`.

Sarvam's current realtime events do not provide recognition confidence. Language/VAD confidence
must not be relabelled as recognition confidence and no percentage may be fabricated.

### 3.6 Pipeline progress

Show one compact status component driven by actual server events. It maps the backend states into
plain-language statuses:

| Backend state | User-facing group |
|---|---|
| `AUDIO_RECEIVED`, `STT_PARTIAL`, `STT_FINAL` | Transcribing |
| `SPECULATIVE_RETRIEVAL`, `RETRIEVED` | Retrieving evidence |
| `INPUT_GUARDED` | Checking the question |
| `EVIDENCE_SELECTED` | Selecting evidence |
| `ANSWERED` | Preparing the answer |
| `VERIFIED` | Verifying grounding |
| `COMPLETED` | Completed |
| `ABSTAINED` | Not enough evidence |
| `NEEDS_REPEAT` | Please repeat |
| `UNSAFE` | Request blocked |
| `DEADLINE_FALLBACK` | Evidence fallback |
| `DEPENDENCY_UNAVAILABLE` | Service unavailable |
| `FAILED` | Failed |

The UI must not simulate stages or timers that the server did not report.

### 3.7 Terminal result card

The result card renders one of these mutually exclusive outcomes:

1. **Grounded answer** — answer text, mode, final transcript, language, and citations.
2. **Evidence fallback** — exact returned evidence, clearly labelled as a deadline fallback rather
   than a generated answer.
3. **Abstention** — the server's guardrail message/reason and no success styling.
4. **Repeat request** — asks the user to try again and returns focus to the record control.
5. **Blocked request** — a safe, non-technical explanation.
6. **Dependency/error state** — error message, error code in details, and `Retry` only when the
   server says `retryable: true`.

Required result controls:

- `Copy answer`, shown only when answer text exists;
- `Ask another question`;
- `Retry`, shown only for a retryable terminal error;
- `Show diagnostics` / `Hide diagnostics`.

Client code must branch on `state`, `answer_mode`, and `guardrail.decision`; it must not infer
success merely because HTTP/WebSocket transport succeeded.

### 3.8 Citation list

Every returned citation is displayed. Each citation includes:

- exact cited text;
- canonical document ID, parent ID, chunk ID, and strategy;
- coordinate system and character span;
- dense and sparse scores only when the corresponding value is not `null`;
- `Expand` / `Collapse` for long citation text;
- `Copy citation`.

The client must not manufacture a document title, URL, relevance percentage, category, or
confidence score. Citation order is the server order. An answer with no citations is visibly marked
as ungrounded/invalid unless it is an abstention.

### 3.9 Collapsed diagnostics

Diagnostics are hidden by default. When opened they show:

- request ID;
- terminal pipeline state and answer mode;
- guardrail decision, reason, and user message;
- evidence agreement when it is not `null`;
- every returned `timings_ms` entry with the exact timing key;
- completed timestamp;
- `Copy diagnostics` as sanitized JSON.

Diagnostics must not expose secrets, absolute server paths, raw provider frames, or internal stack
traces.

## 4. Page 2: Evaluation & System Evidence (`/evidence`)

### 4.1 Page purpose

This page proves what was measured; it is not a decorative dashboard. Every metric group must show
its sample count, timestamp or artifact identity, and qualification state. Missing evidence is
rendered as `Not measured` or `Qualifying run pending`, never as zero and never as a guessed value.

Required page controls:

- `Refresh evidence`;
- `Copy evidence summary`;
- `Download sanitized JSON`;
- expandable `Methodology and limitations`.

There are no browser buttons for reindexing, corpus ingestion, deleting data, changing thresholds,
editing prompts, or running paid benchmarks.

### 4.2 Retrieval evaluation section

Show the current final held-out report:

- qualification badge (`Qualifying`, `Non-qualifying`, or `Not measured`);
- evaluated query count;
- failure count and completion coverage;
- Recall@1, Recall@5, Recall@10, MRR@10, and nDCG@10;
- retrieval-hit coverage;
- final-split and provenance verification status.

The current qualifying 500-query report is approximately Recall@1 26.7%, Recall@5 70.63%,
Recall@10 84.33%, MRR@10 45.33%, and nDCG@10 54.69%. These numbers are examples of the current
artifact, not values to hardcode into components. The UI loads them from sanitized evidence.

Each metric needs a short accessible explanation:

- Recall@K: whether at least one relevant passage appears in the top K.
- MRR@10: how early the first relevant passage appears.
- nDCG@10: ranking quality across the top ten positions.

### 4.3 Corpus and index section

Show only manifest-backed facts:

- dataset ID, language, revision, and source split;
- document count, evaluation-fixture count, and indexed point/chunk count;
- Qdrant collection and readiness;
- dense model, pinned model revision, vector dimension, and distance;
- sparse representation name/version;
- index build ID and manifest verification status.

The current artifacts contain 10,005 documents, 1,006 original evaluation fixtures, and 112,114
indexed chunks. Again, these are loaded values rather than frontend constants.

### 4.4 Chunk representations section

Show the five representations actually built, as read-only comparison cards or a table:

- atomic;
- sentence window;
- semantic section;
- parent-child;
- bilingual paired.

For each, render enabled state, chunk count, average text length, artifact bytes, and build duration
when supplied by the manifest. Include a plain-language description. Do not show an `Active`
selector or allow users to change runtime routing; the Tide Router selects representations
automatically.

### 4.5 Guardrail evidence section

Show qualification, sample size, execution scope, category results, and failure count from a
sanitized guardrail report when one exists. Offline/unit fixtures must be labelled
`Non-qualifying synthetic evidence`. Do not claim that prompt injection, contradictory evidence,
or live dependencies passed end-to-end merely because a direct unit gate passed.

### 4.6 Voice latency section

Until a qualifying real-provider voice run exists, show `Qualifying voice latency run pending`.
When evidence exists, render only the fields present in the sanitized report:

- cold and warm runs separately;
- sample count and human/synthetic coverage;
- P50, P70, P95, and P100/max for the defined primary latency;
- server timing coverage and required stage percentiles;
- transcript-match and verified-response coverage;
- speculative retrieval launched/reused counts;
- hard/fallback deadline compatibility;
- qualification and failed checks.

One request's timing is never displayed as an aggregate percentile. Cold and warm results are never
merged.

### 4.7 Readiness and provenance section

Show the real readiness checks returned by the backend, plus:

- active model/index/threshold binding status;
- Qdrant collection count/schema readiness;
- Sarvam configuration and credentialed-smoke status without showing the key;
- corpus/index/report hashes in a collapsed technical-details area;
- process instance/start time and configured hard/fallback deadlines.

`All systems operational` is allowed only when the backend returns `status: ready` and all required
checks are ready.

### 4.8 Methodology and limitations

The expandable section must state at least:

- the retrieval report is a deterministic final held-out evaluation;
- metrics depend on this corpus, index, model, router contract, and frozen thresholds;
- retrieval quality does not prove generation or voice accuracy;
- Sarvam recognition confidence is unavailable, so its low-recognition-confidence path is not
  credentialed-provider validated;
- unmeasured voice/guardrail evidence remains non-qualifying;
- raw evaluation rows and private audio are not exposed by the frontend.

## 5. Exact backend/API contract

### 5.1 Existing endpoints

| Method | Path | Frontend use |
|---|---|---|
| `GET` | `/health` | Process liveness and backend version. |
| `GET` | `/ready` | Submission readiness, individual checks, runtime instance, and deadlines. |
| `GET` | `/metrics` | Privacy-safe aggregate process telemetry; never query history. |
| `POST` | `/v1/query/text` | Text test/fallback request. |
| `WS` | `/v1/query/voice` | Realtime voice session. |

Text request body:

```json
{
  "query": "question, 1 to 4096 characters",
  "language": "unknown",
  "request_id": "client-generated UUID",
  "deadline_ms": null
}
```

The language enum is `hi`, `en`, `mr`, `hi-en`, or `unknown`. The normal frontend leaves
`deadline_ms` null so the server's frozen policy is used.

### 5.2 Voice client events

All frames are JSON text and require `version: "1"`:

```json
{"type":"start","version":"1","request_id":"...","encoding":"pcm_s16le","sample_rate_hz":16000,"language":"unknown"}
{"type":"audio_chunk","version":"1","sequence":0,"audio_b64":"..."}
{"type":"end_of_stream","version":"1"}
```

The client sequence starts at zero and increases monotonically.

### 5.3 Voice server events

The client validates the discriminated event types before rendering:

- `stt_partial`: revisable text, language, nullable confidence;
- `pipeline_state`: one exact backend pipeline state;
- `answer`: the complete typed `QueryResponse`;
- `error`: code, state, message, retryable, details, and timings.

Unknown versions, event types, or malformed payloads produce a safe client protocol-error state and
are never rendered as an answer.

### 5.4 Required new read-only endpoint

The frontend build requires one small backend addition:

`GET /v1/evidence/summary`

It returns a versioned, typed, sanitized summary assembled from approved manifests and reports. The
response contains these top-level groups:

```text
schema_version
generated_at
retrieval
corpus
index
chunk_representations
guardrails
voice_latency
provenance
```

Every measured group includes `status`, `qualifying`, `sample_count`, `source_artifact_sha256`, and
`failed_checks` where applicable. The endpoint must not return raw queries, answers, transcripts,
audio paths, absolute local paths, API keys, environment values, or arbitrary report contents. If
an artifact is absent or invalid, that group returns `not_measured`/`invalid`, not a server crash.

This endpoint will be implemented with the frontend work. Until then, `/evidence` must show a clear
unavailable state rather than use hardcoded demo data.

## 6. Frontend technical requirements

The implementation baseline is:

- React, TypeScript, and Vite;
- strict TypeScript with no `any` in API models;
- React Router for `/ask` and `/evidence`;
- native `fetch`, `WebSocket`, MediaDevices, and Web Audio APIs;
- runtime validation/type guards for all server events and evidence responses;
- a small in-memory request state machine; no large global state library is required;
- one configurable same-origin API base, with Vite proxying to `127.0.0.1:8000` in development;
- production served behind one same-origin reverse proxy using HTTPS/WSS.

Required environment contract:

```text
VITE_API_BASE_URL=/api
VITE_WS_BASE_URL=/ws
```

The final deployment proxy maps those paths to the backend. No Sarvam key, Qdrant credential,
Hugging Face token, model path, or backend `.env` value is ever placed in a `VITE_*` variable or
sent to the browser. The browser never connects directly to Sarvam, Qdrant, or Hugging Face.

For local loopback development, application bearer auth may be disabled. Before non-loopback
deployment, authentication must be terminated by the same-origin reverse proxy or a backend
session mechanism. A secret bearer token must not be embedded in frontend JavaScript or local
storage. Secure-context microphone access means production must use HTTPS.

## 7. Required client states and error handling

Every network-backed component implements `idle`, `loading`, `success`, `empty`, and `error` states.
The query workflow additionally supports `recording`, `streaming`, `cancelling`, and every terminal
pipeline state.

Required error treatments:

| Condition | Required action/message behavior |
|---|---|
| Backend offline | Keep page usable, show not-ready, disable new voice submission, allow status refresh. |
| Backend alive but not ready | Show failed readiness checks and do not claim the system is online. |
| Microphone denied | Explain how to retry browser permission and offer Text mode. |
| Unsupported audio/browser | Offer Text mode; do not silently send a different format. |
| WebSocket disconnect | Stop recording, close tracks, show retryable connection failure. |
| Validation/unauthorized | Show safe server message; do not retry automatically. |
| Sarvam/Qdrant dependency failure | Preserve dependency-specific code in diagnostics and show retry only if allowed. |
| Silence/short/unclear audio | Show repeat state rather than an empty successful answer. |
| No relevant/contradictory evidence | Show abstention with server reason. |
| Hard deadline | Show evidence fallback or deadline error exactly as returned. |
| Malformed server payload | Show client protocol error and retain no unvalidated content. |

## 8. Privacy, security, and data handling

- No query-history page and no automatic persistence of audio, transcripts, questions, answers, or
  citations.
- Current request state may live in memory and disappears on refresh.
- Clipboard actions occur only after an explicit button press.
- No third-party analytics, session replay, remote fonts, or tracking scripts by default.
- Do not render raw HTML from answers, transcripts, citations, errors, or report fields.
- Apply a strict Content Security Policy in production and restrict connections to the same origin.
- Media tracks are stopped on cancel, terminal response, route change, page hide/unload, and error.
- Server readiness/report details are allowlisted; secrets and filesystem paths stay server-side.
- The final public/non-loopback deployment requires shared auth, origin checks, rate/concurrency
  controls, and HTTPS/WSS. The current safe demo default remains loopback-only.

## 9. Accessibility and responsive behavior

These are functional requirements, not optional styling:

- WCAG 2.2 AA target;
- complete keyboard operation and visible focus;
- semantic headings, landmarks, labels, buttons, lists, and tables;
- screen-reader live regions for partial transcript, pipeline status, and terminal result without
  announcing every audio chunk;
- no color-only meaning for readiness, error, qualification, or guardrail state;
- minimum 44 by 44 CSS-pixel primary touch targets;
- reduced-motion support;
- readable Devanagari and Latin scripts with correct line wrapping;
- desktop, tablet, and mobile layouts with no horizontal page scrolling;
- on narrow screens, microphone/input and answer appear before diagnostics/evidence details.

The browser acceptance target is the current stable Chrome and Edge releases on Windows. Text mode
must remain usable if microphone/Web Audio capability is unavailable.

## 10. Deliberately excluded frontend features

The following are not required and must not be drawn as functional controls:

- persistent query history or audit log;
- corpus browsing/searching or raw passage repository;
- upload/ingest passage;
- reindex/delete/export the corpus;
- manual chunk-strategy selection in the judged query flow;
- model, prompt, temperature, top-p, token, RRF, threshold, or guardrail settings;
- provider/model marketplace or status badges for unused providers;
- TTS playback or synthesized voice answers;
- user accounts, teams, billing, or admin roles;
- a developer API console;
- fake categories, confidence percentages, document titles, or benchmark values;
- buttons whose only behavior would be a toast or placeholder.

These can be reconsidered only after the corresponding backend capability, authorization,
provenance, and retention policy exists.

## 11. Test and completion requirements

The frontend is complete only when all of the following pass:

1. Lint, formatting, strict type-check, unit tests, and production build.
2. Component tests for every answer/abstain/repeat/fallback/error state.
3. Protocol tests for valid and invalid version-1 WebSocket events.
4. Tests that microphone cancel/error always stop media tracks and close the socket.
5. Tests that `null` confidence, scores, and unmeasured evidence are displayed truthfully.
6. Keyboard and automated accessibility checks for both pages and dialogs.
7. Responsive checks at phone, tablet, and desktop widths.
8. Deterministic browser E2E using a mock server for partial transcript, state changes, answer,
   citation, abstention, deadline fallback, and retryable error.
9. One separate local real-system smoke: real microphone -> Sarvam -> Qdrant -> terminal grounded
   answer or truthful abstention, with the backend ready and secrets absent from browser assets.
10. Evidence page renders the actual sanitized 500-query report and labels absent qualifying voice
    evidence as pending.

## 12. What the final style specification must provide

The next MD file from the frontend/style work should define only the visual and content-design
decisions below. It does not need to redesign the backend contract.

1. Final project display name, short tagline, and logo asset or text-only logo decision.
2. Original visual direction/mood and what should feel most prominent.
3. Color tokens for backgrounds, surfaces, text, borders, accent, success, warning, and error.
4. Typography for Latin and Devanagari, including font files or licensed/public font sources.
5. Navigation choice (top, side, or another pattern) for the two pages.
6. Page wireframes or section order at desktop and mobile widths.
7. Visual states for buttons, inputs, tabs, badges, result cards, citations, diagnostics, dialogs,
   loading, disabled, focus, hover, recording, and errors.
8. Icon library and illustration policy.
9. Motion policy, including recording feedback and reduced-motion behavior.
10. Exact interface tone/copy preferences and whether labels remain English-only or are localized.
11. Which screenshot concepts are useful inspiration and which visual ideas must be avoided.
12. Whether the Evidence page should look public-friendly, engineering-focused, or balanced.

The style file may change colors, spacing, typography, navigation appearance, card appearance, and
visual composition. It must not add unsupported pages, fake metrics, unsafe settings, or placeholder
buttons without first changing this functional contract.

## 13. Final handoff checklist

The frontend/style provider needs to deliver:

- the final style MD covering section 12;
- logo/icon assets, if any, in SVG/PNG with usage rights;
- font names/files and licensing, if not using system fonts;
- desktop and mobile reference frames or clear written layout rules;
- final product name and visible copy changes;
- any intentional deviation from this functional scope, clearly listed for approval.

The provider does **not** need to decide the recording protocol, API fields, metric definitions,
guardrail rules, readiness logic, citation schema, or security boundaries. Those are fixed here and
will be implemented with the frontend.
