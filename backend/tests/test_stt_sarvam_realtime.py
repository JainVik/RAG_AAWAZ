from __future__ import annotations

import json
from collections import deque
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from app.domain.enums import Language, SttEventType
from app.stt.base import ProviderState, RetryPolicy, SttProviderError
from app.stt.sarvam_realtime import (
    SARVAM_API_KEY_HEADER,
    SARVAM_REALTIME_ENDPOINT,
    SARVAM_REALTIME_MODEL,
    SarvamConfigUpdate,
    SarvamEndpointing,
    SarvamMode,
    SarvamRealtimeConfig,
    SarvamRealtimeProvider,
    SarvamStreamType,
    SarvamTranscriptFinal,
    classify_sarvam_retry,
    parse_sarvam_server_event,
)


class FakeClosed(Exception):
    def __init__(self, code: int, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class FakeSocket:
    def __init__(self, incoming: list[str | bytes | BaseException]) -> None:
        self.incoming = deque(incoming)
        self.sent: list[str] = []
        self.closed: tuple[int, str] | None = None

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str | bytes:
        item = self.incoming.popleft()
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = (code, reason)


class RecordingConnector:
    def __init__(self, sockets: list[FakeSocket]) -> None:
        self.sockets = deque(sockets)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, url: str, **kwargs: Any) -> FakeSocket:
        self.calls.append((url, kwargs))
        return self.sockets.popleft()


