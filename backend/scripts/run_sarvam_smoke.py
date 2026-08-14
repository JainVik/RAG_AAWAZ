from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import math
import os
import sys
import tempfile
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal, Protocol

import numpy as np
from pydantic import SecretStr, ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.enums import SttEventType  # noqa: E402
from app.domain.models import SttEvent  # noqa: E402
from app.services import SarvamSmokeArtifact  # noqa: E402
from app.stt.base import ProviderState, SttProviderError  # noqa: E402
from app.stt.sarvam_realtime import (  # noqa: E402
    SARVAM_REALTIME_ENDPOINT,
    SARVAM_REALTIME_MODEL,
    SarvamEncoding,
    SarvamLanguageCode,
    SarvamRealtimeConfig,
    SarvamRealtimeProvider,
    SarvamStreamType,
)
from app.stt.stability import normalize_transcript  # noqa: E402

SMOKE_SCHEMA_VERSION: Final[Literal[1]] = 1
API_KEY_ENV = "SARVAM_API_KEY"
PCM_PATH_ENV = "SARVAM_SMOKE_PCM_PATH"
SAMPLE_RATE_HZ: Final[Literal[16000]] = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
BYTES_PER_SECOND = SAMPLE_RATE_HZ * CHANNELS * SAMPLE_WIDTH_BYTES
DEFAULT_CHUNK_MS = 100
DEFAULT_MIN_DURATION_MS = 500
DEFAULT_MAX_DURATION_MS = 30_000
DEFAULT_COMPLETION_TIMEOUT_S = 20.0

_CONTAINER_SIGNATURES = (b"RIFF", b"OggS", b"fLaC", b"ID3")


class SarvamSmokeError(RuntimeError):
    """A smoke prerequisite or success condition was not satisfied."""


class SmokeProvider(Protocol):
    @property
    def state(self) -> ProviderState: ...

    @property
    def request_id(self) -> str | None: ...

    @property
    def session_begin(self) -> object | None: ...

    @property
    def session_end(self) -> object | None: ...

    @property
    def audio_chunks_sent(self) -> int: ...

    async def connect(self) -> None: ...

    async def send_audio(self, audio: bytes) -> None: ...

    async def finish(self) -> None: ...

    def events(self) -> AsyncIterator[SttEvent]: ...

    async def close(self) -> None: ...


ProviderFactory = Callable[[SarvamRealtimeConfig], SmokeProvider]


@dataclass(frozen=True, slots=True)
class SarvamSmokeConfig:
    api_key: SecretStr
    pcm_path: Path
    output_path: Path
    endpoint: str = SARVAM_REALTIME_ENDPOINT
    language_code: SarvamLanguageCode = SarvamLanguageCode.AUTO
    chunk_ms: int = DEFAULT_CHUNK_MS
    min_duration_ms: int = DEFAULT_MIN_DURATION_MS
    max_duration_ms: int = DEFAULT_MAX_DURATION_MS
    completion_timeout_s: float = DEFAULT_COMPLETION_TIMEOUT_S
    pace_audio: bool = True

    def __post_init__(self) -> None:
        if not self.api_key.get_secret_value().strip():
            raise ValueError("Sarvam API key must not be empty")
        if not 20 <= self.chunk_ms <= 1_000:
            raise ValueError("chunk_ms must be between 20 and 1000")
        if self.min_duration_ms < 1:
            raise ValueError("min_duration_ms must be positive")
        if self.max_duration_ms < self.min_duration_ms:
            raise ValueError("max_duration_ms must be at least min_duration_ms")
        if self.completion_timeout_s <= 0:
            raise ValueError("completion_timeout_s must be positive")
        if self.endpoint != SARVAM_REALTIME_ENDPOINT:
            raise ValueError(
                "Credentialed readiness evidence must use the official Sarvam endpoint"
            )
        try:
            same_path = self.pcm_path.resolve() == self.output_path.resolve()
        except OSError:
            same_path = self.pcm_path.absolute() == self.output_path.absolute()
        if same_path:
            raise ValueError("Smoke evidence output must not overwrite the PCM fixture")


@dataclass(frozen=True, slots=True)
class ValidatedPcm:
    data: bytes
    sha256: str
    duration_ms: float
    peak_amplitude: int
    rms_amplitude: float


