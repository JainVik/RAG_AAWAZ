from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import run_latency_benchmark as benchmark


def _backend_evidence(index_manifest: Path) -> dict[str, Any]:
    endpoint = "wss://api.sarvam.ai/speech-to-text/ws"
    model = "saaras:v3-realtime"
    return {
        "ready_url": "http://127.0.0.1:8000/ready",
        "status_code": 200,
        "readiness": {
            "status": "ready",
            "runtime": {
                "process_instance_id": "process-fixture-1",
                "process_started_at": "2026-08-14T09:00:00Z",
                "voice_requests_started": 0,
                "rag_deadline_ms": 200,
                "rag_fallback_at_ms": 170,
            },
            "checks": {
                "index": {
                    "ready": True,
                    "path": str(index_manifest),
                    "expected_points": 42,
                },
                "model": {
                    "ready": True,
                    "name": "intfloat/multilingual-e5-small",
                    "revision": "pinned-revision",
                    "dimension": 384,
                    "backend": "torch",
                },
                "qdrant": {
                    "ready": True,
                    "collection": "awaaz_tiderag_v1",
                    "version": "1.19.0",
                    "expected_points": 42,
                    "exact_points_count": 42,
                    "schema_valid": True,
                },
                "sarvam": {
                    "ready": True,
                    "endpoint": endpoint,
                    "model": model,
                    "credentialed_smoke_verified": True,
                },
            },
        },
        "real_provider_evidence": {
            "verified": True,
            "provider": "sarvam",
            "endpoint": endpoint,
            "model": model,
            "credentialed_smoke_verified": True,
        },
    }