def message(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_connect_uses_verified_endpoint_query_and_header() -> None:
    socket = FakeSocket(
        [
            message(
                {
                    "event": "session.begin",
                    "request_id": "sarvam-request-1",
                    "config": {"threshold": "0.3", "turn_detection": "vad"},
                }
            )
        ]
    )
    connector = RecordingConnector([socket])
    config = SarvamRealtimeConfig(api_key="test-secret", language_code="auto")
    provider = SarvamRealtimeProvider(config, connector=connector)

    await provider.connect()

    assert provider.state is ProviderState.CONNECTED
    assert provider.request_id == "sarvam-request-1"
    url, kwargs = connector.calls[0]
    parsed = urlsplit(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == SARVAM_REALTIME_ENDPOINT
    query = parse_qs(parsed.query)
    assert query["language_code"] == ["auto"]
    assert query["model"] == [SARVAM_REALTIME_MODEL]
    assert query["stream_type"] == ["fast"]
    assert query["encoding"] == ["linear16"]
    assert query["sample_rate"] == ["16000"]
    assert query["return_timestamps"] == ["true"]
    assert kwargs["additional_headers"] == {SARVAM_API_KEY_HEADER: "test-secret"}

    await provider.send_audio(b"\x00\x01")
    audio_message = json.loads(socket.sent[0])
    assert audio_message == {"event": "audio_input", "audio": "AAE="}

    await provider.finish()
    assert json.loads(socket.sent[-1]) == {"event": "end"}
    assert provider.state is ProviderState.ENDING


@pytest.mark.asyncio
async def test_partial_and_final_have_no_invented_recognition_confidence() -> None:
    socket = FakeSocket(
        [
            message({"event": "session.begin", "request_id": "req-2"}),
            message(
                {
                    "event": "transcript.partial",
                    "utterance_idx": 4,
                    "text": "गोवा कब",
                    "language": "hi-IN",
                }
            ),
            message(
                {
                    "event": "transcript.final",
                    "utterance_idx": 4,
                    "text": "गोवा राज्य कब बना?",
                    "language": "hi-IN",
                    "language_confidence": "0.91",
                    "start_s": "0.25",
                    "end_s": 1.75,
                }
            ),
            message(
                {
                    "event": "session.end",
                    "request_id": "req-2",
                    "audio_duration_s": "1.80",
                    "total_duration_s": 2.0,
                    "total_utterances": 1,
                }
            ),
        ]
    )
    provider = SarvamRealtimeProvider(
        SarvamRealtimeConfig(api_key="test-secret"),
        connector=RecordingConnector([socket]),
    )
    await provider.connect()

    events = [event async for event in provider.events()]

    assert [event.event_type for event in events] == [SttEventType.PARTIAL, SttEventType.FINAL]
    assert all(event.confidence is None for event in events)
    assert events[0].language is Language.HINDI
    assert events[1].provider_metadata["language_confidence"] == pytest.approx(0.91)
    assert events[1].provider_metadata["start_s"] == pytest.approx(0.25)
    assert events[1].provider_metadata["end_s"] == pytest.approx(1.75)
    assert events[1].provider_metadata["recognition_confidence_available"] is False
    assert provider.session_end is not None
    assert provider.session_end.audio_duration_s == pytest.approx(1.8)
    assert provider.state is ProviderState.CLOSED


def test_server_float_strings_are_coerced_but_transcript_confidence_is_absent() -> None:
    event = parse_sarvam_server_event(
        {
            "event": "transcript.final",
            "utterance_idx": 0,
            "text": "hello",
            "language_confidence": "0.75",
            "start_s": "1.25",
            "end_s": 2,
        }
    )
    assert isinstance(event, SarvamTranscriptFinal)
    assert event.language_confidence == pytest.approx(0.75)
    assert event.start_s == pytest.approx(1.25)
    assert not hasattr(event, "confidence")


def test_invalid_server_event_is_structured() -> None:
    with pytest.raises(SttProviderError) as caught:
        parse_sarvam_server_event({"event": "transcript.final", "utterance_idx": 0})
    assert caught.value.code == "invalid_server_event"
    assert not caught.value.retryable


@pytest.mark.asyncio
async def test_connect_retries_1011_with_bounded_backoff_before_audio() -> None:
    first = FakeSocket([FakeClosed(1011, "temporary internal failure")])
    second = FakeSocket([message({"event": "session.begin", "request_id": "req-retry"})])
    connector = RecordingConnector([first, second])
    sleeps: list[float] = []

    async def sleeper(delay: float) -> None:
        sleeps.append(delay)

    provider = SarvamRealtimeProvider(
        SarvamRealtimeConfig(
            api_key="test-secret",
            retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.01, max_delay_s=0.1),
        ),
        connector=connector,
        sleeper=sleeper,
    )

    await provider.connect()

    assert len(connector.calls) == 2
    assert sleeps == [pytest.approx(0.01)]
    assert first.closed is not None
    assert provider.request_id == "req-retry"


@pytest.mark.asyncio
async def test_connect_does_not_retry_credential_quota_close() -> None:
    connector = RecordingConnector([FakeSocket([FakeClosed(1003, "invalid key")])])
    provider = SarvamRealtimeProvider(
        SarvamRealtimeConfig(
            api_key="test-secret",
            retry_policy=RetryPolicy(max_attempts=3),
        ),
        connector=connector,
    )

    with pytest.raises(SttProviderError) as caught:
        await provider.connect()

    assert caught.value.close_code == 1003
    assert not caught.value.retryable
    assert len(connector.calls) == 1


@pytest.mark.asyncio
async def test_fatal_structured_error_is_emitted_then_raised() -> None:
    socket = FakeSocket(
        [
            message({"event": "session.begin", "request_id": "req-error"}),
            message(
                {
                    "event": "error",
                    "code": "backend_unavailable",
                    "is_fatal": True,
                    "message": "service unavailable",
                    "status_code": 503,
                }
            ),
        ]
    )
    provider = SarvamRealtimeProvider(
        SarvamRealtimeConfig(api_key="test-secret"),
        connector=RecordingConnector([socket]),
    )
    await provider.connect()
    iterator = provider.events()

    error_event = await anext(iterator)
    assert error_event.event_type is SttEventType.ERROR
    assert error_event.provider_metadata["retryable"] is True
    assert error_event.provider_metadata["audio_replay_safe"] is False
    with pytest.raises(SttProviderError):
        await anext(iterator)
    assert provider.state is ProviderState.FAILED


def test_config_update_rejects_simulated_transition() -> None:
    with pytest.raises(ValidationError):
        SarvamConfigUpdate(stream_type=SarvamStreamType.SIMULATED)


def test_retry_classification_is_conservative() -> None:
    assert classify_sarvam_retry(close_code=1011).retryable
    assert classify_sarvam_retry(close_code=1008).retryable
    assert not classify_sarvam_retry(close_code=1003).retryable
    assert not classify_sarvam_retry(close_code=4000).retryable
    assert not classify_sarvam_retry(error_code="invalid_config").retryable


@pytest.mark.asyncio
async def test_manual_turn_events_are_guarded_by_endpointing() -> None:
    socket = FakeSocket([message({"event": "session.begin", "request_id": "req-manual"})])
    provider = SarvamRealtimeProvider(
        SarvamRealtimeConfig(api_key="test-secret", endpointing=SarvamEndpointing.VAD),
        connector=RecordingConnector([socket]),
    )
    await provider.connect()
    with pytest.raises(RuntimeError, match="endpointing=manual"):
        await provider.send_speech_start()


@pytest.mark.asyncio
async def test_live_config_ack_updates_effective_mode_and_endpointing() -> None:
    socket = FakeSocket(
        [
            message({"event": "session.begin", "request_id": "req-update"}),
            message({"event": "config.updated", "applied": ["mode", "endpointing"]}),
            message(
                {
                    "event": "transcript.final",
                    "utterance_idx": 0,
                    "text": "मेरा phone",
                }
            ),
        ]
    )
    provider = SarvamRealtimeProvider(
        SarvamRealtimeConfig(api_key="test-secret"),
        connector=RecordingConnector([socket]),
    )
    await provider.connect()
    await provider.update_config(
        SarvamConfigUpdate(mode=SarvamMode.CODEMIX, endpointing=SarvamEndpointing.MANUAL)
    )

    final_event = await anext(provider.events())
    await provider.send_speech_start()

    assert final_event.language is Language.CODE_MIXED
    assert json.loads(socket.sent[0]) == {
        "event": "config.update",
        "mode": "codemix",
        "endpointing": "manual",
    }
    assert json.loads(socket.sent[1]) == {"event": "speech_start"}


def test_codemix_mode_maps_final_without_detected_language() -> None:
    provider = SarvamRealtimeProvider(
        SarvamRealtimeConfig(api_key="test-secret", mode=SarvamMode.CODEMIX),
        connector=RecordingConnector([]),
    )
    event = SarvamTranscriptFinal(event="transcript.final", utterance_idx=0, text="मेरा phone")
    normalized = provider._transcript_event(event, is_final=True)
    assert normalized.language is Language.CODE_MIXED
    assert normalized.confidence is None
