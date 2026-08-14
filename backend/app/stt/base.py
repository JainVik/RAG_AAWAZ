from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import SttEventType
from app.domain.models import SttEvent


class ProviderState(StrEnum):
    """Lifecycle shared by concrete speech-to-text providers."""

    NEW = "new"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ENDING = "ending"
    CLOSED = "closed"
    FAILED = "failed"


class RetryDisposition(StrEnum):
    """How a caller may recover from a provider failure."""

    DO_NOT_RETRY = "do_not_retry"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    RECONNECT_NEW_SESSION = "reconnect_new_session"


class RetryDecision(BaseModel):
    """A bounded, explicit retry classification.

    ``audio_replay_safe`` is deliberately false for Sarvam realtime failures:
    the protocol has no resume token or documented audio replay mechanism.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    retryable: bool
    disposition: RetryDisposition
    reason: str
    audio_replay_safe: bool = False


class RetryPolicy(BaseModel):
    """Small retry budget used only where replay is known to be safe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_attempts: int = Field(default=2, ge=1, le=5)
    base_delay_s: float = Field(default=0.1, ge=0.0, le=5.0)
    max_delay_s: float = Field(default=1.0, ge=0.0, le=30.0)

    @model_validator(mode="after")
    def validate_delays(self) -> RetryPolicy:
        if self.max_delay_s < self.base_delay_s:
            raise ValueError("max_delay_s must be at least base_delay_s")
        return self

    def permits_another_attempt(self, completed_attempts: int) -> bool:
        """Return whether another attempt fits after ``completed_attempts``."""

        return completed_attempts < self.max_attempts

    def delay_after(self, completed_attempts: int) -> float:
        """Return deterministic exponential backoff bounded by ``max_delay_s``."""

        exponent = max(0, completed_attempts - 1)
        return float(min(self.max_delay_s, self.base_delay_s * (2**exponent)))


class SttProviderError(Exception):
    """Structured provider error suitable for harness retry/fallback decisions."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        fatal: bool,
        retry: RetryDecision,
        close_code: int | None = None,
        status_code: int | None = None,
        provider_metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.fatal = fatal
        self.retry = retry
        self.close_code = close_code
        self.status_code = status_code
        self.provider_metadata = provider_metadata or {}

    @property
    def retryable(self) -> bool:
        return self.retry.retryable

    def as_event(self) -> SttEvent:
        metadata: dict[str, Any] = {
            "provider_error_code": self.code,
            "fatal": self.fatal,
            "retryable": self.retryable,
            "retry_disposition": self.retry.disposition.value,
            "audio_replay_safe": self.retry.audio_replay_safe,
        }
        if self.close_code is not None:
            metadata["close_code"] = self.close_code
        if self.status_code is not None:
            metadata["status_code"] = self.status_code
        metadata.update(self.provider_metadata)
        return SttEvent(
            event_type=SttEventType.ERROR,
            text=self.message,
            confidence=None,
            provider_metadata=metadata,
        )

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class SpeechToTextProvider(ABC):
    """Interactive STT session used by the backend voice WebSocket.

    Sending audio and consuming ``events()`` are intentionally independent so
    callers can process partial transcripts while more audio is arriving.
    """

    @property
    @abstractmethod
    def state(self) -> ProviderState:
        raise NotImplementedError

    @abstractmethod
    async def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_audio(self, audio: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    async def finish(self) -> None:
        """Gracefully finalize pending audio and end the provider session."""

        raise NotImplementedError

    @abstractmethod
    def events(self) -> AsyncIterator[SttEvent]:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

    async def __aenter__(self) -> SpeechToTextProvider:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        await self.close()
