from __future__ import annotations

import pytest

from app.domain.enums import Language, SttEventType
from app.domain.models import SttEvent
from app.stt.base import ProviderState, SttProviderError
from app.stt.fake import FakeSpeechToTextProvider, FakeSttConfig


@pytest.mark.asyncio
async def test_fake_provider_is_scripted_and_does_not_retain_audio_by_default() -> None:
    scripted = [
        SttEvent(
            event_type=SttEventType.PARTIAL,
            text="गोवा",
            language=Language.HINDI,
            confidence=None,
        ),
        SttEvent(
            event_type=SttEventType.FINAL,
            text="गोवा कब बना",
            language=Language.HINDI,
            confidence=None,
        ),
    ]
    provider = FakeSpeechToTextProvider(scripted)
    await provider.connect()
    await provider.send_audio(b"audio")
    await provider.finish()

    events = [event async for event in provider.events()]

    assert events == scripted
    assert provider.audio_chunks_received == 1
    assert provider.audio_bytes_received == 5
    assert provider.retained_audio == ()
    assert provider.state is ProviderState.CLOSED


@pytest.mark.asyncio
async def test_fake_provider_can_opt_in_to_audio_retention() -> None:
    provider = FakeSpeechToTextProvider(config=FakeSttConfig(retain_audio=True))
    await provider.connect()
    await provider.send_audio(b"one")
    assert provider.retained_audio == (b"one",)


@pytest.mark.asyncio
async def test_fake_provider_exposes_structured_failure() -> None:
    provider = FakeSpeechToTextProvider(
        config=FakeSttConfig(fail_after_audio_chunks=0)
    )
    await provider.connect()
    with pytest.raises(SttProviderError) as caught:
        await provider.send_audio(b"audio")
    assert caught.value.code == "fake_audio_failure"
    assert not caught.value.retryable
    assert provider.state is ProviderState.FAILED
