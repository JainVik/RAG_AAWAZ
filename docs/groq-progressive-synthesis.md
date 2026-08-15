# Optional Groq progressive synthesis

## Purpose and trust boundary

The normal Awaaz TideRAG response remains the fast, verified extractive result with exact
citations. When explicitly enabled, the backend may offer a second, post-primary synthesis using
Groq's `openai/gpt-oss-20b` model. The frontend shows that fluent answer in a separate adjacent
card; it never replaces, delays, or relabels the primary evidence answer.

This is progressive enhancement, not a new answerability path:

- retrieval and the existing guardrails decide whether the corpus supports an answer;
- the primary answer is returned before any Groq request;
- an abstention, repeat request, unsafe decision, deadline fallback, dependency failure, or other
  non-completed primary result is never sent to Groq and never receives a synthesis offer;
- the frontend still renders a fixed Groq-branded status card for a primary result without an
  answer; this display-only state does not imply that Groq received the request or generated text;
- a Groq timeout, rate limit, malformed response, unavailable provider, or grounding failure affects
  only the secondary card. The successful primary result remains intact.

## Configuration

The feature is off by default. Copy `.env.example` to `.env`, keep the real key local, and set:

```dotenv
RAG_ENABLE_GROQ_SYNTHESIS=true
GROQ_API_KEY=<local Groq secret>
GROQ_MODEL=openai/gpt-oss-20b
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_TIMEOUT_S=8
GROQ_MAX_COMPLETION_TOKENS=384
GROQ_MAX_CONCURRENCY=4
RAG_SYNTHESIS_CONTEXT_TTL_S=60
RAG_SYNTHESIS_CONTEXT_MAX_ENTRIES=256
```

`GROQ_API_KEY` is a backend-only secret. Do not add it to a `VITE_*` variable, frontend source,
browser storage, request payload, screenshot, log, or committed file. Disabling
`RAG_ENABLE_GROQ_SYNTHESIS` restores the extractive-only product without requiring a Groq key.
`GROQ_BASE_URL` must use HTTPS. In production, the synthesis endpoint uses the same backend bearer
authentication as the text endpoint; the application token is not the Groq credential.

`GROQ_TIMEOUT_S` bounds one secondary request, `GROQ_MAX_COMPLETION_TOKENS` bounds generated and
reasoning output, and `GROQ_MAX_CONCURRENCY` caps simultaneous provider calls. The context store is
volatile and one-use: `RAG_SYNTHESIS_CONTEXT_TTL_S` controls expiry and
`RAG_SYNTHESIS_CONTEXT_MAX_ENTRIES` bounds its total entries. An expired, evicted, already-consumed,
or request-ID-mismatched offer is rejected rather than reconstructed from browser content.

