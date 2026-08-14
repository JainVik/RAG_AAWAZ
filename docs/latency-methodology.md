# Latency methodology

## Primary definition

The primary timer uses `time.perf_counter_ns()`:

```text
start = backend validates/receives the end_of_stream marker for the final audio frame
end   = complete answer, evidence fallback, error, or abstention payload is materialized
```

This includes Sarvam finalization after the marker, final route/retrieval when speculative results
cannot be reused, request-time late chunking, generation, citation verification, guardrails, and
serialization. It is completed-output latency, not time to first token. A separate timer may report
audio-start-to-response user-perceived duration.

## Benchmark policy

- Primary voice run: at least 100 and target 300 distinct clips; concurrency 1.
- Hindi, English, and code-mixed speech; clean/noisy and short/long groups.
- Target at least 60 human recordings, with synthetic clips labelled separately.
- Warmups are declared and excluded; warm and cold-start results remain separate.
- The primary run disables query-result caching and uses unique questions.
- Slow successful requests are retained. Failures and abstentions are retained and classified.
- Report P50, P70, contextual P95, and `P100 = max(observed)` using nearest-rank percentiles.
- Report answer coverage beside latency; refusing everything cannot count as an SLA success.
- Preserve the complete server `timings_ms` mapping on every raw request. Aggregate every numeric,
  non-negative stage independently with its own sample count and timing coverage; missing stage
  values stay in the request denominator and are never converted to zero.
- A report cannot qualify from `total_after_final_audio` alone. Full measured-request coverage is
  required for `total_after_final_audio`, `serialization`, `audio_start_to_final_response`,
  `stt_finalize`, and `stt_last_final_after_end`. Verified responses additionally require full
  relevant coverage for `input_guarded` and `retrieved`; completed responses require
  `evidence_selected`, `answered`, and `verified`. The raw summary lists every missing field.
- Treat `speculative_launched` and `speculative_reused` as counters, not latency stages. Report
  their totals, joint timing coverage, reuse rate, and any row where reused exceeds launched.
  Qualification requires binary counters on every measured request, reused no greater than
  launched, and a numeric `speculative_retrieval` duration whenever launched is one.
- Raw JSONL/CSV, package versions, hardware, corpus/vector counts, Qdrant configuration, cache
  policy, and concurrency accompany every Markdown report.

The text-only smoke benchmark is useful for development but is explicitly not the judged voice
result. A fake STT benchmark is labelled provider-fixture latency and cannot satisfy the Sarvam
requirement.

Stage percentiles describe the distribution of each reported stage. They are not summed to
reconstruct the total because retrieval branches and other work may overlap. The client timer and
server `total_after_final_audio` remain the two headline measurements.

## Cold-start integrity and warm primary evidence

Cold start is a separately named, exactly-one-request artifact captured after restarting the
backend. It uses `--startup-condition cold --warmup 0 --limit 1`; it bypasses the 100-request
minimum only because it can never be the primary qualifying report. A cold report is labelled
either `cold_start_integrity_valid_non_primary` or `cold_start_integrity_invalid_non_primary`, and
its top-level `qualifying` value is always false.

Cold evidence fails closed unless all of the following are present and true:

- real voice mode, cold startup, zero warmups, exactly one measured request, and zero failures;
- a nonempty backend process-instance ID/start time from `/ready.runtime`, with
  `voice_requests_started == 0` at the pre-request readiness capture;
- one of one client timings and one of one server `total_after_final_audio` timings;
- complete canonical server-stage and speculative-counter evidence under the policy above;
- `/ready` evidence for the official `wss://api.sarvam.ai` Saaras provider plus a validated
  credentialed-smoke artifact;
- a bounded observed trailing-silence value, real-time pacing, disabled query-result cache, and
  concurrency one;
- a complete canonical compatibility object and a SHA-256 fingerprint that recomputes exactly.

The warm primary report compares that cold compatibility object field by field. The fixture hash,
voice WebSocket URL, Sarvam identity, dense model identity, active index/Qdrant identity, declared
deadline, audio chunk size, pacing, cache policy, concurrency, and trailing-silence policy must all
match. The backend process ID/start time is part of that identity, so restarting between cold and
warm captures invalidates the link. Any absent field or mismatch invalidates the cold link. Voice
mode requires an explicit `--deadline-ms` that exactly equals `/ready.runtime.rag_deadline_ms`.
Both that effective hard deadline and `/ready.runtime.rag_fallback_at_ms` are recorded in the
compatibility fingerprint and must match between cold and warm captures.

The warm run must independently meet the minimum sample, transcript-quality, verified-response,
language/condition, source-label, timing-coverage, and zero-failure requirements. A valid cold
one-shot is necessary evidence for that warm report, but it does not make the warm report qualify
by itself.

## Deadline behavior

The default absolute deadline is 200 ms and optional-work cutoff is 170 ms. The controller returns,
in order:

1. a fully verified concise extractive answer;
2. a direct cited evidence span if available;
3. a structured abstention or repeat request.

Retries run only when the remaining budget can accommodate both backoff and useful work. Sarvam
does not document resumable realtime sessions or safe in-flight audio replay, so an abnormal voice
disconnect requests repetition instead of silently replaying audio.

## Current evidence status

No submission latency percentile is recorded until a distinct-clip Sarvam run produces raw
artifacts under `backend/evaluation/reports/final/`. Unit, text-path, in-memory, and cold one-shot
timings are engineering/integrity evidence only and must not be cited as the under-200-ms primary
result.
