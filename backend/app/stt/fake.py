from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import SttEvent
from app.stt.base import (
    ProviderState,
    RetryDecision,
    RetryDisposition,
    SpeechToTextProvider,
    SttProviderError,
)


class FakeSttConfig(BaseModel):
    """Deterministic controls for provider-independent tests."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    emit_interval_s: float = Field(default=0.0, ge=0.0, le=10.0)
    fail_connect: bool = False
    fail_after_audio_chunks: int | None = Field(default=None, ge=0)
    retain_audio: bool = False


class FakeSpeechToTextProvider(SpeechToTextProvider):
    """Scripted STT provider that never silently substitutes for Sarvam."""

    def __init__(
        self,
        scripted_events: Iterable[SttEvent] = (),
        *,
        config: FakeSttConfig | None = None,
    ) -> None:
        self.config = config or FakeSttConfig()
        self._scripted_events = tuple(scripted_events)
        self._state = ProviderState.NEW
        self._audio_chunks = 0
        self._audio_bytes = 0
        self._retained_audio: list[bytes] = []
        self._finished = asyncio.Event()

    @property
    def state(self) -> ProviderState:
        return self._state

    @property
    def audio_chunks_received(self) -> int:
        return self._audio_chunks

    @property
    def audio_bytes_received(self) -> int:
        return self._audio_bytes

    @property
    def retained_audio(self) -> tuple[bytes, ...]:
        return tuple(self._retained_audio)

    async def connect(self) -> None:
        if self._state is ProviderState.CONNECTED:
            return
        if self._state is not ProviderState.NEW:
            raise RuntimeError(f"cannot connect fake STT from state {self._state}")
        if self.config.fail_connect:
            self._state = ProviderState.FAILED
            raise SttProviderError(
                code="fake_connect_failure",
                message="configured fake STT connection failure",
                fatal=True,
                retry=RetryDecision(
                    retryable=False,
                    disposition=RetryDisposition.DO_NOT_RETRY,
                    reason="deterministic fake failure",
                ),
            )
        self._state = ProviderState.CONNECTED

    async def send_audio(self, audio: bytes) -> None:
        if self._state is not ProviderState.CONNECTED:
            raise RuntimeError("fake STT is not connected")
        if not isinstance(audio, bytes):
            raise TypeError("audio must be bytes")
        if not audio:
            raise ValueError("audio chunk must not be empty")
        limit = self.config.fail_after_audio_chunks
        if limit is not None and self._audio_chunks >= limit:
            self._state = ProviderState.FAILED
            raise SttProviderError(
                code="fake_audio_failure",
                message="configured fake STT audio failure",
                fatal=True,
                retry=RetryDecision(
                    retryable=False,
                    disposition=RetryDisposition.DO_NOT_RETRY,
                    reason="deterministic fake failure",
                ),
            )
        self._audio_chunks += 1
        self._audio_bytes += len(audio)
        if self.config.retain_audio:
            self._retained_audio.append(bytes(audio))

    async def finish(self) -> None:
        if self._state in {ProviderState.CLOSED, ProviderState.FAILED}:
            return
        if self._state is not ProviderState.CONNECTED:
            raise RuntimeError("fake STT is not connected")
        self._state = ProviderState.ENDING
        self._finished.set()

    def push_event(self, event: SttEvent) -> None:
        """Append an event before iteration for ad-hoc test fixtures."""

        if self._state in {ProviderState.CLOSED, ProviderState.FAILED}:
            raise RuntimeError("fake STT session is closed")
        self._scripted_events += (event,)

    async def _iterate_events(self) -> AsyncIterator[SttEvent]:
        if self._state is ProviderState.NEW:
            raise RuntimeError("fake STT is not connected")
        for event in self._scripted_events:
            if self.config.emit_interval_s:
                await asyncio.sleep(self.config.emit_interval_s)
            yield event
        if self._state is ProviderState.ENDING:
            self._state = ProviderState.CLOSED

    def events(self) -> AsyncIterator[SttEvent]:
        return self._iterate_events()

    async def close(self) -> None:
        self._finished.set()
        self._state = ProviderState.CLOSED
