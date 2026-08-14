from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.domain.enums import Language, SttEventType
from app.domain.models import SttEvent
from app.services import DefaultServices, load_sarvam_smoke_artifact
from app.stt.base import ProviderState
from app.stt.sarvam_realtime import (
    SarvamEncoding,
    SarvamRealtimeConfig,
    SarvamStreamType,
)
from scripts.run_sarvam_smoke import (
    API_KEY_ENV,
    PCM_PATH_ENV,
    SarvamSmokeConfig,
    SarvamSmokeError,
    run_sarvam_smoke,
    smoke_config_from_environment,
    validate_pcm_fixture,
)


class FakeSmokeProvider:
    def __init__(self, config: SarvamRealtimeConfig, transcript: str = "Goa is a state") -> None:
        self.config = config
        self.transcript = transcript
        self._state = ProviderState.NEW
        self._request_id = "fixture-request"
        self._session_begin: object | None = None
        self._session_end: object | None = None
        self._audio_chunks_sent = 0
        self.chunk_lengths: list[int] = []

    @property
    def state(self) -> ProviderState:
        return self._state

    @property
    def request_id(self) -> str | None:
        return self._request_id

    @property
    def session_begin(self) -> object | None:
        return self._session_begin

    @property
    def session_end(self) -> object | None:
        return self._session_end

    @property
    def audio_chunks_sent(self) -> int:
        return self._audio_chunks_sent

    async def connect(self) -> None:
        self._session_begin = SimpleNamespace(request_id=self._request_id)
        self._state = ProviderState.CONNECTED

    async def send_audio(self, audio: bytes) -> None:
        assert self._state is ProviderState.CONNECTED
        self.chunk_lengths.append(len(audio))
        self._audio_chunks_sent += 1

    async def finish(self) -> None:
        self._state = ProviderState.ENDING

    async def _events(self) -> AsyncIterator[SttEvent]:
        yield SttEvent(
            event_type=SttEventType.PARTIAL,
            text="Goa is",
            language=Language.ENGLISH,
        )
        yield SttEvent(
            event_type=SttEventType.FINAL,
            text=self.transcript,
            language=Language.ENGLISH,
            provider_metadata={"detected_language": "en-IN"},
        )
        self._session_end = SimpleNamespace(
            audio_duration_s=0.6,
            total_duration_s=0.8,
            total_utterances=1,
        )
        self._state = ProviderState.CLOSED

    def events(self) -> AsyncIterator[SttEvent]:
        return self._events()

    async def close(self) -> None:
        self._state = ProviderState.CLOSED


def _pcm_fixture(path: Path, *, duration_ms: int = 600) -> bytes:
    sample_count = int(16_000 * duration_ms / 1_000)
    timeline = np.arange(sample_count, dtype=np.float64) / 16_000
    samples = (np.sin(2 * np.pi * 440 * timeline) * 4_000).astype("<i2")
    data = samples.tobytes()
    path.write_bytes(data)
    return data


def test_environment_gate_requires_key_and_explicit_pcm_path(tmp_path) -> None:
    with pytest.raises(SarvamSmokeError, match=API_KEY_ENV):
        smoke_config_from_environment({})
    with pytest.raises(SarvamSmokeError, match=PCM_PATH_ENV):
        smoke_config_from_environment({API_KEY_ENV: "secret"})

    pcm_path = tmp_path / "speech.pcm"
    config = smoke_config_from_environment(
        {
            API_KEY_ENV: "secret",
            PCM_PATH_ENV: str(pcm_path),
            "RAG_DATA_DIR": str(tmp_path / "evidence"),
        }
    )
    assert config.pcm_path == pcm_path
    assert config.output_path == tmp_path / "evidence" / "sarvam-smoke.json"
    assert str(config.api_key) == "**********"


def test_pcm_validation_rejects_container_silence_and_misalignment(tmp_path) -> None:
    output = tmp_path / "evidence.json"

    wav = tmp_path / "fixture.wav"
    wav.write_bytes(b"RIFF" + b"\x01\x00" * 8_000)
    with pytest.raises(SarvamSmokeError, match="container header"):
        validate_pcm_fixture(
            SarvamSmokeConfig(
                api_key=SecretStr("secret"), pcm_path=wav, output_path=output
            )
        )

    silence = tmp_path / "silence.pcm"
    silence.write_bytes(b"\x00\x00" * 8_000)
    with pytest.raises(SarvamSmokeError, match="digital silence"):
        validate_pcm_fixture(
            SarvamSmokeConfig(
                api_key=SecretStr("secret"), pcm_path=silence, output_path=output
            )
        )

    odd = tmp_path / "odd.pcm"
    odd.write_bytes(b"\x01" * 16_001)
    with pytest.raises(SarvamSmokeError, match="align"):
        validate_pcm_fixture(
            SarvamSmokeConfig(
                api_key=SecretStr("secret"), pcm_path=odd, output_path=output
            )
        )


