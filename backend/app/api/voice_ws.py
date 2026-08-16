from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hmac
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any, Literal, Protocol, runtime_checkable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.config import Settings
from app.core.deadlines import Deadline
from app.core.errors import PipelineError
from app.domain.enums import (
    AnswerMode,
    ErrorCode,
    GuardrailDecision,
    GuardrailReason,
    Language,
    PipelineState,
    SttEventType,
)
from app.domain.languages import language_from_tag
from app.domain.models import (
    AudioChunkEvent,
    AudioStartEvent,
    EndOfStreamEvent,
    GuardrailResult,
    QueryResponse,
    SttEvent,
    Transcript,
    VoiceErrorPayload,
    server_event_adapter,
)
from app.guardrails.audio_gate import evaluate_pcm_audio
from app.harness.circuit_breaker import CircuitBreaker
from app.harness.orchestrator import PipelineOrchestrator
from app.retrieval.hybrid import RetrievalResult
from app.stt.base import (
    RetryDecision,
    RetryDisposition,
    SpeechToTextProvider,
    SttProviderError,
)
from app.stt.stability import (
    SpeculativeRetrievalConfig,
    SpeculativeRetrievalController,
    TranscriptStabilityConfig,
    TranscriptStabilityDetector,
)
from app.telemetry.recorder import metrics_recorder

MAX_AUDIO_BYTES = 16_000 * 2 * 60
MAX_VOICE_JSON_CHARACTERS = 2_560_512


class VoiceServices(Protocol):
    orchestrator: PipelineOrchestrator | None
    stt_factory: Callable[[], SpeechToTextProvider] | None
    sarvam_breaker: CircuitBreaker


@runtime_checkable
class SessionConfigurableStt(Protocol):
    def configure_session(self, language: Language) -> None: ...


router = APIRouter(tags=["query"])


def _language_from_provider(value: str | None, fallback: Language) -> Language:
    detected = language_from_tag(value)
    return fallback if detected == Language.UNKNOWN else detected


def _voice_access_allowed(websocket: WebSocket, settings: Settings) -> bool:
    origin = websocket.headers.get("origin")
    allowed_origins = settings.voice_allowed_origins
    if origin is not None and allowed_origins and origin not in allowed_origins:
        return False
    expected = settings.voice_api_token_value
    if expected is None:
        return True
    authorization = websocket.headers.get("authorization", "")
    scheme, _, provided = authorization.partition(" ")
    return scheme.casefold() == "bearer" and hmac.compare_digest(provided, expected)


async def _bounded_provider_call(
    operation: Callable[[], Awaitable[Any]],
    *,
    breaker: CircuitBreaker | None,
    timeout_s: float,
    operation_name: str,
) -> Any:
    async def timed() -> Any:
        try:
            async with asyncio.timeout(timeout_s):
                return await operation()
        except TimeoutError as exc:
            raise SttProviderError(
                code=f"{operation_name}_timeout",
                message=f"Sarvam {operation_name} exceeded its operation timeout",
                fatal=True,
                retry=RetryDecision(
                    retryable=True,
                    disposition=RetryDisposition.RECONNECT_NEW_SESSION,
                    reason="provider operation timeout",
                    audio_replay_safe=False,
                ),
            ) from exc

    return await (breaker.call(timed) if breaker is not None else timed())


async def _receive_json_frame(
    websocket: WebSocket, *, timeout_s: float
) -> tuple[dict[str, Any], int]:
    """Timestamp an ASGI WebSocket frame before JSON decoding and validation."""

    message = await asyncio.wait_for(websocket.receive(), timeout=timeout_s)
    received_ns = time.perf_counter_ns()
    if message.get("type") == "websocket.disconnect":
        raise WebSocketDisconnect(code=int(message.get("code", 1000)))
    raw = message.get("text")
    if raw is None and isinstance(message.get("bytes"), bytes):
        try:
            raw = message["bytes"].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Voice events must contain UTF-8 JSON") from exc
    if not isinstance(raw, str):
        raise ValueError("Voice events must be JSON text frames")
    if len(raw) > MAX_VOICE_JSON_CHARACTERS:
        raise ValueError("Voice event exceeds the protocol frame limit")
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("Voice events must be JSON objects")
    return decoded, received_ns