The exact model identifier and OpenAI-compatible base URL follow the official
[Groq GPT-OSS 20B model page](https://console.groq.com/docs/model/openai/gpt-oss-20b) and
[API reference](https://console.groq.com/docs/api-reference). The backend uses Chat Completions,
bounded output, low reasoning effort, and excludes model reasoning from the application response.
Its strict response schema follows Groq's
[Structured Outputs documentation](https://console.groq.com/docs/structured-outputs).

When synthesis is enabled, `/ready` requires valid local Groq configuration and the presence of a
key. That startup check does not prove the key has provider access or that a real completion has
succeeded; the independent secondary unavailable/error states remain necessary.

## Progressive API flow

1. Text or voice submission completes through the existing retrieval, evidence-selection,
   extraction, and verification path.
2. An eligible primary `QueryResponse` may contain an optional synthesis offer:

   ```json
   {
     "synthesis": {
       "token": "opaque-server-issued-token",
       "provider": "groq",
       "model": "openai/gpt-oss-20b",
       "expires_in_ms": 60000
     }
   }
   ```

   The token is opaque. The browser must not attempt to decode it or send the transcript/evidence
   directly to Groq. A missing or `null` offer means the synthesis endpoint must not be called. A
   completed primary response then keeps the single-card UI; a no-answer primary response uses the
   fixed status-card mapping below.
3. The frontend renders the primary Evidence answer immediately, then sends the primary request ID
   and token to `POST /v1/query/synthesis`:

   ```json
   {
     "request_id": "the-primary-request-id",
     "token": "opaque-server-issued-token"
   }
   ```

4. The backend resolves the short-lived server-side offer and, only then, sends the bounded
   question/transcript and retrieved evidence to Groq. The response contract contains
   `request_id`, `provider`, `model`, `status`, `answer`, `claims`, `citations`, `guardrail`,
   `retryable`, `timings_ms`, and `completed_at`.
5. The secondary status is one of `completed`, `abstained`, `timed_out`, `unavailable`, or
   `grounding_failed`. Only `completed` is styled as a successful synthesized answer. The other
   states explain why the secondary enhancement was unavailable while preserving the primary card.

Offer tokens remain one-use even when the provider fails, so non-completed synthesis responses set
`retryable` to `false`. A new attempt requires a fresh primary query and a new offer; the client
must not replay the consumed token.

The frontend lays out Evidence first and Groq synthesis adjacent to it on wide screens, with the
same order stacked vertically on narrower screens. It identifies the provider/model honestly and
does not present the generated card as stronger evidence than the verified primary result.

### Fixed no-call card states

When the primary result has no answer, no synthesis offer, and no synthesis result, the adjacent
card keeps the `Groq grounded synthesis` header but does not show a model badge, generated timing,
or provider-result status:

- an evidence abstention uses the title/status `Out of context` and the exact explanation
  `Groq was not invoked because no verified corpus evidence was available.`;
- `NEEDS_REPEAT`, `UNSAFE`/blocked (including prompt injection), `DEPENDENCY_UNAVAILABLE`,
  `DEADLINE_FALLBACK`, and `FAILED` use the title/status `Not generated` with an outcome-specific
  explanation.

These strings are deterministic frontend status copy. They are not returned by Groq and must not
be described as a Groq answer, refusal, or generation. None of these states redeems an offer or
makes a request to `/v1/query/synthesis` or Groq.

## Grounding and citations

Groq receives only the bounded evidence selected by this RAG request and instructions to answer
from that evidence. The backend, not the model, remains authoritative for citation identity and
text. Model-returned citation references must resolve to the offered retrieved set; invented or
unsupported references fail grounding rather than appearing in the UI.

The generated answer is an additional fluent rendering, not permission to use the model's
pretrained knowledge as a fallback. If the evidence does not substantiate the generated claims,
the secondary response is `grounding_failed` or `abstained`. The original extractive answer and
citations remain available.

## Latency reporting

`total_after_final_audio` continues to measure the primary voice result and remains the latency
shown on the primary card. Groq synthesis starts after that result is materialized. Its canonical
user-facing duration is `timings_ms.total_synthesis`; `timings_ms.groq_synthesis` is the
provider-call portion only. The secondary card labels the total synthesis duration, not the
provider-only value.

Never add secondary synthesis time to, subtract it from, or silently substitute it for the primary
timing. A single Groq request is not a P50/P70/P95/P100 benchmark. Any aggregate synthesis latency
claim needs its own measured sample, timing coverage, failure/abstention denominator, provider and
model identity, and qualification label.

## Third-party data disclosure

Enabling and requesting progressive synthesis sends the user's final question/transcript and the
selected corpus evidence to Groq for processing. It does **not** send raw microphone audio,
revisable partial transcripts, Sarvam provider frames, Qdrant credentials, Groq credentials,
backend bearer tokens, environment values, or unrelated corpus passages.

Operators must disclose this third-party processing before enabling the feature and apply their
chosen Groq account, retention, regional, privacy, and contractual controls. Do not enable it for
data whose policy prohibits disclosure to Groq. The repository's no-persistence default does not,
by itself, define or override Groq's service-side data policy.

## Run and rebuild

After pulling the implementation, rebuild the backend and frontend images because both the API and
card/protocol types changed:

```powershell
Set-Location C:\RAG
docker compose build backend frontend
docker compose up -d qdrant backend frontend
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/ready
```

A later `.env`-only change does not require an image build, but it does require recreating the
backend container so the new process receives the values:

```powershell
docker compose up -d --force-recreate backend
Invoke-RestMethod http://127.0.0.1:8000/ready
```

For direct development, restart both processes after changing `.env`:

```powershell
# Terminal 1
Set-Location C:\RAG\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2
Set-Location C:\RAG\frontend
npm run dev
```

Open `http://localhost:5173`, submit a corpus-answerable question, confirm the primary Evidence
card appears first, and then confirm the separate Groq card settles independently. Also test an
unsupported question: it must abstain, show the fixed `Out of context` card and no model badge, and
neither offer synthesis nor call Groq. Repeat, unsafe/block, dependency, deadline, and failed
fixtures must instead show `Not generated` without calling Groq.