@pytest.mark.asyncio
async def test_structured_evidence_streams_pcm_without_persisting_sensitive_content(
    tmp_path,
) -> None:
    pcm_path = tmp_path / "spoken-fixture.pcm"
    raw_audio = _pcm_fixture(pcm_path)
    output = tmp_path / "sarvam-smoke.json"
    config = SarvamSmokeConfig(
        api_key=SecretStr("super-secret-key"),
        pcm_path=pcm_path,
        output_path=output,
        pace_audio=False,
    )
    providers: list[FakeSmokeProvider] = []

    def factory(provider_config: SarvamRealtimeConfig) -> FakeSmokeProvider:
        provider = FakeSmokeProvider(provider_config)
        providers.append(provider)
        return provider

    first = await run_sarvam_smoke(config, provider_factory=factory)
    second = await run_sarvam_smoke(
        config,
        provider_factory=lambda provider_config: FakeSmokeProvider(provider_config),
    )

    provider = providers[0]
    assert provider.config.encoding is SarvamEncoding.LINEAR16
    assert provider.config.sample_rate == 16_000
    assert provider.config.stream_type is SarvamStreamType.FAST
    assert provider.chunk_lengths == [3_200] * 6
    assert first.success is True
    assert first.audio_sha256 == hashlib.sha256(raw_audio).hexdigest()
    assert first.normalized_final_transcript == "goa is a state"
    assert first.provider_request_id == "fixture-request"
    assert first.observed_session_begin is True
    assert first.observed_final is True
    assert first.observed_session_end is True
    assert first.model_dump(exclude={"created_at"}) == second.model_dump(
        exclude={"created_at"}
    )

    serialized = output.read_text(encoding="utf-8")
    parsed = json.loads(serialized)
    assert parsed == second.model_dump(mode="json")
    assert "super-secret-key" not in serialized
    assert str(pcm_path) not in serialized
    assert "audio_input" not in serialized
    assert "audio" not in parsed
    assert "audio_bytes" not in parsed

    loaded = load_sarvam_smoke_artifact(output)
    assert loaded == second
    settings = Settings(
        environment="test",
        sarvam_api_key=SecretStr("configured-key"),
        rag_data_dir=tmp_path,
        rag_target_unique_passages=10,
        rag_development_passages=10,
    )
    services = DefaultServices(settings)
    services._configure_sarvam()
    readiness = await services.readiness()
    assert readiness["checks"]["sarvam"]["ready"] is True
    assert (
        readiness["checks"]["sarvam"]["credentialed_smoke_verified"] is True
    )


@pytest.mark.asyncio
async def test_empty_or_malformed_smoke_artifact_keeps_readiness_false(tmp_path) -> None:
    settings = Settings(
        environment="test",
        sarvam_api_key=SecretStr("configured-key"),
        rag_data_dir=tmp_path,
        rag_target_unique_passages=10,
        rag_development_passages=10,
    )
    smoke_path = tmp_path / "sarvam-smoke.json"
    smoke_path.write_text("", encoding="utf-8")

    services = DefaultServices(settings)
    services._configure_sarvam()
    readiness = await services.readiness()

    assert readiness["checks"]["sarvam"]["ready"] is False
    assert (
        readiness["checks"]["sarvam"]["credentialed_smoke_verified"] is False
    )
    assert (
        readiness["checks"]["sarvam"]["reason"]
        == "credentialed_smoke_artifact_invalid"
    )


_REAL_KEY_CONFIGURED = bool(os.getenv(API_KEY_ENV, "").strip())
_REAL_PCM_CONFIGURED = bool(os.getenv(PCM_PATH_ENV, "").strip())


@pytest.mark.real_sarvam
@pytest.mark.asyncio
@pytest.mark.skipif(
    not (_REAL_KEY_CONFIGURED and _REAL_PCM_CONFIGURED),
    reason=(
        f"real Sarvam smoke requires both {API_KEY_ENV} and an explicit "
        f"{PCM_PATH_ENV} raw 16 kHz mono PCM fixture"
    ),
)
async def test_real_sarvam_adapter_returns_nonempty_final_transcript(tmp_path) -> None:
    """Opt-in live request; this test is not exercised without both environment gates."""

    config = smoke_config_from_environment(
        os.environ,
        output_path=tmp_path / "sarvam-smoke.json",
    )
    evidence = await run_sarvam_smoke(config)

    assert evidence.success is True
    assert evidence.adapter == "SarvamRealtimeProvider"
    assert evidence.observed_session_begin is True
    assert evidence.observed_final is True
    assert evidence.observed_session_end is True
    assert evidence.normalized_final_transcript