async def _send(
    websocket: WebSocket,
    lock: asyncio.Lock,
    *,
    event_type: Literal["stt_partial", "pipeline_state", "answer", "error"],
    request_id: str,
    payload: dict[str, Any],
    deadline: Deadline | None = None,
    audio_started_ns: int | None = None,
) -> dict[str, Any]:
    event = server_event_adapter.validate_python(
        {
            "type": event_type,
            "version": "1",
            "request_id": request_id,
            "payload": payload,
        }
    )
    materialized = event.model_dump(mode="json")
    if deadline is not None:
        timings = materialized["payload"].setdefault("timings_ms", {})
        timings["serialization"] = 0.0
        timings["total_after_final_audio"] = deadline.elapsed_ms
        if audio_started_ns is not None:
            timings["audio_start_to_final_response"] = (
                time.perf_counter_ns() - audio_started_ns
            ) / 1_000_000
        serialization_started = time.perf_counter_ns()
        json.dumps(materialized, ensure_ascii=False, separators=(",", ":"))
        serialization_ms = (time.perf_counter_ns() - serialization_started) / 1_000_000
        timings["serialization"] = serialization_ms
        # A structurally identical probe estimates the final encode so the
        # payload reports completed-output materialization, not first-token time.
        timings["total_after_final_audio"] = deadline.elapsed_ms + serialization_ms
        if audio_started_ns is not None:
            timings["audio_start_to_final_response"] = (
                time.perf_counter_ns() - audio_started_ns
            ) / 1_000_000 + serialization_ms
    wire_payload = json.dumps(
        materialized, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    async with lock:
        await websocket.send_text(wire_payload)
    return materialized


async def _send_error(
    websocket: WebSocket,
    lock: asyncio.Lock,
    request_id: str,
    code: ErrorCode,
    message: str,
    *,
    state: PipelineState = PipelineState.FAILED,
    deadline: Deadline | None = None,
    audio_started_ns: int | None = None,
) -> None:
    sent = await _send(
        websocket,
        lock,
        event_type="error",
        request_id=request_id,
        payload={"code": code.value, "state": state.value, "message": message[:1_024]},
        deadline=deadline,
        audio_started_ns=audio_started_ns,
    )
    metrics_recorder.record_error(VoiceErrorPayload.model_validate(sent["payload"]))


@router.websocket("/v1/query/voice")
async def voice_query(websocket: WebSocket) -> None:
    send_lock = asyncio.Lock()
    request_id = f"req_{uuid.uuid4().hex}"
    provider: SpeechToTextProvider | None = None
    consumer_task: asyncio.Task[None] | None = None
    speculative: SpeculativeRetrievalController[RetrievalResult] | None = None
    deadline: Deadline | None = None
    audio_started_ns: int | None = None
    first_partial_ns: int | None = None
    last_final_ns: int | None = None
    provider_done_ns: int | None = None
    speculative_durations_ms: list[float] = []
    audio = bytearray()
    try:
        services: VoiceServices | None = getattr(websocket.app.state, "services", None)
        if (
            services is None
            or services.orchestrator is None
            or services.stt_factory is None
        ):
            await websocket.accept()
            await _send_error(
                websocket,
                send_lock,
                request_id,
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Sarvam, the embedding model, or the retrieval index is not ready.",
                state=PipelineState.DEPENDENCY_UNAVAILABLE,
            )
            await websocket.close(code=1013)
            return
        orchestrator = services.orchestrator
        if not _voice_access_allowed(websocket, orchestrator.settings):
            await websocket.close(code=1008, reason="Voice access is not authorized")
            return
        websocket.app.state.voice_requests_started = (
            int(getattr(websocket.app.state, "voice_requests_started", 0)) + 1
        )
        await websocket.accept()

        session_expires_ns = time.perf_counter_ns() + int(
            orchestrator.settings.rag_voice_max_session_s * 1_000_000_000
        )
        start_payload, audio_started_ns = await _receive_json_frame(
            websocket,
            timeout_s=min(
                orchestrator.settings.rag_voice_idle_timeout_s,
                max(0.001, (session_expires_ns - time.perf_counter_ns()) / 1_000_000_000),
            ),
        )
        start = AudioStartEvent.model_validate(start_payload)
        request_id = start.request_id or request_id
        if start.encoding != "pcm_s16le" or start.sample_rate_hz != 16_000:
            await _send_error(
                websocket,
                send_lock,
                request_id,
                ErrorCode.VALIDATION_ERROR,
                "The realtime voice path accepts mono pcm_s16le at 16000 Hz.",
                state=PipelineState.NEEDS_REPEAT,
            )
            await websocket.close(code=1003)
            return

        provider = services.stt_factory()
        if isinstance(provider, SessionConfigurableStt):
            provider.configure_session(start.language)
        sarvam_breaker: CircuitBreaker | None = getattr(services, "sarvam_breaker", None)
        await _bounded_provider_call(
            provider.connect,
            breaker=sarvam_breaker,
            timeout_s=orchestrator.settings.rag_voice_idle_timeout_s,
            operation_name="connect",
        )
        detector = TranscriptStabilityDetector(
            TranscriptStabilityConfig(
                stable_after_ms=orchestrator.settings.speculative_stability_ms
            )
        )
        speculative = SpeculativeRetrievalController(
            SpeculativeRetrievalConfig(
                reuse_similarity_threshold=(
                    orchestrator.settings.speculative_similarity_threshold
                ),
                wait_for_speculative_ms=3,
            )
        )
        final_events: list[SttEvent] = []
        provider_done: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        async def speculative_retrieve(query: str) -> RetrievalResult:
            speculative_started_ns = time.perf_counter_ns()
            speculative_deadline = Deadline.after_ms(2_000, 1_900)
            try:
                plan = orchestrator.router.route(
                    query,
                    language_hint=(
                        start.language if start.language != Language.UNKNOWN else None
                    ),
                )
                return await orchestrator.retriever.retrieve(query, plan, speculative_deadline)
            finally:
                speculative_durations_ms.append(
                    (time.perf_counter_ns() - speculative_started_ns) / 1_000_000
                )

        async def consume_event_stream() -> None:
            nonlocal first_partial_ns, last_final_ns, provider_done_ns
            async for event in provider.events():
                if event.event_type == SttEventType.PARTIAL:
                    if first_partial_ns is None:
                        first_partial_ns = time.perf_counter_ns()
                    partial_language = (
                        start.language
                        if start.language != Language.UNKNOWN
                        else event.language
                    )
                    await _send(
                        websocket,
                        send_lock,
                        event_type="stt_partial",
                        request_id=request_id,
                        payload={
                            "text": event.text,
                            "language": partial_language.value,
                            "confidence": None,
                        },
                    )
                    stable = detector.observe(event.text)
                    if (
                        stable is not None
                        and orchestrator.settings.rag_enable_speculative_retrieval
                    ):
                        await speculative.launch(stable, speculative_retrieve)
                elif event.event_type == SttEventType.FINAL:
                    last_final_ns = time.perf_counter_ns()
                    final_events.append(event)
                elif event.event_type == SttEventType.ERROR:
                    raise SttProviderError(
                        code=str(
                            event.provider_metadata.get("provider_error_code", "error")
                        ),
                        message=event.text or "Sarvam returned an error",
                        fatal=bool(event.provider_metadata.get("fatal", True)),
                        retry=provider_error_retry(event),
                    )

        async def consume_provider_events() -> None:
            nonlocal provider_done_ns
            try:
                if sarvam_breaker is None:
                    await consume_event_stream()
                else:
                    await sarvam_breaker.call(consume_event_stream)
            except Exception as exc:
                provider_done_ns = time.perf_counter_ns()
                if not provider_done.done():
                    provider_done.set_exception(exc)
            else:
                provider_done_ns = time.perf_counter_ns()
                if not provider_done.done():
                    provider_done.set_result(None)

        consumer_task = asyncio.create_task(consume_provider_events())
        expected_sequence = 0
        while True:
            session_remaining_s = (
                session_expires_ns - time.perf_counter_ns()
            ) / 1_000_000_000
            if session_remaining_s <= 0:
                raise TimeoutError
            payload, frame_received_ns = await _receive_json_frame(
                websocket,
                timeout_s=min(
                    orchestrator.settings.rag_voice_idle_timeout_s,
                    session_remaining_s,
                ),
            )
            event_type = payload.get("type")
            if event_type == "audio_chunk":
                chunk_event = AudioChunkEvent.model_validate(payload)
                if chunk_event.sequence != expected_sequence:
                    raise ValueError(
                        f"Expected audio sequence {expected_sequence}, got {chunk_event.sequence}"
                    )
                expected_sequence += 1
                try:
                    chunk = base64.b64decode(chunk_event.audio_b64, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise ValueError("audio_b64 is not valid base64") from exc
                if not chunk:
                    raise ValueError("audio_chunk must contain at least one PCM sample")
                if len(chunk) % 2:
                    raise ValueError("pcm_s16le audio chunks must contain complete samples")
                if len(audio) + len(chunk) > MAX_AUDIO_BYTES:
                    raise ValueError("Audio exceeds the 60-second request limit")
                audio.extend(chunk)
                await _bounded_provider_call(
                    partial(provider.send_audio, chunk),
                    breaker=sarvam_breaker,
                    timeout_s=orchestrator.settings.rag_voice_idle_timeout_s,
                    operation_name="audio_send",
                )
                continue
            if event_type != "end_of_stream":
                raise ValueError(f"Unsupported voice event: {event_type}")
            EndOfStreamEvent.model_validate(payload)
            deadline = Deadline.starting_at(
                frame_received_ns,
                orchestrator.settings.rag_deadline_ms,
                orchestrator.settings.rag_fallback_at_ms,
            )
            break

        await _send(
            websocket,
            send_lock,
            event_type="pipeline_state",
            request_id=request_id,
            payload={"state": PipelineState.AUDIO_RECEIVED.value},
        )
        audio_decision = evaluate_pcm_audio(bytes(audio), sample_rate_hz=start.sample_rate_hz)
        audio.clear()
        if audio_decision.decision != GuardrailDecision.ALLOW:
            response = _audio_guardrail_response(
                request_id, start.language, audio_decision, deadline
            )
            sent = await _send(
                websocket,
                send_lock,
                event_type="answer",
                request_id=request_id,
                payload=response.model_dump(mode="json"),
                deadline=deadline,
                audio_started_ns=audio_started_ns,
            )
            metrics_recorder.record_response(QueryResponse.model_validate(sent["payload"]))
            return

        try:
            await _bounded_provider_call(
                provider.finish,
                breaker=sarvam_breaker,
                timeout_s=deadline.timeout_seconds(reserve_ms=5),
                operation_name="finish",
            )
        except SttProviderError as exc:
            if exc.code == "finish_timeout":
                raise TimeoutError from exc
            raise
        try:
            async with asyncio.timeout(deadline.timeout_seconds(reserve_ms=5)):
                await provider_done
        except TimeoutError:
            timeout_error = SttProviderError(
                code="session_end_timeout",
                message="Sarvam session.end exceeded its operation timeout",
                fatal=True,
                retry=RetryDecision(
                    retryable=True,
                    disposition=RetryDisposition.RECONNECT_NEW_SESSION,
                    reason="provider event stream timeout",
                    audio_replay_safe=False,
                ),
            )
            if sarvam_breaker is not None:
                await sarvam_breaker.record_failure(timeout_error)
            raise
        if sarvam_breaker is not None and not sarvam_breaker.reset_on_call_success:
            await sarvam_breaker.record_success()
        provider_timings: dict[str, float] = {}
        if provider_done_ns is not None:
            provider_timings["stt_finalize"] = max(
                0.0, (provider_done_ns - deadline.started_ns) / 1_000_000
            )
        if last_final_ns is not None:
            provider_timings["stt_last_final_after_end"] = max(
                0.0, (last_final_ns - deadline.started_ns) / 1_000_000
            )
        if first_partial_ns is not None and audio_started_ns is not None:
            provider_timings["stt_first_partial_from_audio_start"] = max(
                0.0, (first_partial_ns - audio_started_ns) / 1_000_000
            )
        if speculative_durations_ms:
            provider_timings["speculative_retrieval"] = sum(speculative_durations_ms)
        final_text, language = _aggregate_final_events(final_events, start.language)
        if not final_text:
            response = _stt_repeat_response(request_id, language, deadline)
            response = response.model_copy(
                update={"timings_ms": {**response.timings_ms, **provider_timings}}
            )
            sent = await _send(
                websocket,
                send_lock,
                event_type="answer",
                request_id=request_id,
                payload=response.model_dump(mode="json"),
                deadline=deadline,
                audio_started_ns=audio_started_ns,
            )
            metrics_recorder.record_response(QueryResponse.model_validate(sent["payload"]))
            return

        had_speculative_generation = speculative.active_generation_id > 0
        resolution = await speculative.resolve_speculative_only(
            final_text,
            wait_for_speculative_ms=min(3, int(deadline.remaining_ms)),
        )
        if had_speculative_generation:
            metrics_recorder.record_speculative(reused=resolution is not None)
        provider_timings["speculative_launched"] = float(had_speculative_generation)
        provider_timings["speculative_reused"] = float(resolution is not None)
        transcript = Transcript(
            text=final_text,
            language=language,
            confidence=None,
            is_final=True,
            received_ns=deadline.started_ns,
        )
        response = await orchestrator.process_transcript(
            transcript,
            deadline=deadline,
            request_id=request_id,
            retrieval_override=resolution.value if resolution is not None else None,
            record_response=False,
        )
        response = response.model_copy(
            update={"timings_ms": {**response.timings_ms, **provider_timings}}
        )
        sent = await _send(
            websocket,
            send_lock,
            event_type="answer",
            request_id=request_id,
            payload=response.model_dump(mode="json"),
            deadline=deadline,
            audio_started_ns=audio_started_ns,
        )
        metrics_recorder.record_response(QueryResponse.model_validate(sent["payload"]))
    except WebSocketDisconnect:
        return
    except (ValidationError, ValueError) as exc:
        await _send_error(
            websocket,
            send_lock,
            request_id,
            ErrorCode.VALIDATION_ERROR,
            str(exc),
            deadline=deadline,
            audio_started_ns=audio_started_ns,
        )
    except TimeoutError:
        if deadline is None:
            await _send_error(
                websocket,
                send_lock,
                request_id,
                ErrorCode.VALIDATION_ERROR,
                "The voice stream was idle for too long. Please start again.",
                state=PipelineState.NEEDS_REPEAT,
            )
        else:
            await _send_error(
                websocket,
                send_lock,
                request_id,
                ErrorCode.DEADLINE_EXCEEDED,
                "The final transcript was not available before the deadline.",
                state=PipelineState.DEADLINE_FALLBACK,
                deadline=deadline,
                audio_started_ns=audio_started_ns,
            )
    except SttProviderError as exc:
        await _send_error(
            websocket,
            send_lock,
            request_id,
            ErrorCode.SARVAM_ERROR,
            exc.message,
            state=PipelineState.DEPENDENCY_UNAVAILABLE,
            deadline=deadline,
            audio_started_ns=audio_started_ns,
        )
    except PipelineError as exc:
        await _send_error(
            websocket,
            send_lock,
            request_id,
            exc.code,
            exc.message,
            state=exc.state,
            deadline=deadline,
            audio_started_ns=audio_started_ns,
        )
    except Exception:
        await _send_error(
            websocket,
            send_lock,
            request_id,
            ErrorCode.INTERNAL_ERROR,
            "The voice request failed safely.",
            deadline=deadline,
            audio_started_ns=audio_started_ns,
        )
    finally:
        audio.clear()
        if speculative is not None:
            with contextlib.suppress(Exception):
                await speculative.close()
        if consumer_task is not None and not consumer_task.done():
            consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consumer_task
        if provider is not None:
            with contextlib.suppress(Exception):
                async with asyncio.timeout(1.0):
                    await provider.close()


def provider_error_retry(event: SttEvent) -> RetryDecision:
    return RetryDecision(
        retryable=bool(event.provider_metadata.get("retryable", False)),
        disposition=RetryDisposition.DO_NOT_RETRY,
        reason="provider event",
        audio_replay_safe=False,
    )


def _aggregate_final_events(
    events: list[SttEvent], fallback_language: Language
) -> tuple[str, Language]:
    """Join every finalized VAD utterance; the provider emits one final per pause."""

    text = " ".join(event.text.strip() for event in events if event.text.strip()).strip()
    if fallback_language != Language.UNKNOWN:
        return text, fallback_language

    language: Language = fallback_language
    for event in reversed(events):
        if event.language != Language.UNKNOWN:
            language = event.language
            break
        detected = event.provider_metadata.get("detected_language")
        language = _language_from_provider(str(detected or ""), language)
        if language != Language.UNKNOWN:
            break
    return text, language


def _audio_guardrail_response(
    request_id: str,
    language: Language,
    decision: GuardrailResult,
    deadline: Deadline,
) -> QueryResponse:
    return QueryResponse(
        request_id=request_id,
        transcript="",
        language=language,
        answer=None,
        answer_mode=AnswerMode.ABSTENTION,
        guardrail=decision,
        state=PipelineState.NEEDS_REPEAT,
        timings_ms={"total_after_final_audio": deadline.elapsed_ms},
    )


def _stt_repeat_response(
    request_id: str, language: Language, deadline: Deadline
) -> QueryResponse:
    return QueryResponse(
        request_id=request_id,
        transcript="",
        language=language,
        answer=None,
        answer_mode=AnswerMode.ABSTENTION,
        guardrail=GuardrailResult(
            decision=GuardrailDecision.NEEDS_REPEAT,
            reason=GuardrailReason.LOW_STT_CONFIDENCE,
            evidence={"provider_final_text_empty": True},
            user_message=(
                "No intelligible final transcript was available. Please repeat the question."
            ),
        ),
        state=PipelineState.NEEDS_REPEAT,
        timings_ms={"total_after_final_audio": deadline.elapsed_ms},
    )
