from __future__ import annotations

import asyncio
import base64
import contextlib
import inspect
import json
import math
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol, TypeAlias
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    field_validator,
)
from websockets.asyncio.client import connect as websocket_connect

from app.domain.enums import Language, SttEventType
from app.domain.models import SttEvent
from app.stt.base import (
    ProviderState,
    RetryDecision,
    RetryDisposition,
    RetryPolicy,
    SpeechToTextProvider,
    SttProviderError,
)

SARVAM_REALTIME_ENDPOINT = "wss://api.sarvam.ai/speech-to-text-realtime/ws"
SARVAM_REALTIME_MODEL: Literal["saaras:v3-realtime"] = "saaras:v3-realtime"
SARVAM_API_KEY_HEADER = "API-SUBSCRIPTION-KEY"
SARVAM_BROWSER_SUBPROTOCOL_PREFIX = "api-subscription-key."


class SarvamLanguageCode(StrEnum):
    AUTO = "auto"
    ENGLISH = "en-IN"
    HINDI = "hi-IN"
    BENGALI = "bn-IN"
    KANNADA = "kn-IN"
    MALAYALAM = "ml-IN"
    MARATHI = "mr-IN"
    ODIA = "or-IN"
    PUNJABI = "pa-IN"
    TAMIL = "ta-IN"
    TELUGU = "te-IN"
    GUJARATI = "gu-IN"
    ASSAMESE = "as-IN"
    URDU = "ur-IN"
    NEPALI = "ne-IN"
    KONKANI = "kok-IN"
    KASHMIRI = "ks-IN"
    SINDHI = "sd-IN"
    SANSKRIT = "sa-IN"
    SANTALI = "sat-IN"
    MANIPURI = "mni-IN"
    BODO = "brx-IN"
    MAITHILI = "mai-IN"
    DOGRI = "doi-IN"


