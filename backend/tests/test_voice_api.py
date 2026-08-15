from __future__ import annotations

import asyncio
import base64
import struct
import threading
import time
from collections.abc import AsyncIterator, Iterable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.domain.enums import Language, SttEventType
from app.domain.models import CorpusDocument, SttEvent
from app.embeddings.dense import HashingDenseEncoder
from app.embeddings.sparse_char_ngram import SparseCharNgramEncoder
from app.generation.grounded_generator import ExtractiveGroundedGenerator
from app.harness.circuit_breaker import CircuitBreaker, CircuitState
from app.harness.orchestrator import PipelineOrchestrator
from app.ingestion.chunk_factory import ChunkFactory
from app.main import create_app
from app.retrieval.hybrid import HybridRetriever, RetrievalResult
from app.retrieval.in_memory import InMemoryHybridIndex
from app.stt.fake import FakeSpeechToTextProvider


class StallingFinishProvider(FakeSpeechToTextProvider):
    async def finish(self) -> None:
        await asyncio.Event().wait()


class StallingConnectProvider(FakeSpeechToTextProvider):
    async def connect(self) -> None:
        await asyncio.Event().wait()


class StallingSessionEndProvider(FakeSpeechToTextProvider):
    async def events(self) -> AsyncIterator[SttEvent]:
        await asyncio.Event().wait()
        if False:
            yield SttEvent(event_type=SttEventType.FINAL, text="unreachable")


class SessionConfigurableFakeProvider(FakeSpeechToTextProvider):
    def __init__(self, events: Iterable[SttEvent]) -> None:
        super().__init__(events)
        self.configured_language: Language | None = None

    def configure_session(self, language: Language) -> None:
        self.configured_language = language


