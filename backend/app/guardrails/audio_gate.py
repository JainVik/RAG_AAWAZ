from __future__ import annotations

import math
import struct

from app.domain.enums import GuardrailDecision, GuardrailReason
from app.domain.models import GuardrailResult


def evaluate_pcm_audio(
    audio: bytes,
    *,
    sample_width: int = 2,
    sample_rate_hz: int = 16_000,
    min_duration_ms: int = 250,
    min_rms: int = 80,
) -> GuardrailResult:
    if not audio:
        return GuardrailResult(
            decision=GuardrailDecision.NEEDS_REPEAT,
            reason=GuardrailReason.SILENCE,
            user_message="I could not hear any audio. Please try again.",
        )
    if len(audio) % sample_width:
        return GuardrailResult(
            decision=GuardrailDecision.NEEDS_REPEAT,
            reason=GuardrailReason.INVALID_AUDIO,
            evidence={"byte_count": len(audio)},
            user_message="The audio format was invalid. Please try again.",
        )
    duration_ms = len(audio) / (sample_width * sample_rate_hz) * 1_000
    if duration_ms < min_duration_ms:
        return GuardrailResult(
            decision=GuardrailDecision.NEEDS_REPEAT,
            reason=GuardrailReason.AUDIO_TOO_SHORT,
            evidence={"duration_ms": round(duration_ms, 1)},
            user_message="The recording was too short. Please repeat the full question.",
        )
    if sample_width != 2:
        return GuardrailResult(
            decision=GuardrailDecision.NEEDS_REPEAT,
            reason=GuardrailReason.INVALID_AUDIO,
            evidence={"sample_width": sample_width},
            user_message="Only 16-bit PCM audio is supported by this endpoint.",
        )
    sample_count = len(audio) // 2
    samples = struct.unpack(f"<{sample_count}h", audio)
    rms = int(math.sqrt(sum(sample * sample for sample in samples) / sample_count))
    if rms < min_rms:
        return GuardrailResult(
            decision=GuardrailDecision.NEEDS_REPEAT,
            reason=GuardrailReason.SILENCE,
            evidence={"rms": rms},
            user_message="I could not hear clear speech. Please try again.",
        )
    return GuardrailResult(decision=GuardrailDecision.ALLOW, evidence={"duration_ms": duration_ms})
