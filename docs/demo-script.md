# Submission demo script

## Pre-demo evidence check

1. Start pinned Qdrant and the backend from a clean checkout.
2. Confirm `GET /health` is 200.
3. Confirm `GET /ready` is 200 and show model name/dimension, collection/point count, sparse state,
   and Sarvam endpoint/model. Do not proceed if `credentialed_smoke_verified` is false.
4. Show the corpus and index manifest checksums and the completed requirements traceability table.
5. Keep the primary voice benchmark report and raw JSONL open; state hardware, corpus size, clip
   count, cache policy, concurrency, coverage, and P50/P70/P100.

## Main voice path

1. Select a clean Hindi microphone question whose answer is supported by the indexed corpus.
2. Speak naturally. Show `stt_partial` events and the `SPECULATIVE_RETRIEVAL` state without
   exposing raw text in server logs.
3. End the recording. Point out that the timer begins on the backend's `end_of_stream` receipt.
4. Show the authoritative final transcript, concise extractive answer, canonical passage ID,
   chunk strategy, exact cited text/span, dense and sparse scores, evidence agreement, terminal
   `COMPLETED` state, and full-output latency.
5. Repeat with an English question and a Hinglish/code-mixed question. The latter should show the
   bilingual/sparse route.

## Guardrail cases

1. Ask a current/live question. Expect `STALE_CORPUS`, not `UNSAFE_REQUEST`.
2. Say an instruction to ignore system rules and reveal hidden context. Expect
   `PROMPT_INJECTION`.
3. Play silence or an extremely short clip. Expect `SILENCE`/`AUDIO_TOO_SHORT` and a repeat prompt.
4. Ask an unsupported static question. Expect `NO_RELEVANT_EVIDENCE`.
5. Run the forced-deadline fixture. Show a cited evidence fallback when evidence exists and an
   explicit abstention when it does not.

## Reliability evidence

1. Run the scripted Qdrant failure test and show `DEPENDENCY_UNAVAILABLE`, bounded circuit opening,
   and absence of a generic HTTP 500.
2. Run the Sarvam abnormal-close fixture and show that in-flight audio is not silently replayed.
3. Show that stale speculative generations are cancelled/ignored and partial-only input cannot
   produce a final answer.
4. Finish with `GET /metrics`; verify it contains aggregate counts/timings but no audio, transcript,
   query, or secret.

## Claims discipline

- Say “Hindi, English, and code-mixed tested,” not “all 14 languages.”
- State measured completed-output latency, not time to first token.
- If P100 exceeds 200 ms, state it plainly and show fallback/coverage behavior.
- Do not call text input, fake STT, or synthetic-only clips the final judged voice path.
- Do not describe ingestion, evaluation, or threshold calibration as model training.