class VoiceTestServices:
    def __init__(
        self,
        orchestrator: PipelineOrchestrator,
        events: Iterable[SttEvent] | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        partial = SttEvent(
            event_type=SttEventType.PARTIAL,
            text="When was Goa formed",
            language=Language.ENGLISH,
        )
        final = SttEvent(
            event_type=SttEventType.FINAL,
            text="When was Goa formed",
            language=Language.ENGLISH,
        )
        scripted = tuple(events) if events is not None else (partial, partial, final)
        self.stt_factory = lambda: FakeSpeechToTextProvider(scripted)

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def readiness(self) -> dict[str, Any]:
        return {"status": "ready", "checks": {}}


async def make_services(events: Iterable[SttEvent] | None = None) -> VoiceTestServices:
    parent = CorpusDocument(
        canonical_doc_id="doc",
        parent_id="doc",
        english_text="Goa became a state in 1987.",
        translated_text="गोवा 1987 में राज्य बना।",
        translation_language="hin_Deva",
    )
    chunks = ChunkFactory().all_enabled(parent, enable_semantic=False)
    index = InMemoryHybridIndex(
        chunks, HashingDenseEncoder(), SparseCharNgramEncoder(dimensions=10_007)
    )
    await index.initialize()
    retriever = HybridRetriever(index, index)
    settings = Settings(
        rag_target_unique_passages=10,
        rag_development_passages=1,
        rag_deadline_ms=1_000,
        rag_fallback_at_ms=900,
        min_answer_score=0.0,
        min_score_margin=0.0,
        min_evidence_agreement=0.0,
        speculative_stability_ms=0,
    )
    orchestrator = PipelineOrchestrator(
        settings=settings,
        retriever=retriever,
        generator=ExtractiveGroundedGenerator(),
    )
    return VoiceTestServices(orchestrator, events)


def test_voice_websocket_uses_final_stt_and_same_grounded_harness() -> None:
    services = asyncio.run(make_services())
    pcm = struct.pack("<8000h", *([1_000] * 8_000))
    with (
        TestClient(create_app(services)) as client,
        client.websocket_connect("/v1/query/voice") as socket,
    ):
        socket.send_json(
            {
                "type": "start",
                "version": "1",
                "request_id": "req_voice_test",
                "encoding": "pcm_s16le",
                "sample_rate_hz": 16_000,
                "language": "en",
            }
        )
        socket.send_json(
            {
                "type": "audio_chunk",
                "version": "1",
                "sequence": 0,
                "audio_b64": base64.b64encode(pcm).decode("ascii"),
            }
        )
        socket.send_json({"type": "end_of_stream", "version": "1"})

        answer = None
        for _ in range(10):
            event = socket.receive_json()
            if event["type"] == "answer":
                answer = event["payload"]
                break
        assert answer is not None
        assert answer["transcript"] == "When was Goa formed"
        assert answer["state"] == "COMPLETED"
        assert answer["citations"]


def test_voice_websocket_explicit_language_overrides_provider_language() -> None:
    events = (
        SttEvent(
            event_type=SttEventType.FINAL,
            text="गोवा राज्य",
            language=Language.UNKNOWN,
            provider_metadata={"utterance_idx": 0, "detected_language": "en-IN"},
        ),
        SttEvent(
            event_type=SttEventType.FINAL,
            text="कब बना",
            language=Language.ENGLISH,
            provider_metadata={"utterance_idx": 1, "detected_language": "en-IN"},
        ),
    )
    services = asyncio.run(make_services(events))
    provider = SessionConfigurableFakeProvider(events)
    services.stt_factory = lambda: provider
    pcm = struct.pack("<8000h", *([1_000] * 8_000))
    with (
        TestClient(create_app(services)) as client,
        client.websocket_connect("/v1/query/voice") as socket,
    ):
        socket.send_json(
            {
                "type": "start",
                "version": "1",
                "encoding": "pcm_s16le",
                "sample_rate_hz": 16_000,
                "language": "hi",
            }
        )
        socket.send_json(
            {
                "type": "audio_chunk",
                "version": "1",
                "sequence": 0,
                "audio_b64": base64.b64encode(pcm).decode("ascii"),
            }
        )
        socket.send_json({"type": "end_of_stream", "version": "1"})

        answer = None
        for _ in range(10):
            event = socket.receive_json()
            if event["type"] == "answer":
                answer = event["payload"]
                break
        assert answer is not None
        assert answer["transcript"] == "गोवा राज्य कब बना"
        assert answer["language"] == "hi"
        assert answer["state"] == "COMPLETED"
        assert provider.configured_language is Language.HINDI


class CancelAwareRetriever:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.cancelled = threading.Event()

    async def retrieve(self, query: str, plan: object, deadline: object) -> RetrievalResult:
        del query, plan, deadline
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        raise AssertionError("unreachable")


def test_voice_disconnect_cancels_inflight_speculative_retrieval() -> None:
    partial = SttEvent(
        event_type=SttEventType.PARTIAL,
        text="When was Goa formed",
        language=Language.ENGLISH,
    )
    services = asyncio.run(make_services((partial, partial)))
    retriever = CancelAwareRetriever()
    assert services.orchestrator is not None
    services.orchestrator.retriever = retriever  # type: ignore[assignment]

    with (
        TestClient(create_app(services)) as client,
        client.websocket_connect("/v1/query/voice") as socket,
    ):
        socket.send_json(
            {
                "type": "start",
                "version": "1",
                "encoding": "pcm_s16le",
                "sample_rate_hz": 16_000,
                "language": "en",
            }
        )
        event = socket.receive_json()
        assert event["type"] == "stt_partial"
        assert retriever.started.wait(timeout=1.0)

    assert retriever.cancelled.wait(timeout=1.0)


def test_voice_provider_finish_is_bounded_by_final_audio_deadline() -> None:
    services = asyncio.run(make_services())
    assert services.orchestrator is not None
    services.orchestrator.settings.rag_deadline_ms = 80
    services.orchestrator.settings.rag_fallback_at_ms = 60
    services.stt_factory = StallingFinishProvider
    breaker = CircuitBreaker("sarvam", failure_threshold=1)
    services.sarvam_breaker = breaker
    pcm = struct.pack("<8000h", *([1_000] * 8_000))

    started = time.perf_counter()
    with (
        TestClient(create_app(services)) as client,
        client.websocket_connect("/v1/query/voice") as socket,
    ):
        socket.send_json(
            {
                "type": "start",
                "version": "1",
                "encoding": "pcm_s16le",
                "sample_rate_hz": 16_000,
                "language": "en",
            }
        )
        socket.send_json(
            {
                "type": "audio_chunk",
                "version": "1",
                "sequence": 0,
                "audio_b64": base64.b64encode(pcm).decode("ascii"),
            }
        )
        socket.send_json({"type": "end_of_stream", "version": "1"})

        terminal = None
        for _ in range(5):
            event = socket.receive_json()
            if event["type"] == "error":
                terminal = event
                break

    assert terminal is not None
    assert terminal["payload"]["code"] == "DEADLINE_EXCEEDED"
    assert terminal["payload"]["state"] == "DEADLINE_FALLBACK"
    assert breaker.state == CircuitState.OPEN
    assert time.perf_counter() - started < 1.0


def test_voice_missing_session_end_opens_sarvam_breaker() -> None:
    services = asyncio.run(make_services())
    assert services.orchestrator is not None
    services.orchestrator.settings.rag_deadline_ms = 80
    services.orchestrator.settings.rag_fallback_at_ms = 60
    services.stt_factory = StallingSessionEndProvider
    breaker = CircuitBreaker("sarvam", failure_threshold=1)
    services.sarvam_breaker = breaker
    pcm = struct.pack("<8000h", *([1_000] * 8_000))

    with (
        TestClient(create_app(services)) as client,
        client.websocket_connect("/v1/query/voice") as socket,
    ):
        socket.send_json(
            {
                "type": "start",
                "version": "1",
                "encoding": "pcm_s16le",
                "sample_rate_hz": 16_000,
                "language": "en",
            }
        )
        socket.send_json(
            {
                "type": "audio_chunk",
                "version": "1",
                "sequence": 0,
                "audio_b64": base64.b64encode(pcm).decode("ascii"),
            }
        )
        socket.send_json({"type": "end_of_stream", "version": "1"})

        terminal = None
        for _ in range(5):
            event = socket.receive_json()
            if event["type"] == "error":
                terminal = event
                break

    assert terminal is not None
    assert terminal["payload"]["code"] == "DEADLINE_EXCEEDED"
    assert breaker.state == CircuitState.OPEN


def test_voice_provider_connect_has_a_bounded_dependency_timeout() -> None:
    services = asyncio.run(make_services())
    assert services.orchestrator is not None
    services.orchestrator.settings.rag_voice_idle_timeout_s = 0.05
    services.stt_factory = StallingConnectProvider

    started = time.perf_counter()
    with (
        TestClient(create_app(services)) as client,
        client.websocket_connect("/v1/query/voice") as socket,
    ):
        socket.send_json(
            {
                "type": "start",
                "version": "1",
                "encoding": "pcm_s16le",
                "sample_rate_hz": 16_000,
                "language": "en",
            }
        )
        error = socket.receive_json()

    assert error["type"] == "error"
    assert error["payload"]["code"] == "SARVAM_ERROR"
    assert error["payload"]["state"] == "DEPENDENCY_UNAVAILABLE"
    assert time.perf_counter() - started < 1.0


def test_voice_open_sarvam_circuit_returns_structured_dependency_error() -> None:
    services = asyncio.run(make_services())
    breaker = CircuitBreaker("sarvam", recovery_timeout_s=60.0)
    breaker.state = CircuitState.OPEN
    breaker.opened_at = time.monotonic()
    services.sarvam_breaker = breaker

    with (
        TestClient(create_app(services)) as client,
        client.websocket_connect("/v1/query/voice") as socket,
    ):
        socket.send_json(
            {
                "type": "start",
                "version": "1",
                "encoding": "pcm_s16le",
                "sample_rate_hz": 16_000,
                "language": "en",
            }
        )
        error = socket.receive_json()

    assert error["type"] == "error"
    assert error["payload"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert error["payload"]["state"] == "DEPENDENCY_UNAVAILABLE"


def test_voice_bearer_token_is_checked_before_accept() -> None:
    services = asyncio.run(make_services())
    assert services.orchestrator is not None
    services.orchestrator.settings.rag_voice_api_token = SecretStr("test-secret")

    with (
        TestClient(create_app(services)) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/v1/query/voice"),
    ):
        pass

    assert exc_info.value.code == 1008


def test_voice_browser_origin_is_rejected_unless_allowlisted() -> None:
    services = asyncio.run(make_services())

    with (
        TestClient(create_app(services)) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(
            "/v1/query/voice", headers={"origin": "https://untrusted.example"}
        ),
    ):
        pass

    assert exc_info.value.code == 1008


def test_voice_protocol_version_is_required() -> None:
    services = asyncio.run(make_services())

    with (
        TestClient(create_app(services)) as client,
        client.websocket_connect("/v1/query/voice") as socket,
    ):
        socket.send_json(
            {
                "type": "start",
                "encoding": "pcm_s16le",
                "sample_rate_hz": 16_000,
                "language": "en",
            }
        )
        error = socket.receive_json()

    assert error["type"] == "error"
    assert error["version"] == "1"
    assert error["payload"]["code"] == "VALIDATION_ERROR"


def test_voice_total_session_time_is_bounded_independently_of_idle_frames() -> None:
    services = asyncio.run(make_services())
    assert services.orchestrator is not None
    services.orchestrator.settings.rag_voice_idle_timeout_s = 1.0
    services.orchestrator.settings.rag_voice_max_session_s = 0.05

    with (
        TestClient(create_app(services)) as client,
        client.websocket_connect("/v1/query/voice") as socket,
    ):
        socket.send_json(
            {
                "type": "start",
                "version": "1",
                "encoding": "pcm_s16le",
                "sample_rate_hz": 16_000,
                "language": "en",
            }
        )
        time.sleep(0.08)
        error = None
        for _ in range(5):
            event = socket.receive_json()
            if event["type"] == "error":
                error = event
                break

    assert error is not None
    assert error["type"] == "error"
    assert error["payload"]["code"] == "VALIDATION_ERROR"
    assert error["payload"]["state"] == "NEEDS_REPEAT"