class SarvamStreamType(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    SIMULATED = "simulated"


class SarvamMode(StrEnum):
    TRANSCRIBE = "transcribe"
    TRANSLATE = "translate"
    VERBATIM = "verbatim"
    TRANSLIT = "translit"
    CODEMIX = "codemix"


class SarvamEndpointing(StrEnum):
    VAD = "vad"
    MANUAL = "manual"


class SarvamEncoding(StrEnum):
    LINEAR16 = "linear16"
    LINEAR32 = "linear32"
    MULAW = "mulaw"
    ALAW = "alaw"


class SarvamRealtimeConfig(BaseModel):
    """Verified query and local transport settings for Saaras realtime beta."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr
    endpoint: str = SARVAM_REALTIME_ENDPOINT
    language_code: SarvamLanguageCode = SarvamLanguageCode.AUTO
    model: Literal["saaras:v3-realtime"] = SARVAM_REALTIME_MODEL
    stream_type: SarvamStreamType = SarvamStreamType.FAST
    mode: SarvamMode = SarvamMode.TRANSCRIBE
    prompt: str | None = None
    endpointing: SarvamEndpointing = SarvamEndpointing.VAD
    encoding: SarvamEncoding = SarvamEncoding.LINEAR16
    sample_rate: Literal[8000, 16000] = 16000
    return_timestamps: bool = True
    threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    prefix_padding_ms: int = Field(default=300, ge=0)
    silence_duration_ms: int = Field(default=500, ge=0)
    min_speech_duration_ms: int = Field(default=250, ge=0)
    connect_timeout_s: float = Field(default=5.0, gt=0.0, le=60.0)
    session_begin_timeout_s: float = Field(default=5.0, gt=0.0, le=60.0)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Sarvam API key must not be empty")
        return value

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "wss" or not parsed.netloc:
            raise ValueError("Sarvam realtime endpoint must be an absolute wss:// URL")
        return value

    def query_parameters(self) -> dict[str, str]:
        params = {
            "language_code": self.language_code.value,
            "model": self.model,
            "stream_type": self.stream_type.value,
            "mode": self.mode.value,
            "endpointing": self.endpointing.value,
            "encoding": self.encoding.value,
            "sample_rate": str(self.sample_rate),
            "return_timestamps": str(self.return_timestamps).lower(),
            "threshold": str(self.threshold),
            "prefix_padding_ms": str(self.prefix_padding_ms),
            "silence_duration_ms": str(self.silence_duration_ms),
            "min_speech_duration_ms": str(self.min_speech_duration_ms),
        }
        if self.prompt is not None:
            params["prompt"] = self.prompt
        return params

    def websocket_url(self) -> str:
        parsed = urlsplit(self.endpoint)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update(self.query_parameters())
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
        )

    def authentication_headers(self) -> dict[str, str]:
        return {SARVAM_API_KEY_HEADER: self.api_key.get_secret_value()}


def _coerce_wire_float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid float")
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("value is not a valid float") from exc
    if not math.isfinite(converted):
        raise ValueError("float must be finite")
    return converted


WireFloat = Annotated[float, BeforeValidator(_coerce_wire_float)]
Probability = Annotated[WireFloat, Field(ge=0.0, le=1.0)]


class SarvamWireModel(BaseModel):
    """Forward-compatible wire model while still validating known fields."""

    model_config = ConfigDict(extra="allow")


class SarvamResolvedConfig(SarvamWireModel):
    model: str | None = None
    language_code: str | None = None
    encoding: str | None = None
    sample_rate: int | None = None
    stream_type: str | None = None
    mode: str | None = None
    prompt: str | None = None
    turn_detection: str | None = None
    threshold: WireFloat | None = None
    prefix_padding_ms: int | None = None
    silence_duration_ms: int | None = None
    min_speech_duration_ms: int | None = None
    return_timestamps: bool | None = None


class SarvamSessionBegin(SarvamWireModel):
    event: Literal["session.begin"]
    request_id: str
    config: SarvamResolvedConfig | None = None


class SarvamVadSpeechStart(SarvamWireModel):
    event: Literal["vad.speech_start"]
    utterance_idx: int = Field(ge=0)
    confidence: Probability | None = None


class SarvamVadSpeechEnd(SarvamWireModel):
    event: Literal["vad.speech_end"]
    utterance_idx: int = Field(ge=0)
    confidence: Probability | None = None


class SarvamTranscriptPartial(SarvamWireModel):
    event: Literal["transcript.partial"]
    utterance_idx: int = Field(ge=0)
    text: str
    language: str | None = None


class SarvamTranscriptFinal(SarvamWireModel):
    event: Literal["transcript.final"]
    utterance_idx: int = Field(ge=0)
    text: str
    language: str | None = None
    language_confidence: Probability | None = None
    start_s: WireFloat | None = Field(default=None, ge=0.0)
    end_s: WireFloat | None = Field(default=None, ge=0.0)


class SarvamConfigUpdated(SarvamWireModel):
    event: Literal["config.updated"]
    applied: list[str]


class SarvamPong(SarvamWireModel):
    event: Literal["pong"]


class SarvamSessionEnd(SarvamWireModel):
    event: Literal["session.end"]
    request_id: str
    total_duration_s: WireFloat | None = Field(default=None, ge=0.0)
    total_utterances: int | None = Field(default=None, ge=0)
    audio_duration_s: WireFloat | None = Field(default=None, ge=0.0)


class SarvamErrorEvent(SarvamWireModel):
    event: Literal["error"]
    code: str
    is_fatal: bool
    message: str
    status_code: int | None = None


SarvamServerEvent: TypeAlias = Annotated[
    SarvamSessionBegin
    | SarvamVadSpeechStart
    | SarvamVadSpeechEnd
    | SarvamTranscriptPartial
    | SarvamTranscriptFinal
    | SarvamConfigUpdated
    | SarvamPong
    | SarvamSessionEnd
    | SarvamErrorEvent,
    Field(discriminator="event"),
]
_SERVER_EVENT_ADAPTER: TypeAdapter[SarvamServerEvent] = TypeAdapter(SarvamServerEvent)


class SarvamAudioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["audio_input"] = "audio_input"
    audio: str


class SarvamSpeechStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["speech_start"] = "speech_start"


class SarvamSpeechEnd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["speech_end"] = "speech_end"


class SarvamFlush(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["flush"] = "flush"


class SarvamConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["config.update"] = "config.update"
    language_code: SarvamLanguageCode | None = None
    prompt: str | None = None
    mode: SarvamMode | None = None
    stream_type: Literal[SarvamStreamType.FAST, SarvamStreamType.BALANCED] | None = None
    endpointing: SarvamEndpointing | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    silence_duration_ms: int | None = Field(default=None, ge=0)
    min_speech_duration_ms: int | None = Field(default=None, ge=0)


class SarvamEnd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["end"] = "end"


class SarvamPing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["ping"] = "ping"


class WebSocketLike(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...

    async def close(self, code: int = 1000, reason: str = "") -> None: ...


Connector: TypeAlias = Callable[..., Awaitable[WebSocketLike] | Any]
Sleeper: TypeAlias = Callable[[float], Awaitable[None]]


def parse_sarvam_server_event(
    payload: str | bytes | bytearray | Mapping[str, Any],
) -> SarvamServerEvent:
    """Parse and validate a Sarvam event, coercing documented float strings."""

    try:
        if isinstance(payload, Mapping):
            decoded: Any = dict(payload)
        else:
            if isinstance(payload, bytes | bytearray):
                payload = bytes(payload).decode("utf-8")
            decoded = json.loads(payload)
        return _SERVER_EVENT_ADAPTER.validate_python(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise SttProviderError(
            code="invalid_server_event",
            message="Sarvam returned an invalid realtime event",
            fatal=True,
            retry=RetryDecision(
                retryable=False,
                disposition=RetryDisposition.DO_NOT_RETRY,
                reason="invalid provider payload cannot be replayed safely",
            ),
            provider_metadata={"validation_error": str(exc)},
        ) from exc


def classify_sarvam_retry(
    *,
    close_code: int | None = None,
    status_code: int | None = None,
    error_code: str | None = None,
) -> RetryDecision:
    """Classify failures without claiming that sent audio can be replayed."""

    if error_code == "invalid_config":
        return RetryDecision(
            retryable=False,
            disposition=RetryDisposition.DO_NOT_RETRY,
            reason="invalid config is non-fatal and the previous config remains active",
        )
    if close_code == 1011 or status_code in {500, 503}:
        return RetryDecision(
            retryable=True,
            disposition=RetryDisposition.RETRY_WITH_BACKOFF,
            reason="Sarvam internal or unavailable error",
        )
    if close_code == 1008 or status_code == 408:
        return RetryDecision(
            retryable=True,
            disposition=RetryDisposition.RECONNECT_NEW_SESSION,
            reason="reconnect after an inactivity or timeout close",
        )
    if close_code == 1003 or status_code in {401, 403, 429}:
        return RetryDecision(
            retryable=False,
            disposition=RetryDisposition.DO_NOT_RETRY,
            reason="credential, quota, or rate-limit state must be resolved first",
        )
    if close_code == 4000 or status_code in {400, 413}:
        return RetryDecision(
            retryable=False,
            disposition=RetryDisposition.DO_NOT_RETRY,
            reason="request parameters or beta account access must be corrected",
        )
    return RetryDecision(
        retryable=False,
        disposition=RetryDisposition.DO_NOT_RETRY,
        reason="Sarvam does not document this failure as retryable",
    )


def _domain_language(code: str | SarvamLanguageCode | None) -> Language:
    value = code.value if isinstance(code, SarvamLanguageCode) else code
    if value is None:
        return Language.UNKNOWN
    return {
        SarvamLanguageCode.HINDI.value: Language.HINDI,
        SarvamLanguageCode.ENGLISH.value: Language.ENGLISH,
        SarvamLanguageCode.MARATHI.value: Language.MARATHI,
    }.get(value, Language.UNKNOWN)


def _close_details(exc: BaseException) -> tuple[int | None, str]:
    code = getattr(exc, "code", None)
    reason = getattr(exc, "reason", "") or str(exc)
    received = getattr(exc, "rcvd", None)
    if code is None and received is not None:
        code = getattr(received, "code", None)
        reason = getattr(received, "reason", reason)
    return code if isinstance(code, int) else None, str(reason)


class SarvamRealtimeProvider(SpeechToTextProvider):
    """Raw WebSocket adapter for Sarvam's beta ``saaras:v3-realtime`` API."""

    def __init__(
        self,
        config: SarvamRealtimeConfig,
        *,
        connector: Connector = websocket_connect,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        self.config = config
        self._connector = connector
        self._sleeper = sleeper
        self._state = ProviderState.NEW
        self._socket: WebSocketLike | None = None
        self._send_lock = asyncio.Lock()
        self._request_id: str | None = None
        self._session_begin: SarvamSessionBegin | None = None
        self._session_end: SarvamSessionEnd | None = None
        self._last_vad_event: SarvamVadSpeechStart | SarvamVadSpeechEnd | None = None
        self._last_config_update: SarvamConfigUpdated | None = None
        self._audio_chunks_sent = 0
        self._effective_language_code = config.language_code
        self._effective_mode = config.mode
        self._effective_endpointing = config.endpointing
        self._pending_config_updates: deque[dict[str, Any]] = deque()

    @property
    def state(self) -> ProviderState:
        return self._state

    @property
    def request_id(self) -> str | None:
        return self._request_id

    @property
    def session_begin(self) -> SarvamSessionBegin | None:
        return self._session_begin

    @property
    def session_end(self) -> SarvamSessionEnd | None:
        return self._session_end

    @property
    def last_vad_event(self) -> SarvamVadSpeechStart | SarvamVadSpeechEnd | None:
        return self._last_vad_event

    @property
    def audio_chunks_sent(self) -> int:
        return self._audio_chunks_sent

    def configure_session(self, language: Language) -> None:
        """Bind a fresh provider to the language selected for this voice session.

        Saaras ``codemix`` preserves Indic text in its native script while retaining
        embedded English words.  Auto-detected sessions use the same output mode so
        Hindi speech is not unnecessarily romanized.  This must run before connect
        because these values are part of the provider WebSocket URL.
        """

        if self._state is not ProviderState.NEW:
            raise RuntimeError("Sarvam session language must be configured before connect")

        if language in {Language.HINDI, Language.CODE_MIXED}:
            language_code = SarvamLanguageCode.HINDI
            mode = SarvamMode.CODEMIX
        elif language is Language.ENGLISH:
            language_code = SarvamLanguageCode.ENGLISH
            mode = SarvamMode.TRANSCRIBE
        elif language is Language.UNKNOWN:
            language_code = SarvamLanguageCode.AUTO
            mode = SarvamMode.CODEMIX
        else:
            return

        self.config = self.config.model_copy(
            update={"language_code": language_code, "mode": mode}
        )
        self._effective_language_code = language_code
        self._effective_mode = mode

    async def connect(self) -> None:
        if self._state is ProviderState.CONNECTED:
            return
        if self._state is not ProviderState.NEW:
            raise RuntimeError(f"cannot connect Sarvam STT from state {self._state}")

        self._state = ProviderState.CONNECTING
        attempts = 0
        last_error: SttProviderError | None = None
        while self.config.retry_policy.permits_another_attempt(attempts):
            attempts += 1
            try:
                await self._connect_once()
                self._state = ProviderState.CONNECTED
                return
            except asyncio.CancelledError:
                self._state = ProviderState.FAILED
                raise
            except SttProviderError as exc:
                last_error = exc
            except Exception as exc:  # transport-specific exceptions vary by websockets version
                last_error = self._transport_error(exc, during_connect=True)

            await self._discard_socket()
            if (
                last_error is None
                or not last_error.retryable
                or not self.config.retry_policy.permits_another_attempt(attempts)
            ):
                self._state = ProviderState.FAILED
                if last_error is None:
                    raise RuntimeError("Sarvam connection failed without an error")
                raise last_error
            await self._sleeper(self.config.retry_policy.delay_after(attempts))

        self._state = ProviderState.FAILED
        if last_error is None:
            raise RuntimeError("Sarvam connection retry budget was exhausted")
        raise last_error

    async def _connect_once(self) -> None:
        try:
            pending = self._connector(
                self.config.websocket_url(),
                additional_headers=self.config.authentication_headers(),
                open_timeout=self.config.connect_timeout_s,
            )
            if not inspect.isawaitable(pending):
                raise TypeError("WebSocket connector did not return an awaitable")
            self._socket = await asyncio.wait_for(pending, timeout=self.config.connect_timeout_s)
            socket = self._socket
            if socket is None:
                raise RuntimeError("WebSocket connector returned no socket")
            raw_event = await asyncio.wait_for(
                socket.recv(), timeout=self.config.session_begin_timeout_s
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise self._transport_error(exc, during_connect=True) from exc

        event = parse_sarvam_server_event(raw_event)
        if isinstance(event, SarvamErrorEvent):
            raise self._provider_error(event)
        if not isinstance(event, SarvamSessionBegin):
            raise SttProviderError(
                code="missing_session_begin",
                message=f"expected session.begin, received {event.event}",
                fatal=True,
                retry=RetryDecision(
                    retryable=False,
                    disposition=RetryDisposition.DO_NOT_RETRY,
                    reason="unexpected provider event order",
                ),
            )
        self._session_begin = event
        self._request_id = event.request_id
        self._apply_session_config(event.config)

    async def send_audio(self, audio: bytes) -> None:
        if self._state is not ProviderState.CONNECTED:
            raise RuntimeError("Sarvam STT is not connected")
        if not isinstance(audio, bytes):
            raise TypeError("audio must be bytes")
        if not audio:
            raise ValueError("audio chunk must not be empty")
        encoded = base64.b64encode(audio).decode("ascii")
        await self._send_model(SarvamAudioInput(audio=encoded))
        self._audio_chunks_sent += 1

    async def send_speech_start(self) -> None:
        self._require_manual_endpointing("speech_start")
        await self._send_model(SarvamSpeechStart())

    async def send_speech_end(self) -> None:
        self._require_manual_endpointing("speech_end")
        await self._send_model(SarvamSpeechEnd())

    async def flush(self) -> None:
        self._require_manual_endpointing("flush")
        await self._send_model(SarvamFlush())

    async def update_config(self, update: SarvamConfigUpdate) -> None:
        pending = update.model_dump(mode="python", exclude_none=True, exclude={"event"})
        self._pending_config_updates.append(pending)
        try:
            await self._send_model(update)
        except BaseException:
            if self._pending_config_updates and self._pending_config_updates[-1] is pending:
                self._pending_config_updates.pop()
            raise

    async def ping(self) -> None:
        await self._send_model(SarvamPing())

    async def finish(self) -> None:
        if self._state in {ProviderState.ENDING, ProviderState.CLOSED, ProviderState.FAILED}:
            return
        if self._state is not ProviderState.CONNECTED:
            raise RuntimeError("Sarvam STT is not connected")
        await self._send_model(SarvamEnd())
        self._state = ProviderState.ENDING

    def _require_manual_endpointing(self, event: str) -> None:
        if self._effective_endpointing is not SarvamEndpointing.MANUAL:
            raise RuntimeError(f"{event} is only valid with endpointing=manual")

    async def _send_model(self, model: BaseModel) -> None:
        if self._state not in {ProviderState.CONNECTED, ProviderState.ENDING}:
            raise RuntimeError("Sarvam STT is not connected")
        if self._socket is None:
            raise RuntimeError("Sarvam WebSocket is unavailable")
        message = json.dumps(
            model.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            async with self._send_lock:
                await self._socket.send(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._state = ProviderState.FAILED
            raise self._transport_error(exc, during_connect=False) from exc

    async def _iterate_events(self) -> AsyncIterator[SttEvent]:
        if self._state not in {ProviderState.CONNECTED, ProviderState.ENDING}:
            raise RuntimeError("Sarvam STT is not connected")
        if self._socket is None:
            raise RuntimeError("Sarvam WebSocket is unavailable")

        while self._state in {ProviderState.CONNECTED, ProviderState.ENDING}:
            try:
                raw_event = await self._socket.recv()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                close_code, _ = _close_details(exc)
                if close_code in {1000, 1001}:
                    self._state = ProviderState.CLOSED
                    return
                self._state = ProviderState.FAILED
                raise self._transport_error(exc, during_connect=False) from exc

            try:
                event = parse_sarvam_server_event(raw_event)
            except SttProviderError:
                self._state = ProviderState.FAILED
                raise
            if isinstance(event, SarvamSessionBegin):
                self._session_begin = event
                self._request_id = event.request_id
                self._apply_session_config(event.config)
                continue
            if isinstance(event, SarvamVadSpeechStart | SarvamVadSpeechEnd):
                self._last_vad_event = event
                continue
            if isinstance(event, SarvamConfigUpdated):
                self._last_config_update = event
                self._apply_config_updated(event)
                continue
            if isinstance(event, SarvamPong):
                continue
            if isinstance(event, SarvamSessionEnd):
                self._session_end = event
                self._state = ProviderState.CLOSED
                return
            if isinstance(event, SarvamTranscriptPartial):
                yield self._transcript_event(event, is_final=False)
                continue
            if isinstance(event, SarvamTranscriptFinal):
                yield self._transcript_event(event, is_final=True)
                continue
            if isinstance(event, SarvamErrorEvent):
                error = self._provider_error(event)
                if event.code == "invalid_config" and self._pending_config_updates:
                    self._pending_config_updates.popleft()
                yield error.as_event()
                if event.is_fatal:
                    self._state = ProviderState.FAILED
                    raise error

    def events(self) -> AsyncIterator[SttEvent]:
        return self._iterate_events()

    def _transcript_event(
        self, event: SarvamTranscriptPartial | SarvamTranscriptFinal, *, is_final: bool
    ) -> SttEvent:
        metadata: dict[str, Any] = {
            "provider": "sarvam",
            "provider_event": event.event,
            "request_id": self._request_id,
            "utterance_idx": event.utterance_idx,
            "model": SARVAM_REALTIME_MODEL,
            "recognition_confidence_available": False,
        }
        if event.language is not None:
            metadata["detected_language"] = event.language
        if isinstance(event, SarvamTranscriptFinal):
            if event.language_confidence is not None:
                metadata["language_confidence"] = event.language_confidence
            if event.start_s is not None:
                metadata["start_s"] = event.start_s
            if event.end_s is not None:
                metadata["end_s"] = event.end_s

        language = _domain_language(event.language)
        if language is Language.UNKNOWN:
            if self._effective_mode is SarvamMode.CODEMIX:
                language = Language.CODE_MIXED
            else:
                language = _domain_language(self._effective_language_code)
        return SttEvent(
            event_type=SttEventType.FINAL if is_final else SttEventType.PARTIAL,
            text=event.text,
            language=language,
            confidence=None,
            provider_metadata=metadata,
        )

    def _apply_session_config(self, resolved: SarvamResolvedConfig | None) -> None:
        if resolved is None:
            return
        if resolved.language_code is not None:
            with contextlib.suppress(ValueError):
                self._effective_language_code = SarvamLanguageCode(resolved.language_code)
        if resolved.mode is not None:
            with contextlib.suppress(ValueError):
                self._effective_mode = SarvamMode(resolved.mode)
        if resolved.turn_detection is not None:
            with contextlib.suppress(ValueError):
                self._effective_endpointing = SarvamEndpointing(resolved.turn_detection)

    def _apply_config_updated(self, event: SarvamConfigUpdated) -> None:
        if not self._pending_config_updates:
            return
        pending = self._pending_config_updates.popleft()
        for key in event.applied:
            value = pending.get(key)
            if key == "language_code" and isinstance(value, SarvamLanguageCode):
                self._effective_language_code = value
            elif key == "mode" and isinstance(value, SarvamMode):
                self._effective_mode = value
            elif key == "endpointing" and isinstance(value, SarvamEndpointing):
                self._effective_endpointing = value

    def _provider_error(self, event: SarvamErrorEvent) -> SttProviderError:
        retry = classify_sarvam_retry(
            status_code=event.status_code,
            error_code=event.code,
        )
        return SttProviderError(
            code=event.code,
            message=event.message,
            fatal=event.is_fatal,
            retry=retry,
            status_code=event.status_code,
            provider_metadata={"request_id": self._request_id},
        )

    def _transport_error(self, exc: BaseException, *, during_connect: bool) -> SttProviderError:
        close_code, reason = _close_details(exc)
        retry = classify_sarvam_retry(close_code=close_code)
        if close_code is None and isinstance(exc, OSError | TimeoutError):
            retry = RetryDecision(
                retryable=True,
                disposition=RetryDisposition.RETRY_WITH_BACKOFF,
                reason="transient connection or timeout failure",
            )
        if not during_connect and self._audio_chunks_sent:
            retry = retry.model_copy(
                update={
                    "reason": f"{retry.reason}; in-flight audio cannot be replayed safely",
                    "audio_replay_safe": False,
                }
            )
        return SttProviderError(
            code="sarvam_connection_error",
            message=reason or "Sarvam realtime connection failed",
            fatal=True,
            retry=retry,
            close_code=close_code,
            provider_metadata={
                "request_id": self._request_id,
                "during_connect": during_connect,
                "audio_chunks_sent": self._audio_chunks_sent,
            },
        )

    async def _discard_socket(self) -> None:
        socket, self._socket = self._socket, None
        if socket is None:
            return
        try:
            await socket.close(code=1000, reason="connection attempt failed")
        except Exception:
            return

    async def close(self) -> None:
        if self._state is ProviderState.CLOSED:
            return
        socket = self._socket
        if socket is None:
            self._state = ProviderState.CLOSED
            return
        if self._state is ProviderState.CONNECTED:
            with contextlib.suppress(RuntimeError, SttProviderError):
                await self.finish()
        try:
            await socket.close(code=1000, reason="client shutdown")
        finally:
            self._socket = None
            self._state = ProviderState.CLOSED