def _voice_fixture(tmp_path: Path) -> Path:
    audio = tmp_path / "clip.pcm"
    audio.write_bytes((512).to_bytes(2, "little", signed=True) * 1_600)
    fixture = tmp_path / "voice.jsonl"
    fixture.write_text(
        json.dumps(
            {
                "clip_id": "clip-1",
                "audio_path": audio.name,
                "expected_transcript": "Where is Goa?",
                "language": "en",
                "condition": "clean-short",
                "source_type": "human",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return fixture


def _voice_result() -> dict[str, Any]:
    timings: dict[str, Any] = {
        "total_after_final_audio": 19.5,
        "retrieval": "8.25",
        "serialization": 0.75,
        "audio_start_to_final_response": 120.0,
        "stt_finalize": 4.5,
        "stt_last_final_after_end": 4.0,
        "input_guarded": 0.2,
        "retrieved": 8.25,
        "evidence_selected": 0.4,
        "answered": 0.3,
        "verified": 0.1,
        "speculative_retrieval": 3.5,
        "speculative_launched": 1.0,
        "speculative_reused": 1.0,
        "future_server_field": {"preserved": True},
    }
    return {
        "terminal_event": "answer",
        "client_end_marker_to_terminal_ms": 21.0,
        "server_timings_ms": timings,
        "server_total_after_final_audio_ms": 19.5,
        "completed_answer": True,
        "answer_mode": "extractive",
        "pipeline_state": "COMPLETED",
        "citation_count": 1,
        "verified_completed_response": True,
        "verified_evidence_response": False,
        "observed_transcript": "Where is Goa?",
        "guardrail_reason": None,
        "response_request_id": "fixture-request",
        "request_id_matches": True,
        "error": None,
    }


@pytest.mark.asyncio
async def test_voice_request_copies_complete_server_timing_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import websockets

    audio = tmp_path / "request.pcm"
    audio.write_bytes((400).to_bytes(2, "little", signed=True) * 160)
    expected_timings: dict[str, Any] = {
        "total_after_final_audio": 7.5,
        "retrieval": 3.25,
        "speculative_launched": 1,
        "speculative_reused": 0,
        "future_field": {"kept": True},
    }

    class Socket:
        def __init__(self) -> None:
            self.request_id = ""
            self.ended = asyncio.Event()

        async def send(self, raw: str) -> None:
            event = json.loads(raw)
            if event["type"] == "start":
                self.request_id = event["request_id"]
            elif event["type"] == "end_of_stream":
                self.ended.set()

        async def recv(self) -> str:
            await self.ended.wait()
            return json.dumps(
                {
                    "type": "answer",
                    "request_id": self.request_id,
                    "payload": {
                        "answer": "Goa is in India.",
                        "state": "COMPLETED",
                        "answer_mode": "extractive",
                        "citations": [{"canonical_doc_id": "doc-1"}],
                        "transcript": "Where is Goa?",
                        "timings_ms": expected_timings,
                    },
                }
            )

    socket = Socket()

    class Connection:
        async def __aenter__(self) -> Socket:
            return socket

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: Connection())
    result = await benchmark._voice_request(
        {"audio_path": str(audio), "language": "en"},
        websocket_url="ws://127.0.0.1:8000/v1/query/voice",
        timeout_seconds=2.0,
        chunk_ms=100,
        pace_audio=False,
        api_token=None,
    )

    assert result["server_timings_ms"] == expected_timings
    assert result["server_total_after_final_audio_ms"] == 7.5
    assert result["request_id_matches"] is True


def test_stage_and_speculative_aggregates_retain_missing_rows() -> None:
    rows = [
        {
            "server_timings_ms": {
                "retrieval": 10,
                "speculative_launched": 1,
                "speculative_reused": 1,
            },
            "completed_answer": True,
        },
        {
            "server_timings_ms": {
                "retrieval": "20.0",
                "speculative_launched": 1,
                "speculative_reused": 0,
            },
            "completed_answer": False,
        },
        {
            "server_timings_ms": {},
            "completed_answer": False,
        },
    ]

    stages = benchmark._server_stage_metrics(rows)
    retrieval = stages["retrieval"]
    assert retrieval["request_count"] == 3
    assert retrieval["sample_count"] == 2
    assert retrieval["timing_coverage"] == pytest.approx(2 / 3)
    assert retrieval["missing_timing_count"] == 1
    assert retrieval["p50_ms"] == 10.0
    assert retrieval["p70_ms"] == 20.0
    assert retrieval["p100_ms"] == 20.0
    assert "speculative_launched" not in stages

    speculative = benchmark._speculative_metrics(rows)
    assert speculative["request_count"] == 3
    assert speculative["speculative_launched_total"] == 2.0
    assert speculative["speculative_reused_total"] == 1.0
    assert speculative["timing_coverage"] == pytest.approx(2 / 3)
    assert speculative["reuse_rate"] == 0.5
    assert speculative["counts_consistent"] is True
    assert speculative["qualification_ready"] is False


def test_total_only_server_timing_cannot_satisfy_canonical_evidence() -> None:
    total_only = [
        {
            "server_timings_ms": {"total_after_final_audio": 10.0},
            "verified_response": True,
            "verified_completed_response": True,
        }
    ]
    incomplete = benchmark._server_timing_evidence(total_only)
    assert incomplete["passed"] is False
    assert "serialization" in incomplete["failed_fields"]
    assert "retrieved" in incomplete["failed_fields"]

    complete = [
        {
            "server_timings_ms": _voice_result()["server_timings_ms"],
            "verified_response": True,
            "verified_completed_response": True,
        }
    ]
    assert benchmark._server_timing_evidence(complete)["passed"] is True
    assert benchmark._speculative_metrics(complete)["qualification_ready"] is True


def test_cold_preflight_rejects_backend_with_prior_voice_request(tmp_path: Path) -> None:
    evidence = _backend_evidence(tmp_path / "index-manifest.json")
    evidence["readiness"]["runtime"]["voice_requests_started"] = 1
    with pytest.raises(benchmark.EvaluationError, match="voice_requests_started=0"):
        benchmark._require_fresh_cold_runtime(evidence)


def test_voice_deadline_must_match_effective_ready_policy(tmp_path: Path) -> None:
    evidence = _backend_evidence(tmp_path / "index-manifest.json")
    benchmark._require_voice_deadline_match(evidence, 200)

    with pytest.raises(benchmark.EvaluationError, match="must exactly match"):
        benchmark._require_voice_deadline_match(evidence, 190)

    evidence["readiness"]["runtime"]["rag_fallback_at_ms"] = None
    with pytest.raises(benchmark.EvaluationError, match="rag_fallback_at_ms"):
        benchmark._require_voice_deadline_match(evidence, 200)


@pytest.mark.asyncio
async def test_cold_voice_run_preserves_timings_and_is_integrity_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _voice_fixture(tmp_path)
    index_manifest = tmp_path / "index-manifest.json"
    index_manifest.write_text('{"point_count":42}', encoding="utf-8")

    async def backend_metadata(websocket_url: str, timeout_seconds: float) -> dict[str, Any]:
        assert websocket_url == "ws://127.0.0.1:8000/v1/query/voice"
        assert timeout_seconds > 0
        return _backend_evidence(index_manifest)

    async def voice_request(row: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        assert row["clip_id"] == "clip-1"
        assert kwargs["pace_audio"] is True
        return _voice_result()

    monkeypatch.setattr(benchmark, "_backend_metadata", backend_metadata)
    monkeypatch.setattr(benchmark, "_voice_request", voice_request)
    args = benchmark.build_parser().parse_args(
        [
            "--fixture",
            str(fixture),
            "--startup-condition",
            "cold",
            "--warmup",
            "0",
            "--deadline-ms",
            "200",
        ]
    )

    summary, rows = await benchmark.run(args)

    assert len(rows) == 1
    assert rows[0]["server_timings_ms"] == _voice_result()["server_timings_ms"]
    assert summary["server_stage_latency"]["retrieval"]["p100_ms"] == 8.25
    assert summary["speculative_retrieval"]["speculative_launched_total"] == 1.0
    assert summary["cold_start_integrity"]["valid"] is True, summary["cold_start_integrity"]
    assert summary["cold_start_integrity"]["primary_qualifying"] is False
    assert summary["cold_start_integrity"]["process_instance_id"] == "process-fixture-1"
    assert summary["qualifying"] is False
    assert summary["metadata"]["qualification"] == ("cold_start_integrity_valid_non_primary")
    markdown = benchmark._markdown(summary)
    assert "Server stage latency" in markdown
    assert "Cold-start integrity (non-primary)" in markdown


@pytest.mark.asyncio
async def test_cold_evidence_fails_closed_on_tamper_or_policy_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _voice_fixture(tmp_path)
    index_manifest = tmp_path / "index-manifest.json"
    index_manifest.write_text('{"point_count":42}', encoding="utf-8")

    async def backend_metadata(websocket_url: str, timeout_seconds: float) -> dict[str, Any]:
        del websocket_url, timeout_seconds
        return _backend_evidence(index_manifest)

    async def voice_request(row: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        del row, kwargs
        return _voice_result()

    monkeypatch.setattr(benchmark, "_backend_metadata", backend_metadata)
    monkeypatch.setattr(benchmark, "_voice_request", voice_request)
    args = benchmark.build_parser().parse_args(
        [
            "--fixture",
            str(fixture),
            "--startup-condition",
            "cold",
            "--warmup",
            "0",
            "--deadline-ms",
            "200",
        ]
    )
    summary, _ = await benchmark.run(args)
    expected = summary["metadata"]["compatibility"]

    report = tmp_path / "cold.json"
    report.write_text(json.dumps(summary), encoding="utf-8")
    valid_evidence = benchmark._cold_start_evidence(report, expected_compatibility=expected)
    assert valid_evidence["verified"] is True, valid_evidence

    tampered_failure = copy.deepcopy(summary)
    tampered_failure["failure_count"] = 1
    report.write_text(json.dumps(tampered_failure), encoding="utf-8")
    failed = benchmark._cold_start_evidence(report, expected_compatibility=expected)
    assert failed["verified"] is False
    assert "zero_request_failures" in failed["failed_checks"]

    warmed_before_capture = copy.deepcopy(summary)
    warmed_before_capture["metadata"]["backend"]["readiness"]["runtime"][
        "voice_requests_started"
    ] = 1
    report.write_text(json.dumps(warmed_before_capture), encoding="utf-8")
    stale_process = benchmark._cold_start_evidence(report, expected_compatibility=expected)
    assert stale_process["verified"] is False
    assert "zero_prior_voice_requests" in stale_process["failed_checks"]

    tampered_policy = copy.deepcopy(summary)
    compatibility = tampered_policy["metadata"]["compatibility"]
    compatibility["chunk_ms"] = 120
    tampered_policy["metadata"]["compatibility_fingerprint"] = benchmark._compatibility_fingerprint(
        compatibility
    )
    report.write_text(json.dumps(tampered_policy), encoding="utf-8")
    mismatched = benchmark._cold_start_evidence(report, expected_compatibility=expected)
    assert mismatched["verified"] is False
    assert "chunking_matches" in mismatched["failed_checks"]
    assert "compatibility_fingerprint_matches" in mismatched["failed_checks"]

    tampered_deadline = copy.deepcopy(summary)
    deadline_compatibility = tampered_deadline["metadata"]["compatibility"]
    deadline_compatibility["deadline_policy"]["backend_fallback_at_ms"] = 160
    tampered_deadline["metadata"]["compatibility_fingerprint"] = (
        benchmark._compatibility_fingerprint(deadline_compatibility)
    )
    report.write_text(json.dumps(tampered_deadline), encoding="utf-8")
    wrong_deadline = benchmark._cold_start_evidence(report, expected_compatibility=expected)
    assert wrong_deadline["verified"] is False
    assert "runtime_deadline_policy_bound_to_compatibility" in wrong_deadline["failed_checks"]
    assert "deadline_policy_matches" in wrong_deadline["failed_checks"]

    tampered_index = copy.deepcopy(summary)
    index_compatibility = tampered_index["metadata"]["compatibility"]
    index_compatibility["backend_identity"]["index"]["manifest_sha256"] = "b" * 64
    tampered_index["metadata"]["compatibility_fingerprint"] = benchmark._compatibility_fingerprint(
        index_compatibility
    )
    report.write_text(json.dumps(tampered_index), encoding="utf-8")
    wrong_index = benchmark._cold_start_evidence(report, expected_compatibility=expected)
    assert wrong_index["verified"] is False
    assert "backend_and_index_match" in wrong_index["failed_checks"]

    missing_server_timing = copy.deepcopy(summary)
    missing_server_timing["server_total_after_final_audio"]["timing_coverage"] = 0.0
    report.write_text(json.dumps(missing_server_timing), encoding="utf-8")
    incomplete = benchmark._cold_start_evidence(report, expected_compatibility=expected)
    assert incomplete["verified"] is False
    assert "complete_server_timing" in incomplete["failed_checks"]
