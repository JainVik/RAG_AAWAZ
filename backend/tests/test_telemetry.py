from __future__ import annotations

from app.domain.enums import (
    AnswerMode,
    ErrorCode,
    GuardrailDecision,
    Language,
    PipelineState,
)
from app.domain.models import GuardrailResult, QueryResponse, VoiceErrorPayload
from app.telemetry.recorder import MetricsRecorder, nearest_rank_percentile


def test_p100_is_actual_maximum() -> None:
    values = [1.0, 2.0, 3.0, 99.0]
    assert nearest_rank_percentile(values, 100) == max(values)
    assert nearest_rank_percentile(values, 50) == 2.0


def test_recorder_aggregates_each_completed_transport_timing() -> None:
    recorder = MetricsRecorder()
    recorder.record_response(
        QueryResponse(
            request_id="req",
            transcript="question",
            language=Language.ENGLISH,
            answer=None,
            answer_mode=AnswerMode.ABSTENTION,
            guardrail=GuardrailResult(decision=GuardrailDecision.ABSTAIN),
            state=PipelineState.ABSTAINED,
            timings_ms={
                "retrieved": 8.0,
                "stt_finalize": 12.0,
                "serialization": 1.0,
                "total_after_final_audio": 25.0,
            },
        )
    )

    snapshot = recorder.snapshot()

    assert snapshot["requests_total"] == 1
    assert snapshot["latency_sample_count"] == 1
    assert snapshot["timings_ms"]["stt_finalize"] == {
        "count": 1,
        "p50": 12.0,
        "p70": 12.0,
        "p95": 12.0,
        "p100": 12.0,
    }

    recorder.record_error(
        VoiceErrorPayload(
            code=ErrorCode.SARVAM_ERROR,
            state=PipelineState.DEPENDENCY_UNAVAILABLE,
            message="provider failed",
            timings_ms={"total_after_final_audio": 30.0},
        )
    )
    failed_snapshot = recorder.snapshot()
    assert failed_snapshot["requests_total"] == 2
    assert failed_snapshot["error_codes"] == {"SARVAM_ERROR": 1}
    assert failed_snapshot["latency_sample_count"] == 2