def smoke_config_from_environment(
    environment: Mapping[str, str],
    *,
    pcm_path: Path | None = None,
    output_path: Path | None = None,
    language_code: SarvamLanguageCode | None = None,
    chunk_ms: int = DEFAULT_CHUNK_MS,
    completion_timeout_s: float = DEFAULT_COMPLETION_TIMEOUT_S,
) -> SarvamSmokeConfig:
    """Resolve explicit live-smoke inputs without placing a key on the command line."""

    raw_key = environment.get(API_KEY_ENV, "").strip()
    if not raw_key:
        raise SarvamSmokeError(
            f"{API_KEY_ENV} is required for the opt-in credentialed Sarvam smoke"
        )
    raw_path = str(pcm_path) if pcm_path is not None else environment.get(PCM_PATH_ENV, "")
    if not raw_path.strip():
        raise SarvamSmokeError(
            f"An explicit raw PCM fixture is required via --pcm or {PCM_PATH_ENV}"
        )
    resolved_output = output_path or Path(
        environment.get("RAG_DATA_DIR", "data")
    ) / "sarvam-smoke.json"
    endpoint = environment.get("SARVAM_WS_URL", SARVAM_REALTIME_ENDPOINT).strip()
    if not endpoint:
        endpoint = SARVAM_REALTIME_ENDPOINT

    if language_code is None:
        raw_language = environment.get("SARVAM_LANGUAGE_CODE", "auto").strip() or "auto"
        try:
            language_code = SarvamLanguageCode(raw_language)
        except ValueError as exc:
            raise SarvamSmokeError(
                f"Unsupported SARVAM_LANGUAGE_CODE for realtime smoke: {raw_language!r}"
            ) from exc

    return SarvamSmokeConfig(
        api_key=SecretStr(raw_key),
        pcm_path=Path(raw_path),
        output_path=resolved_output,
        endpoint=endpoint,
        language_code=language_code,
        chunk_ms=chunk_ms,
        completion_timeout_s=completion_timeout_s,
    )


def validate_pcm_fixture(config: SarvamSmokeConfig) -> ValidatedPcm:
    """Validate raw mono signed little-endian PCM interpreted at exactly 16 kHz."""

    path = config.pcm_path
    if not path.exists():
        raise SarvamSmokeError(f"Raw PCM fixture does not exist: {path}")
    if not path.is_file():
        raise SarvamSmokeError(f"Raw PCM fixture is not a regular file: {path}")
    size = path.stat().st_size
    if size == 0:
        raise SarvamSmokeError("Raw PCM fixture is empty")
    if size % SAMPLE_WIDTH_BYTES:
        raise SarvamSmokeError(
            "Raw PCM fixture byte length must align to signed 16-bit samples"
        )
    duration_ms = size / BYTES_PER_SECOND * 1_000
    if duration_ms < config.min_duration_ms:
        raise SarvamSmokeError(
            f"Raw PCM fixture is too short: {duration_ms:.1f} ms; "
            f"minimum is {config.min_duration_ms} ms"
        )
    if duration_ms > config.max_duration_ms:
        raise SarvamSmokeError(
            f"Raw PCM fixture is too long: {duration_ms:.1f} ms; "
            f"maximum is {config.max_duration_ms} ms"
        )

    data = path.read_bytes()
    if any(data.startswith(signature) for signature in _CONTAINER_SIGNATURES):
        raise SarvamSmokeError(
            "Fixture appears to contain an audio container header; provide headerless "
            "mono pcm_s16le bytes"
        )
    samples = np.frombuffer(data, dtype="<i2")
    peak = int(np.max(np.abs(samples.astype(np.int32))))
    if peak == 0:
        raise SarvamSmokeError("Raw PCM fixture contains only digital silence")
    rms = float(math.sqrt(float(np.mean(samples.astype(np.float64) ** 2))))
    return ValidatedPcm(
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
        duration_ms=duration_ms,
        peak_amplitude=peak,
        rms_amplitude=rms,
    )


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode(
                    "utf-8"
                )
            )
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


async def _collect_events(provider: SmokeProvider) -> tuple[list[SttEvent], int]:
    events: list[SttEvent] = []
    provider_errors = 0
    async for event in provider.events():
        events.append(event)
        if event.event_type is SttEventType.ERROR:
            provider_errors += 1
    return events, provider_errors


def _default_provider_factory(config: SarvamRealtimeConfig) -> SmokeProvider:
    return SarvamRealtimeProvider(config)


def _build_evidence(
    config: SarvamSmokeConfig,
    pcm: ValidatedPcm,
    provider: SmokeProvider,
    events: Sequence[SttEvent],
) -> SarvamSmokeArtifact:
    finals = [
        event
        for event in events
        if event.event_type is SttEventType.FINAL and event.text.strip()
    ]
    if not finals:
        raise SarvamSmokeError("No nonempty final transcript is available for evidence")
    normalized_final = normalize_transcript(finals[-1].text)
    request_id = provider.request_id
    if not request_id:
        raise SarvamSmokeError("Sarvam session did not provide a provider request_id")
    if provider.session_begin is None:
        raise SarvamSmokeError("Sarvam session.begin was not observed")
    if provider.session_end is None:
        raise SarvamSmokeError("Sarvam session.end was not observed")
    return SarvamSmokeArtifact(
        schema_version=SMOKE_SCHEMA_VERSION,
        success=True,
        endpoint=config.endpoint,
        model=SARVAM_REALTIME_MODEL,
        provider_request_id=request_id,
        observed_session_begin=True,
        observed_final=True,
        observed_session_end=True,
        normalized_final_transcript=normalized_final,
        audio_sha256=pcm.sha256,
        created_at=datetime.now(UTC),
    )


async def run_sarvam_smoke(
    config: SarvamSmokeConfig,
    *,
    provider_factory: ProviderFactory | None = None,
) -> SarvamSmokeArtifact:
    """Run one credentialed production-adapter session and atomically save evidence."""

    pcm = await asyncio.to_thread(validate_pcm_fixture, config)
    try:
        provider_config = SarvamRealtimeConfig(
            api_key=config.api_key,
            endpoint=config.endpoint,
            language_code=config.language_code,
            model=SARVAM_REALTIME_MODEL,
            stream_type=SarvamStreamType.FAST,
            encoding=SarvamEncoding.LINEAR16,
            sample_rate=SAMPLE_RATE_HZ,
            return_timestamps=True,
        )
    except ValidationError as exc:
        raise SarvamSmokeError("Invalid Sarvam realtime smoke configuration") from exc

    create_provider = provider_factory or _default_provider_factory
    provider = create_provider(provider_config)
    collector: asyncio.Task[tuple[list[SttEvent], int]] | None = None
    events: list[SttEvent] = []
    provider_errors = 0
    chunks_sent = 0
    chunk_bytes = int(BYTES_PER_SECOND * config.chunk_ms / 1_000)
    chunk_bytes -= chunk_bytes % SAMPLE_WIDTH_BYTES
    try:
        await provider.connect()
        collector = asyncio.create_task(_collect_events(provider))
        for offset in range(0, len(pcm.data), chunk_bytes):
            chunk = pcm.data[offset : offset + chunk_bytes]
            await provider.send_audio(chunk)
            chunks_sent += 1
            if config.pace_audio:
                await asyncio.sleep(len(chunk) / BYTES_PER_SECOND)
        await provider.finish()
        try:
            events, provider_errors = await asyncio.wait_for(
                collector, timeout=config.completion_timeout_s
            )
        except TimeoutError as exc:
            raise SarvamSmokeError(
                "Timed out waiting for Sarvam to finalize the realtime session"
            ) from exc
    finally:
        if collector is not None and not collector.done():
            collector.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await collector
        await provider.close()

    if provider_errors:
        raise SarvamSmokeError(
            f"Sarvam emitted {provider_errors} provider error event(s) during smoke"
        )
    finals = [
        event
        for event in events
        if event.event_type is SttEventType.FINAL and event.text.strip()
    ]
    if not finals:
        raise SarvamSmokeError(
            "Sarvam smoke completed without a nonempty final transcript"
        )
    if provider.audio_chunks_sent != chunks_sent:
        raise SarvamSmokeError(
            "Production adapter audio chunk count did not match the smoke sender"
        )

    evidence = _build_evidence(config, pcm, provider, events)
    evidence_payload = evidence.model_dump(mode="json")
    serialized = json.dumps(evidence_payload, ensure_ascii=False, sort_keys=True)
    secret = config.api_key.get_secret_value()
    if secret and secret in serialized:
        raise SarvamSmokeError("Refusing to persist smoke evidence containing a credential")
    await asyncio.to_thread(_atomic_write_json, config.output_path, evidence_payload)
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run an opt-in real Sarvam smoke with headerless 16 kHz mono pcm_s16le. "
            "SARVAM_API_KEY is read only from the environment."
        )
    )
    parser.add_argument(
        "--pcm",
        type=Path,
        help=f"Explicit raw fixture path (or set {PCM_PATH_ENV}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Evidence JSON path; defaults to RAG_DATA_DIR/sarvam-smoke.json.",
    )
    parser.add_argument(
        "--language-code",
        choices=[code.value for code in SarvamLanguageCode],
    )
    parser.add_argument("--chunk-ms", type=int, default=DEFAULT_CHUNK_MS)
    parser.add_argument(
        "--completion-timeout-s",
        type=float,
        default=DEFAULT_COMPLETION_TIMEOUT_S,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    language = (
        SarvamLanguageCode(args.language_code) if args.language_code is not None else None
    )
    try:
        config = smoke_config_from_environment(
            os.environ,
            pcm_path=args.pcm,
            output_path=args.output,
            language_code=language,
            chunk_ms=args.chunk_ms,
            completion_timeout_s=args.completion_timeout_s,
        )
        evidence = asyncio.run(run_sarvam_smoke(config))
    except SttProviderError as exc:
        print(
            "Sarvam smoke failed: provider_error "
            f"code={exc.code} retryable={str(exc.retryable).lower()}",
            file=sys.stderr,
        )
        return 1
    except (SarvamSmokeError, OSError, ValueError) as exc:
        print(f"Sarvam smoke failed: {exc}", file=sys.stderr)
        return 1
    console_result = evidence.model_dump(
        mode="json", exclude={"normalized_final_transcript"}
    )
    console_result["normalized_final_transcript_present"] = True
    print(json.dumps(console_result, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Evidence: {config.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
