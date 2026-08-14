from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import hashlib
import json
import math
import os
import sys
import time
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.enums import Language  # noqa: E402
from app.evaluation.metrics import latency_metrics  # noqa: E402
from app.stt.stability import (  # noqa: E402
    normalize_transcript,
    normalized_edit_similarity,
)
from scripts._common import (  # noqa: E402
    DEFAULT_CORPUS_EVALUATION_FIXTURE,
    REPORTS_ROOT,
    EvaluationError,
    base_metadata,
    corpus_metadata,
    enforce_distinct,
    file_sha256,
    initialized_services,
    load_records,
    markdown_table,
    print_artifacts,
    require_minimum_cases,
    require_text,
    select_query_and_field,
    write_report_bundle,
)

DEFAULT_MINIMUM_REQUESTS = 100
DEFAULT_TARGET_REQUESTS = 300
MAX_AUDIO_BYTES = 16_000 * 2 * 60
PCM_SAMPLE_RATE_HZ = 16_000
PCM_SAMPLE_WIDTH_BYTES = 2
AUDIBLE_SAMPLE_THRESHOLD = 64
SPECULATIVE_COUNTER_FIELDS = frozenset({"speculative_launched", "speculative_reused"})
CANONICAL_PROVIDER_TIMING_FIELDS = (
    "total_after_final_audio",
    "serialization",
    "audio_start_to_final_response",
    "stt_finalize",
    "stt_last_final_after_end",
)
CANONICAL_VERIFIED_INTERNAL_TIMING_FIELDS = ("input_guarded", "retrieved")
CANONICAL_COMPLETED_INTERNAL_TIMING_FIELDS = (
    "evidence_selected",
    "answered",
    "verified",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark voice end-of-audio latency or a non-qualifying text smoke path."
    )
    parser.add_argument("--mode", choices=("voice", "text-smoke"), default="voice")
    parser.add_argument(
        "--fixture",
        type=Path,
        help=(
            "Defaults to the corpus fixture for text-smoke or "
            "evaluation/private/voice-latency.jsonl for voice mode."
        ),
    )
    parser.add_argument("--output-prefix", type=Path, default=REPORTS_ROOT / "latency-benchmark")
    parser.add_argument("--websocket-url", default="ws://127.0.0.1:8000/v1/query/voice")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--minimum-requests", type=int, default=DEFAULT_MINIMUM_REQUESTS)
    parser.add_argument("--target-requests", type=int, default=DEFAULT_TARGET_REQUESTS)
    parser.add_argument(
        "--under-target-reason",
        help="Required for a qualifying voice run below the 300-request target.",
    )
    parser.add_argument(
        "--human-recorded-waiver-reason",
        help=(
            "Required for a qualifying voice run with fewer than 60 human-recorded "
            "clips; explains why that target was not feasible."
        ),
    )
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--deadline-ms", type=int)
    parser.add_argument("--chunk-ms", type=int, default=100)
    parser.add_argument(
        "--maximum-trailing-silence-ms",
        type=float,
        default=200.0,
        help="Qualifying fixtures must end within this many ms of the last audible sample.",
    )
    parser.add_argument("--minimum-transcript-similarity", type=float, default=0.80)
    parser.add_argument("--minimum-transcript-match-coverage", type=float, default=0.95)
    parser.add_argument("--minimum-verified-response-coverage", type=float, default=0.90)
    parser.add_argument(
        "--pace-audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pace PCM chunks in real time (enabled by default).",
    )
    parser.add_argument("--allow-small-smoke", action="store_true")
    parser.add_argument(
        "--startup-condition",
        choices=("cold", "warm"),
        default="warm",
        help="Whether this separately named run was captured before or after warmup.",
    )
    parser.add_argument(
        "--cold-start-report",
        type=Path,
        help="Cold voice summary JSON linked to a qualifying warm primary report.",
    )
    parser.add_argument(
        "--cache-policy",
        choices=("disabled", "cold", "warm", "mixed", "uncontrolled"),
        default="disabled",
        help="Primary qualifying runs require disabled query-result caching.",
    )
    return parser


def _trailing_silence_ms(
    audio: bytes, *, audible_threshold: int = AUDIBLE_SAMPLE_THRESHOLD
) -> float:
    last_audible_sample = -1
    sample_count = len(audio) // 2
    for sample_index in range(sample_count):
        offset = sample_index * 2
        sample = int.from_bytes(audio[offset : offset + 2], "little", signed=True)
        if abs(sample) >= audible_threshold:
            last_audible_sample = sample_index
    trailing_samples = (
        sample_count if last_audible_sample < 0 else sample_count - last_audible_sample - 1
    )
    return trailing_samples / PCM_SAMPLE_RATE_HZ * 1_000


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _ready_url(websocket_url: str) -> str:
    parsed = urlsplit(websocket_url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
        raise EvaluationError(f"Invalid --websocket-url: {websocket_url!r}")
    scheme = "https" if parsed.scheme == "wss" else "http"
    return urlunsplit((scheme, parsed.netloc, "/ready", "", ""))


def _compatibility_fingerprint(compatibility: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        compatibility,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _selected_mapping(value: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {field: value.get(field) for field in fields}


def _index_identity(value: Any) -> dict[str, Any]:
    identity = _selected_mapping(value, ("path", "expected_points"))
    raw_path = identity.get("path")
    manifest_path = Path(raw_path) if isinstance(raw_path, str) else None
    if manifest_path is not None and not manifest_path.is_absolute():
        manifest_path = BACKEND_ROOT / manifest_path
    identity["manifest_sha256"] = (
        file_sha256(manifest_path)
        if manifest_path is not None and manifest_path.is_file()
        else None
    )
    return identity


def _benchmark_compatibility(
    metadata: Mapping[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    fixture = metadata.get("fixture")
    backend = metadata.get("backend")
    backend = backend if isinstance(backend, Mapping) else {}
    readiness = backend.get("readiness")
    checks = readiness.get("checks") if isinstance(readiness, Mapping) else None
    checks = checks if isinstance(checks, Mapping) else {}
    runtime = readiness.get("runtime") if isinstance(readiness, Mapping) else None
    provider = backend.get("real_provider_evidence")
    return {
        "fixture_sha256": (fixture.get("sha256") if isinstance(fixture, Mapping) else None),
        "websocket_url": args.websocket_url,
        "backend_identity": {
            "ready_url": backend.get("ready_url"),
            "process": _selected_mapping(
                runtime,
                ("process_instance_id", "process_started_at"),
            ),
            "provider": _selected_mapping(
                provider,
                (
                    "verified",
                    "provider",
                    "endpoint",
                    "model",
                    "credentialed_smoke_verified",
                ),
            ),
            "index": _index_identity(checks.get("index")),
            "model": _selected_mapping(
                checks.get("model"),
                ("name", "revision", "dimension", "backend"),
            ),
            "qdrant": _selected_mapping(
                checks.get("qdrant"),
                (
                    "collection",
                    "version",
                    "expected_points",
                    "exact_points_count",
                    "schema_valid",
                ),
            ),
        },
        "deadline_ms": args.deadline_ms,
        "deadline_policy": {
            "declared_hard_deadline_ms": args.deadline_ms,
            "backend_hard_deadline_ms": (
                runtime.get("rag_deadline_ms") if isinstance(runtime, Mapping) else None
            ),
            "backend_fallback_at_ms": (
                runtime.get("rag_fallback_at_ms") if isinstance(runtime, Mapping) else None
            ),
        },
        "chunk_ms": args.chunk_ms,
        "pace_audio": args.pace_audio,
        "cache_policy": args.cache_policy,
        "concurrency": args.concurrency,
        "trailing_silence_policy": {
            "maximum_ms": args.maximum_trailing_silence_ms,
            "audible_sample_threshold": AUDIBLE_SAMPLE_THRESHOLD,
            "sample_rate_hz": PCM_SAMPLE_RATE_HZ,
            "sample_width_bytes": PCM_SAMPLE_WIDTH_BYTES,
        },
    }


def _exact_number(value: Any, expected: int | float) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and float(value) == float(expected)
    )


def _official_provider_evidence(metadata: Mapping[str, Any]) -> bool:
    backend = metadata.get("backend")
    evidence = backend.get("real_provider_evidence") if isinstance(backend, Mapping) else None
    if not isinstance(evidence, Mapping):
        return False
    endpoint_parts = urlsplit(str(evidence.get("endpoint") or ""))
    model = evidence.get("model")
    return bool(
        evidence.get("verified") is True
        and evidence.get("provider") == "sarvam"
        and endpoint_parts.scheme == "wss"
        and endpoint_parts.hostname == "api.sarvam.ai"
        and isinstance(model, str)
        and model.casefold().startswith("saaras")
        and evidence.get("credentialed_smoke_verified") is True
    )


def _require_voice_deadline_match(backend: Any, declared_deadline_ms: Any) -> None:
    readiness = backend.get("readiness") if isinstance(backend, Mapping) else None
    runtime = readiness.get("runtime") if isinstance(readiness, Mapping) else None
    backend_deadline = runtime.get("rag_deadline_ms") if isinstance(runtime, Mapping) else None
    backend_fallback = runtime.get("rag_fallback_at_ms") if isinstance(runtime, Mapping) else None
    declared = _float_or_none(declared_deadline_ms)
    effective = _float_or_none(backend_deadline)
    fallback = _float_or_none(backend_fallback)
    if declared is None:
        raise EvaluationError("Real voice benchmarking requires an explicit --deadline-ms")
    if effective is None or fallback is None:
        raise EvaluationError(
            "Backend /ready.runtime must expose numeric rag_deadline_ms and rag_fallback_at_ms"
        )
    if declared != effective:
        raise EvaluationError(
            "--deadline-ms must exactly match /ready.runtime.rag_deadline_ms; "
            f"declared={declared:g}, backend={effective:g}"
        )
    if fallback >= effective:
        raise EvaluationError(
            "Backend /ready.runtime deadline policy is invalid: rag_fallback_at_ms "
            "must be below rag_deadline_ms"
        )


def _require_fresh_cold_runtime(backend: Any) -> None:
    readiness = backend.get("readiness") if isinstance(backend, Mapping) else None
    runtime = readiness.get("runtime") if isinstance(readiness, Mapping) else None
    valid = bool(
        isinstance(runtime, Mapping)
        and isinstance(runtime.get("process_instance_id"), str)
        and runtime.get("process_instance_id")
        and isinstance(runtime.get("process_started_at"), str)
        and runtime.get("process_started_at")
        and _exact_number(runtime.get("voice_requests_started"), 0)
    )
    if not valid:
        raise EvaluationError(
            "Cold-start capture requires /ready.runtime with a nonempty process ID/start "
            "time and voice_requests_started=0; restart the backend before retrying"
        )


def _full_single_timing(metric: Any) -> bool:
    if not isinstance(metric, Mapping):
        return False
    return bool(
        _exact_number(metric.get("request_count"), 1)
        and _exact_number(metric.get("sample_count"), 1)
        and _exact_number(metric.get("timing_coverage"), 1.0)
        and _exact_number(metric.get("missing_timing_count"), 0)
        and _exact_number(metric.get("excluded_from_percentiles_count"), 0)
    )


def _valid_compatibility_shape(compatibility: Any) -> bool:
    if not isinstance(compatibility, Mapping):
        return False
    required = {
        "fixture_sha256",
        "websocket_url",
        "backend_identity",
        "deadline_ms",
        "deadline_policy",
        "chunk_ms",
        "pace_audio",
        "cache_policy",
        "concurrency",
        "trailing_silence_policy",
    }
    if not required.issubset(compatibility):
        return False
    fixture_sha = compatibility.get("fixture_sha256")
    backend = compatibility.get("backend_identity")
    trailing = compatibility.get("trailing_silence_policy")
    if not isinstance(backend, Mapping) or not isinstance(trailing, Mapping):
        return False
    provider = backend.get("provider")
    process = backend.get("process")
    index = backend.get("index")
    model = backend.get("model")
    qdrant = backend.get("qdrant")
    if not all(
        isinstance(item, Mapping)
        for item in (provider, process, index, model, qdrant)
    ):
        return False
    assert isinstance(provider, Mapping)
    assert isinstance(process, Mapping)
    assert isinstance(index, Mapping)
    assert isinstance(model, Mapping)
    assert isinstance(qdrant, Mapping)
    websocket_parts = urlsplit(str(compatibility.get("websocket_url") or ""))
    deadline = _float_or_none(compatibility.get("deadline_ms"))
    deadline_policy = compatibility.get("deadline_policy")
    if deadline is None or not isinstance(deadline_policy, Mapping):
        return False
    declared_deadline = (
        deadline_policy.get("declared_hard_deadline_ms")
    )
    backend_deadline = deadline_policy.get("backend_hard_deadline_ms")
    backend_fallback = _float_or_none(
        deadline_policy.get("backend_fallback_at_ms")
    )
    manifest_sha = index.get("manifest_sha256")
    return bool(
        isinstance(fixture_sha, str)
        and len(fixture_sha) == 64
        and all(character in "0123456789abcdef" for character in fixture_sha.casefold())
        and isinstance(compatibility.get("websocket_url"), str)
        and compatibility.get("websocket_url")
        and websocket_parts.scheme in {"ws", "wss"}
        and websocket_parts.netloc
        and isinstance(backend.get("ready_url"), str)
        and bool(backend.get("ready_url"))
        and isinstance(process.get("process_instance_id"), str)
        and bool(process.get("process_instance_id"))
        and isinstance(process.get("process_started_at"), str)
        and bool(process.get("process_started_at"))
        and isinstance(index.get("path"), str)
        and bool(index.get("path"))
        and _float_or_none(index.get("expected_points")) is not None
        and isinstance(manifest_sha, str)
        and len(manifest_sha) == 64
        and all(
            isinstance(model.get(field), str) and bool(model.get(field))
            for field in ("name", "revision", "backend")
        )
        and _float_or_none(model.get("dimension")) is not None
        and isinstance(qdrant.get("collection"), str)
        and bool(qdrant.get("collection"))
        and isinstance(qdrant.get("version"), str)
        and bool(qdrant.get("version"))
        and _float_or_none(qdrant.get("expected_points")) is not None
        and _float_or_none(qdrant.get("exact_points_count")) is not None
        and qdrant.get("schema_valid") is True
        and _exact_number(declared_deadline, deadline)
        and _exact_number(backend_deadline, deadline)
        and backend_fallback is not None
        and backend_fallback < deadline
        and _float_or_none(compatibility.get("chunk_ms")) is not None
        and isinstance(compatibility.get("pace_audio"), bool)
        and isinstance(compatibility.get("cache_policy"), str)
        and _float_or_none(compatibility.get("concurrency")) is not None
        and _float_or_none(trailing.get("maximum_ms")) is not None
        and _exact_number(trailing.get("audible_sample_threshold"), AUDIBLE_SAMPLE_THRESHOLD)
        and _exact_number(trailing.get("sample_rate_hz"), PCM_SAMPLE_RATE_HZ)
        and _exact_number(trailing.get("sample_width_bytes"), PCM_SAMPLE_WIDTH_BYTES)
    )


def _cold_report_checks(
    value: Any,
    *,
    expected_compatibility: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    report = value if isinstance(value, Mapping) else {}
    metadata = report.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    compatibility = metadata.get("compatibility")
    fingerprint = metadata.get("compatibility_fingerprint")
    compatibility_valid = _valid_compatibility_shape(compatibility)
    fingerprint_valid = False
    if (
        compatibility_valid
        and isinstance(compatibility, Mapping)
        and isinstance(fingerprint, str)
    ):
        try:
            fingerprint_valid = fingerprint == _compatibility_fingerprint(compatibility)
        except (TypeError, ValueError):
            fingerprint_valid = False

    trailing = (
        compatibility.get("trailing_silence_policy") if isinstance(compatibility, Mapping) else None
    )
    voice_quality = report.get("voice_quality")
    maximum_observed = (
        voice_quality.get("maximum_observed_trailing_silence_ms")
        if isinstance(voice_quality, Mapping)
        else None
    )
    trailing_maximum = trailing.get("maximum_ms") if isinstance(trailing, Mapping) else None
    observed_trailing = _float_or_none(maximum_observed)
    allowed_trailing = _float_or_none(trailing_maximum)
    backend = metadata.get("backend")
    readiness = backend.get("readiness") if isinstance(backend, Mapping) else None
    runtime = readiness.get("runtime") if isinstance(readiness, Mapping) else None
    runtime = runtime if isinstance(runtime, Mapping) else {}
    backend_identity = (
        compatibility.get("backend_identity") if isinstance(compatibility, Mapping) else None
    )
    compatible_process = (
        backend_identity.get("process") if isinstance(backend_identity, Mapping) else None
    )
    compatible_deadline_policy = (
        compatibility.get("deadline_policy") if isinstance(compatibility, Mapping) else None
    )
    runtime_deadline = _float_or_none(runtime.get("rag_deadline_ms"))
    runtime_fallback = _float_or_none(runtime.get("rag_fallback_at_ms"))
    runtime_process = {
        "process_instance_id": runtime.get("process_instance_id"),
        "process_started_at": runtime.get("process_started_at"),
    }
    server_timing_evidence = report.get("server_timing_evidence")
    speculative_evidence = report.get("speculative_retrieval")
    checks = {
        "voice_mode": metadata.get("mode") == "voice",
        "cold_startup_condition": metadata.get("startup_condition") == "cold",
        "non_primary_classification": (
            report.get("qualifying") is False and metadata.get("qualifying") is False
        ),
        "zero_warmups": _exact_number(metadata.get("warmup_count"), 0),
        "exactly_one_measured_request": _exact_number(metadata.get("measured_request_count"), 1),
        "zero_request_failures": _exact_number(report.get("failure_count"), 0),
        "complete_client_timing": _full_single_timing(report.get("client_end_marker_to_terminal")),
        "complete_server_timing": _full_single_timing(report.get("server_total_after_final_audio")),
        "real_sarvam_evidence": _official_provider_evidence(metadata),
        "backend_boot_identity_present": bool(
            isinstance(runtime.get("process_instance_id"), str)
            and runtime.get("process_instance_id")
            and isinstance(runtime.get("process_started_at"), str)
            and runtime.get("process_started_at")
        ),
        "zero_prior_voice_requests": _exact_number(runtime.get("voice_requests_started"), 0),
        "boot_identity_bound_to_compatibility": (
            isinstance(compatible_process, Mapping) and dict(compatible_process) == runtime_process
        ),
        "runtime_deadline_policy_bound_to_compatibility": (
            isinstance(compatible_deadline_policy, Mapping)
            and runtime_deadline is not None
            and runtime_fallback is not None
            and _exact_number(
                compatible_deadline_policy.get("declared_hard_deadline_ms"),
                runtime_deadline,
            )
            and _exact_number(
                compatible_deadline_policy.get("backend_hard_deadline_ms"),
                runtime_deadline,
            )
            and _exact_number(
                compatible_deadline_policy.get("backend_fallback_at_ms"),
                runtime_fallback,
            )
        ),
        "canonical_server_timing_evidence": (
            isinstance(server_timing_evidence, Mapping)
            and server_timing_evidence.get("passed") is True
        ),
        "speculative_counter_evidence": (
            isinstance(speculative_evidence, Mapping)
            and speculative_evidence.get("qualification_ready") is True
        ),
        "compatibility_fields_complete": compatibility_valid,
        "compatibility_fingerprint_valid": fingerprint_valid,
        "primary_cache_policy": (
            isinstance(compatibility, Mapping) and compatibility.get("cache_policy") == "disabled"
        ),
        "primary_concurrency": (
            isinstance(compatibility, Mapping)
            and _exact_number(compatibility.get("concurrency"), 1)
        ),
        "real_time_audio_pacing": (
            isinstance(compatibility, Mapping) and compatibility.get("pace_audio") is True
        ),
        "bounded_trailing_silence": (
            observed_trailing is not None
            and allowed_trailing is not None
            and observed_trailing <= allowed_trailing
        ),
    }
    if expected_compatibility is not None:
        expected = dict(expected_compatibility)
        observed = dict(compatibility) if isinstance(compatibility, Mapping) else {}
        checks.update(
            {
                "fixture_matches": observed.get("fixture_sha256") == expected.get("fixture_sha256"),
                "backend_and_index_match": observed.get("backend_identity")
                == expected.get("backend_identity"),
                "websocket_matches": observed.get("websocket_url") == expected.get("websocket_url"),
                "deadline_matches": observed.get("deadline_ms") == expected.get("deadline_ms"),
                "deadline_policy_matches": observed.get("deadline_policy")
                == expected.get("deadline_policy"),
                "chunking_matches": observed.get("chunk_ms") == expected.get("chunk_ms"),
                "pacing_matches": observed.get("pace_audio") == expected.get("pace_audio"),
                "cache_policy_matches": observed.get("cache_policy")
                == expected.get("cache_policy"),
                "concurrency_matches": observed.get("concurrency") == expected.get("concurrency"),
                "trailing_policy_matches": observed.get("trailing_silence_policy")
                == expected.get("trailing_silence_policy"),
                "compatibility_fingerprint_matches": (
                    fingerprint_valid and fingerprint == _compatibility_fingerprint(expected)
                ),
            }
        )
    return checks


def _cold_start_evidence(
    path: Path | None, *, expected_compatibility: Mapping[str, Any]
) -> dict[str, Any]:
    if path is None:
        return {"verified": False, "reason": "cold_start_report_not_supplied"}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvaluationError(f"Cold-start report is unreadable: {path}: {exc}") from exc
    checks = _cold_report_checks(value, expected_compatibility=expected_compatibility)
    failed_checks = [name for name, passed in checks.items() if not passed]
    valid = not failed_checks
    metadata = value.get("metadata") if isinstance(value, Mapping) else None
    backend = metadata.get("backend") if isinstance(metadata, Mapping) else None
    readiness = backend.get("readiness") if isinstance(backend, Mapping) else None
    runtime = readiness.get("runtime") if isinstance(readiness, Mapping) else None
    return {
        "verified": valid,
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
        "process_instance_id": (
            runtime.get("process_instance_id") if isinstance(runtime, Mapping) else None
        ),
        "process_started_at": (
            runtime.get("process_started_at") if isinstance(runtime, Mapping) else None
        ),
        "checks": checks,
        "failed_checks": failed_checks,
        "reason": None if valid else "cold_start_report_incompatible_or_incomplete",
    }


async def _backend_metadata(websocket_url: str, timeout_seconds: float) -> dict[str, Any]:
    try:
        import httpx
    except ImportError as exc:
        raise EvaluationError("Voice benchmarking requires the httpx package") from exc
    url = _ready_url(websocket_url)
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise EvaluationError(f"Backend readiness endpoint is unavailable at {url}: {exc}") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise EvaluationError(f"Backend readiness endpoint returned non-JSON at {url}") from exc
    if (
        response.status_code != 200
        or not isinstance(payload, dict)
        or payload.get("status") != "ready"
    ):
        raise EvaluationError(
            f"Backend is not ready for a qualifying voice benchmark at {url}: "
            f"HTTP {response.status_code}, payload={payload!r}"
        )
    checks = payload.get("checks")
    sarvam = checks.get("sarvam") if isinstance(checks, dict) else None
    if not isinstance(sarvam, dict) or sarvam.get("ready") is not True:
        raise EvaluationError("Backend readiness does not verify an initialized Sarvam provider")
    endpoint = sarvam.get("endpoint")
    model = sarvam.get("model")
    endpoint_parts = urlsplit(str(endpoint or ""))
    real_endpoint = endpoint_parts.scheme == "wss" and endpoint_parts.hostname == "api.sarvam.ai"
    credentialed_smoke = sarvam.get("credentialed_smoke_verified") is True
    model_verified = isinstance(model, str) and model.casefold().startswith("saaras")
    if not real_endpoint or not model_verified or not credentialed_smoke:
        raise EvaluationError(
            "Qualifying voice mode requires readiness evidence for the real Sarvam "
            "wss://api.sarvam.ai provider, a Saaras model, and "
            f"credentialed_smoke_verified=true; observed {sarvam!r}"
        )
    return {
        "ready_url": url,
        "status_code": response.status_code,
        "readiness": payload,
        "real_provider_evidence": {
            "verified": True,
            "provider": "sarvam",
            "endpoint": endpoint,
            "model": model,
            "credentialed_smoke_verified": True,
        },
    }


def _language(value: Any, *, row: int) -> str:
    rendered = str(value or Language.UNKNOWN.value)
    try:
        return str(Language(rendered).value)
    except ValueError as exc:
        raise EvaluationError(f"Row {row} has unsupported language {rendered!r}") from exc


def _prepare_text_rows(records: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    selected = records if limit is None else records[:limit]
    if limit is not None and limit < 1:
        raise EvaluationError("--limit must be positive")
    prepared: list[dict[str, Any]] = []
    for row_number, row in enumerate(selected, start=1):
        query, query_source_field = select_query_and_field(row, row=row_number)
        prepared.append(
            {
                **row,
                "query_id": require_text(row, "query_id", row=row_number),
                "query": query,
                "query_source_field": query_source_field,
                "language": (
                    Language.ENGLISH.value
                    if query_source_field == "english_query"
                    else _language(row.get("language"), row=row_number)
                ),
            }
        )
    enforce_distinct(prepared, id_field="query_id", content_field="query")
    return prepared


def _prepare_voice_rows(
    records: list[dict[str, Any]], fixture: Path, limit: int | None
) -> list[dict[str, Any]]:
    selected = records if limit is None else records[:limit]
    if limit is not None and limit < 1:
        raise EvaluationError("--limit must be positive")
    prepared: list[dict[str, Any]] = []
    seen_audio: dict[str, int] = {}
    for row_number, row in enumerate(selected, start=1):
        clip_id = require_text(row, "clip_id", row=row_number)
        explicit_expected = row.get("expected_transcript")
        if isinstance(explicit_expected, str) and explicit_expected.strip():
            expected_transcript = explicit_expected.strip()
            expected_transcript_source = "expected_transcript"
        else:
            expected_transcript, expected_transcript_source = select_query_and_field(
                row, row=row_number
            )
        try:
            query, query_source_field = select_query_and_field(row, row=row_number)
        except EvaluationError:
            query = expected_transcript
            query_source_field = expected_transcript_source
        raw_path = Path(require_text(row, "audio_path", row=row_number))
        audio_path = raw_path if raw_path.is_absolute() else fixture.parent / raw_path
        if not audio_path.is_file():
            raise EvaluationError(f"Row {row_number} PCM fixture does not exist: {audio_path}")
        size = audio_path.stat().st_size
        if size == 0 or size % 2:
            raise EvaluationError(
                f"Row {row_number} must contain non-empty 16-bit PCM with an even byte count: "
                f"{audio_path}"
            )
        if size > MAX_AUDIO_BYTES:
            raise EvaluationError(f"Row {row_number} exceeds the backend 60-second audio limit")
        digest = file_sha256(audio_path)
        trailing_silence_ms = _trailing_silence_ms(audio_path.read_bytes())
        if digest in seen_audio:
            raise EvaluationError(
                f"Rows {seen_audio[digest]} and {row_number} contain identical PCM bytes; "
                "voice benchmark clips must be distinct"
            )
        seen_audio[digest] = row_number
        source_type = str(row.get("source_type") or "unreported")
        if source_type not in {"human", "synthetic", "unreported"}:
            raise EvaluationError(
                f"Row {row_number} source_type must be human, synthetic, or unreported"
            )
        prepared.append(
            {
                **row,
                "clip_id": clip_id,
                "query": query,
                "query_source_field": query_source_field,
                "expected_transcript": expected_transcript,
                "expected_transcript_source": expected_transcript_source,
                "audio_path": str(audio_path.resolve()),
                "audio_sha256": digest,
                "audio_bytes": size,
                "audio_duration_ms": size / (16_000 * 2) * 1_000,
                "trailing_silence_ms": trailing_silence_ms,
                "language": _language(row.get("language"), row=row_number),
                "condition": str(row.get("condition") or "unreported"),
                "source_type": source_type,
            }
        )
    enforce_distinct(prepared, id_field="clip_id")
    seen_expected: dict[str, int] = {}
    for row_number, row in enumerate(prepared, start=1):
        normalized_expected = normalize_transcript(str(row["expected_transcript"]))
        if not normalized_expected:
            raise EvaluationError(
                f"Row {row_number} expected_transcript is empty after normalization"
            )
        if normalized_expected in seen_expected:
            raise EvaluationError(
                f"Rows {seen_expected[normalized_expected]} and {row_number} have the "
                "same normalized expected transcript; voice requests must be distinct"
            )
        seen_expected[normalized_expected] = row_number
    return prepared


async def _voice_request(
    row: dict[str, Any],
    *,
    websocket_url: str,
    timeout_seconds: float,
    chunk_ms: int,
    pace_audio: bool,
    api_token: str | None,
) -> dict[str, Any]:
    try:
        import websockets
    except ImportError as exc:
        raise EvaluationError("Voice benchmarking requires the websockets package") from exc
    request_id = f"bench_{uuid.uuid4().hex}"
    chunk_bytes = 16_000 * 2 * chunk_ms // 1_000
    audio = Path(str(row["audio_path"])).read_bytes()
    started_ns: int | None = None
    terminal_task: asyncio.Task[tuple[dict[str, Any], int]] | None = None
    try:
        async with asyncio.timeout(timeout_seconds):
            headers = {"Authorization": f"Bearer {api_token}"} if api_token is not None else None
            async with websockets.connect(
                websocket_url,
                max_size=8 * 1024 * 1024,
                additional_headers=headers,
            ) as socket:

                async def receive_terminal() -> tuple[dict[str, Any], int]:
                    while True:
                        received = json.loads(await socket.recv())
                        if not isinstance(received, dict):
                            continue
                        if received.get("type") in {"answer", "error"}:
                            return received, time.perf_counter_ns()

                terminal_task = asyncio.create_task(receive_terminal())
                await socket.send(
                    json.dumps(
                        {
                            "type": "start",
                            "version": "1",
                            "request_id": request_id,
                            "encoding": "pcm_s16le",
                            "sample_rate_hz": 16_000,
                            "language": row["language"],
                        }
                    )
                )
                for sequence, offset in enumerate(range(0, len(audio), chunk_bytes)):
                    chunk = audio[offset : offset + chunk_bytes]
                    await socket.send(
                        json.dumps(
                            {
                                "type": "audio_chunk",
                                "version": "1",
                                "sequence": sequence,
                                "audio_b64": base64.b64encode(chunk).decode("ascii"),
                            }
                        )
                    )
                    if pace_audio and offset + chunk_bytes < len(audio):
                        await asyncio.sleep(len(chunk) / (16_000 * 2))
                started_ns = time.perf_counter_ns()
                await socket.send(json.dumps({"type": "end_of_stream", "version": "1"}))
                message, received_ns = await terminal_task
                event_type = message.get("type")
                latency_ms = (received_ns - started_ns) / 1_000_000
                payload = message.get("payload")
                payload = payload if isinstance(payload, dict) else {}
                timings = payload.get("timings_ms")
                timings = timings if isinstance(timings, dict) else {}
                answer = payload.get("answer")
                citations = payload.get("citations")
                citation_count = len(citations) if isinstance(citations, list) else 0
                state = payload.get("state")
                answer_mode = payload.get("answer_mode")
                has_cited_answer = (
                    isinstance(answer, str) and bool(answer.strip()) and citation_count > 0
                )
                return {
                    "terminal_event": event_type,
                    "client_end_marker_to_terminal_ms": latency_ms,
                    "server_timings_ms": dict(timings),
                    "server_total_after_final_audio_ms": _float_or_none(
                        timings.get("total_after_final_audio")
                    ),
                    "completed_answer": isinstance(answer, str) and bool(answer.strip()),
                    "answer_mode": answer_mode,
                    "pipeline_state": state,
                    "citation_count": citation_count,
                    "verified_completed_response": (state == "COMPLETED" and has_cited_answer),
                    "verified_evidence_response": (
                        (state == "DEADLINE_FALLBACK" or answer_mode == "evidence_fallback")
                        and has_cited_answer
                    ),
                    "observed_transcript": payload.get("transcript"),
                    "guardrail_reason": (
                        payload.get("guardrail", {}).get("reason")
                        if isinstance(payload.get("guardrail"), dict)
                        else None
                    ),
                    "response_request_id": message.get("request_id"),
                    "request_id_matches": message.get("request_id") == request_id,
                    "error": payload if event_type == "error" else None,
                }
    except EvaluationError:
        raise
    except Exception as exc:
        return {
            "terminal_event": None,
            "client_end_marker_to_terminal_ms": None,
            "server_timings_ms": {},
            "server_total_after_final_audio_ms": None,
            "completed_answer": False,
            "answer_mode": None,
            "pipeline_state": None,
            "citation_count": 0,
            "verified_completed_response": False,
            "verified_evidence_response": False,
            "observed_transcript": None,
            "guardrail_reason": None,
            "response_request_id": None,
            "request_id_matches": None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    finally:
        if terminal_task is not None:
            if not terminal_task.done():
                terminal_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await terminal_task
        audio = b""


async def _text_request(
    row: dict[str, Any], orchestrator: Any, *, deadline_ms: int | None
) -> dict[str, Any]:
    started_ns = time.perf_counter_ns()
    try:
        response = await orchestrator.process_text(
            row["query"],
            language=Language(row.get("language") or Language.UNKNOWN.value),
            request_id=f"bench_{row['query_id']}",
            deadline_ms=deadline_ms,
        )
        latency_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
        return {
            "terminal_event": "answer",
            "client_end_marker_to_terminal_ms": latency_ms,
            "server_timings_ms": dict(response.timings_ms),
            "server_total_after_final_audio_ms": _float_or_none(
                response.timings_ms.get("total_after_final_audio")
            ),
            "completed_answer": bool(response.answer),
            "answer_mode": response.answer_mode.value,
            "pipeline_state": response.state.value,
            "citation_count": len(response.citations),
            "verified_completed_response": (
                response.state.value == "COMPLETED"
                and bool(response.answer)
                and bool(response.citations)
            ),
            "verified_evidence_response": (
                (
                    response.state.value == "DEADLINE_FALLBACK"
                    or response.answer_mode.value == "evidence_fallback"
                )
                and bool(response.answer)
                and bool(response.citations)
            ),
            "observed_transcript": response.transcript,
            "guardrail_reason": (
                response.guardrail.reason.value if response.guardrail.reason else None
            ),
            "response_request_id": response.request_id,
            "request_id_matches": response.request_id == f"bench_{row['query_id']}",
            "error": None,
        }
    except Exception as exc:
        return {
            "terminal_event": None,
            "client_end_marker_to_terminal_ms": None,
            "server_timings_ms": {},
            "server_total_after_final_audio_ms": None,
            "completed_answer": False,
            "answer_mode": None,
            "pipeline_state": None,
            "citation_count": 0,
            "verified_completed_response": False,
            "verified_evidence_response": False,
            "observed_transcript": None,
            "guardrail_reason": None,
            "response_request_id": None,
            "request_id_matches": None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


async def _bounded_map(
    rows: list[dict[str, Any]],
    concurrency: int,
    operation: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(concurrency)

    async def invoke(row: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await operation(row)

    return list(await asyncio.gather(*(invoke(row) for row in rows)))


def _metrics(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    durations = [
        float(row[field])
        for row in rows
        if isinstance(row.get(field), int | float) and not isinstance(row.get(field), bool)
    ]
    metrics: dict[str, Any] = dict(
        latency_metrics(
            durations,
            total_requests=len(rows),
            completed_answers=sum(bool(row.get("completed_answer")) for row in rows),
        )
    )
    timing_status_field = (
        "client_timing_status"
        if field == "client_end_marker_to_terminal_ms"
        else "server_timing_status"
    )
    timing_counts = Counter(str(row.get(timing_status_field)) for row in rows)
    outcome_counts = Counter(str(row.get("outcome_classification")) for row in rows)
    metrics.update(
        {
            "retained_request_count": len(rows),
            "timing_coverage": len(durations) / len(rows) if rows else 0.0,
            "missing_timing_count": timing_counts.get("missing_timing", 0),
            "request_failure_count": outcome_counts.get("request_failure", 0),
            "excluded_from_percentiles_count": len(rows) - len(durations),
            "timing_status_counts": dict(sorted(timing_counts.items())),
            "outcome_classification_counts": dict(sorted(outcome_counts.items())),
        }
    )
    return metrics


def _server_stage_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stage_names = sorted(
        {
            str(stage)
            for row in rows
            for timings in [row.get("server_timings_ms")]
            if isinstance(timings, Mapping)
            for stage in timings
            if str(stage) not in SPECULATIVE_COUNTER_FIELDS
        }
    )
    completed_answers = sum(bool(row.get("completed_answer")) for row in rows)
    result: dict[str, dict[str, Any]] = {}
    for stage in stage_names:
        durations = [
            duration
            for row in rows
            for timings in [row.get("server_timings_ms")]
            if isinstance(timings, Mapping)
            for duration in [_float_or_none(timings.get(stage))]
            if duration is not None
        ]
        metrics: dict[str, Any] = dict(
            latency_metrics(
                durations,
                total_requests=len(rows),
                completed_answers=completed_answers,
            )
        )
        metrics.update(
            {
                "retained_request_count": len(rows),
                "timing_coverage": len(durations) / len(rows) if rows else 0.0,
                "missing_timing_count": len(rows) - len(durations),
                "excluded_from_percentiles_count": len(rows) - len(durations),
            }
        )
        result[stage] = metrics
    return result


def _speculative_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    launched_values: list[float] = []
    reused_values: list[float] = []
    jointly_reported = 0
    inconsistent_rows = 0
    invalid_counter_rows = 0
    launched_without_duration_rows = 0
    for row in rows:
        timings = row.get("server_timings_ms")
        if not isinstance(timings, Mapping):
            continue
        launched = _float_or_none(timings.get("speculative_launched"))
        reused = _float_or_none(timings.get("speculative_reused"))
        raw_counter_present = "speculative_launched" in timings or "speculative_reused" in timings
        counters_binary = launched in {0.0, 1.0} and reused in {0.0, 1.0}
        if raw_counter_present and not counters_binary:
            invalid_counter_rows += 1
        if launched is not None:
            launched_values.append(launched)
        if reused is not None:
            reused_values.append(reused)
        if launched is not None and reused is not None:
            jointly_reported += 1
            if reused > launched:
                inconsistent_rows += 1
            if launched == 1.0 and _float_or_none(timings.get("speculative_retrieval")) is None:
                launched_without_duration_rows += 1
    launched_total = sum(launched_values)
    reused_total = sum(reused_values)
    full_coverage = bool(rows) and jointly_reported == len(rows)
    counts_consistent = (
        inconsistent_rows == 0 and invalid_counter_rows == 0 and reused_total <= launched_total
    )
    return {
        "request_count": len(rows),
        "speculative_launched_total": launched_total,
        "speculative_reused_total": reused_total,
        "launched_reported_request_count": len(launched_values),
        "reused_reported_request_count": len(reused_values),
        "jointly_reported_request_count": jointly_reported,
        "timing_coverage": jointly_reported / len(rows) if rows else 0.0,
        "reuse_rate": reused_total / launched_total if launched_total else None,
        "inconsistent_row_count": inconsistent_rows,
        "invalid_counter_row_count": invalid_counter_rows,
        "launched_without_duration_row_count": launched_without_duration_rows,
        "counts_consistent": counts_consistent,
        "qualification_ready": (
            full_coverage and counts_consistent and launched_without_duration_rows == 0
        ),
    }


def _timing_field_evidence(
    rows: list[dict[str, Any]],
    field: str,
    *,
    scope: str,
    allow_empty_scope: bool = False,
) -> dict[str, Any]:
    reported = sum(
        _float_or_none(timings.get(field)) is not None
        for row in rows
        for timings in [row.get("server_timings_ms")]
        if isinstance(timings, Mapping)
    )
    request_count = len(rows)
    coverage = reported / request_count if request_count else 0.0
    return {
        "scope": scope,
        "request_count": request_count,
        "reported_request_count": reported,
        "missing_request_count": request_count - reported,
        "timing_coverage": coverage,
        "passed": (request_count == 0 and allow_empty_scope)
        or (request_count > 0 and reported == request_count),
    }


def _server_timing_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    verified_rows = [row for row in rows if row.get("verified_response") is True]
    completed_rows = [row for row in rows if row.get("verified_completed_response") is True]
    checks: dict[str, dict[str, Any]] = {}
    for field in CANONICAL_PROVIDER_TIMING_FIELDS:
        checks[field] = _timing_field_evidence(
            rows,
            field,
            scope="all_measured_voice_requests",
        )
    for field in CANONICAL_VERIFIED_INTERNAL_TIMING_FIELDS:
        checks[field] = _timing_field_evidence(
            verified_rows,
            field,
            scope="verified_completed_or_evidence_responses",
        )
    for field in CANONICAL_COMPLETED_INTERNAL_TIMING_FIELDS:
        checks[field] = _timing_field_evidence(
            completed_rows,
            field,
            scope="verified_completed_responses",
            allow_empty_scope=True,
        )
    failed_fields = [field for field, evidence in checks.items() if not evidence["passed"]]
    return {
        "passed": not failed_fields,
        "failed_fields": failed_fields,
        "checks": checks,
        "policy": {
            "provider_fields_require_full_measured_coverage": list(
                CANONICAL_PROVIDER_TIMING_FIELDS
            ),
            "verified_internal_fields_require_full_relevant_coverage": list(
                CANONICAL_VERIFIED_INTERNAL_TIMING_FIELDS
            ),
            "completed_internal_fields_require_full_relevant_coverage": list(
                CANONICAL_COMPLETED_INTERNAL_TIMING_FIELDS
            ),
            "missing_values_are_never_zero_filled": True,
        },
    }


async def run(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = load_records(args.fixture)
    if args.startup_condition == "cold" and args.mode != "voice":
        raise EvaluationError("Cold-start evidence is supported only in real voice mode")
    if args.mode == "voice":
        rows = _prepare_voice_rows(records, args.fixture, args.limit)
    else:
        rows = _prepare_text_rows(records, args.limit)
    if args.warmup >= len(rows):
        raise EvaluationError(
            f"--warmup ({args.warmup}) must leave at least one measured request "
            f"from {len(rows)} rows"
        )
    measured_count = len(rows) - args.warmup
    if args.startup_condition == "cold" and (args.warmup != 0 or measured_count != 1):
        raise EvaluationError(
            "A cold-start report must use --warmup 0 and exactly one measured request; "
            "restart the backend immediately before the run."
        )
    effective_minimum_requests = max(DEFAULT_MINIMUM_REQUESTS, args.minimum_requests)
    effective_target_requests = max(DEFAULT_TARGET_REQUESTS, args.target_requests)
    size_qualification = (
        "non_primary_cold_start"
        if args.startup_condition == "cold"
        else require_minimum_cases(
            measured_count,
            effective_minimum_requests,
            suite="Latency benchmark",
            allow_small_smoke=args.allow_small_smoke,
        )
    )
    qualification = (
        "non_qualifying_text_smoke"
        if args.mode == "text-smoke"
        else (
            "non_qualifying_pending_voice_validation"
            if size_qualification == "qualifying"
            else size_qualification
        )
    )
    if (
        args.mode == "voice"
        and size_qualification == "qualifying"
        and measured_count < effective_target_requests
        and not (args.under_target_reason or "").strip()
    ):
        raise EvaluationError(
            "A qualifying voice run below --target-requests requires "
            "--under-target-reason to document the limitation"
        )
    metadata = base_metadata(
        command="run_latency_benchmark",
        fixture=args.fixture,
        cache_policy=args.cache_policy,
        concurrency=args.concurrency,
        qualification=qualification,
    )
    metadata.update(
        {
            "mode": args.mode,
            "measurement_start": (
                "immediately before sending end_of_stream"
                if args.mode == "voice"
                else "immediately before process_text (non-qualifying smoke)"
            ),
            "measurement_end": "complete terminal answer/error payload received",
            "warmup_count": args.warmup,
            "measured_request_count": measured_count,
            "minimum_request_count": effective_minimum_requests,
            "target_request_count": effective_target_requests,
            "under_target_reason": args.under_target_reason,
            "human_recorded_waiver_reason": args.human_recorded_waiver_reason,
            "pace_audio": args.pace_audio,
            "chunk_ms": args.chunk_ms,
            "deadline_ms": args.deadline_ms,
            "maximum_trailing_silence_ms": args.maximum_trailing_silence_ms,
            "websocket_url": args.websocket_url if args.mode == "voice" else None,
            "startup_condition": args.startup_condition,
            "startup_condition_definition": (
                "fresh backend process before the sole measured request"
                if args.startup_condition == "cold"
                else "models, provider path, and index warmed before measured requests"
            ),
            "voice_auth_header_configured": bool(os.getenv("RAG_VOICE_API_TOKEN", "").strip()),
            "qualifying": False,
            "query_result_cache_policy": (
                "disabled_and_distinct_queries"
                if args.cache_policy == "disabled"
                else args.cache_policy
            ),
        }
    )

    if args.mode == "voice":
        metadata["backend"] = await _backend_metadata(args.websocket_url, args.timeout_seconds)
        _require_voice_deadline_match(metadata["backend"], args.deadline_ms)
        if args.startup_condition == "cold":
            _require_fresh_cold_runtime(metadata["backend"])
        readiness = metadata["backend"]["readiness"]
        metadata["corpus"] = readiness.get("checks", {}) if isinstance(readiness, dict) else {}
        compatibility = _benchmark_compatibility(metadata, args)
        metadata["compatibility"] = compatibility
        metadata["compatibility_fingerprint"] = _compatibility_fingerprint(compatibility)

        voice_api_token = os.getenv("RAG_VOICE_API_TOKEN", "").strip() or None

        async def operation(row: dict[str, Any]) -> dict[str, Any]:
            return await _voice_request(
                row,
                websocket_url=args.websocket_url,
                timeout_seconds=args.timeout_seconds,
                chunk_ms=args.chunk_ms,
                pace_audio=args.pace_audio,
                api_token=voice_api_token,
            )

        warmup_results = []
        for row in rows[: args.warmup]:
            warmup_results.append(await operation(row))
        measured_results = await _bounded_map(rows[args.warmup :], args.concurrency, operation)
    else:
        async with initialized_services() as services:
            orchestrator = services.orchestrator
            assert orchestrator is not None
            metadata["corpus"] = corpus_metadata(services)

            async def operation(row: dict[str, Any]) -> dict[str, Any]:
                return await _text_request(row, orchestrator, deadline_ms=args.deadline_ms)

            warmup_results = []
            for row in rows[: args.warmup]:
                warmup_results.append(await operation(row))
            measured_results = await _bounded_map(rows[args.warmup :], args.concurrency, operation)

    raw_rows: list[dict[str, Any]] = []
    for index, (fixture_row, result) in enumerate(
        zip(rows, [*warmup_results, *measured_results], strict=True)
    ):
        request_failed = (
            result.get("terminal_event") in {None, "error"}
            or result.get("request_id_matches") is False
        )
        client_timed = isinstance(
            result.get("client_end_marker_to_terminal_ms"), int | float
        ) and not isinstance(result.get("client_end_marker_to_terminal_ms"), bool)
        server_timed = isinstance(
            result.get("server_total_after_final_audio_ms"), int | float
        ) and not isinstance(result.get("server_total_after_final_audio_ms"), bool)
        expected_transcript = fixture_row.get("expected_transcript")
        observed_transcript = result.get("observed_transcript")
        transcript_similarity: float | None = None
        transcript_exact_match: bool | None = None
        transcript_match: bool | None = None
        if (
            args.mode == "voice"
            and isinstance(expected_transcript, str)
            and isinstance(observed_transcript, str)
            and observed_transcript.strip()
        ):
            transcript_similarity = normalized_edit_similarity(
                expected_transcript, observed_transcript
            )
            transcript_exact_match = normalize_transcript(
                expected_transcript
            ) == normalize_transcript(observed_transcript)
            transcript_match = transcript_similarity >= args.minimum_transcript_similarity
        raw_rows.append(
            {
                "sample_index": index,
                "included_in_percentiles": index >= args.warmup,
                "mode": args.mode,
                "query_id": fixture_row.get("query_id"),
                "clip_id": fixture_row.get("clip_id"),
                "query": fixture_row.get("query"),
                "query_source_field": fixture_row.get("query_source_field"),
                "expected_transcript": expected_transcript,
                "expected_transcript_source": fixture_row.get("expected_transcript_source"),
                "normalized_transcript_similarity": transcript_similarity,
                "transcript_exact_match": transcript_exact_match,
                "transcript_match": transcript_match,
                "language": fixture_row.get("language", Language.UNKNOWN.value),
                "condition": fixture_row.get("condition", "unreported"),
                "source_type": fixture_row.get("source_type", "unreported"),
                "audio_path": fixture_row.get("audio_path"),
                "audio_sha256": fixture_row.get("audio_sha256"),
                "audio_bytes": fixture_row.get("audio_bytes"),
                "audio_duration_ms": fixture_row.get("audio_duration_ms"),
                "trailing_silence_ms": fixture_row.get("trailing_silence_ms"),
                "outcome_classification": (
                    "request_failure"
                    if request_failed
                    else (
                        "completed_answer"
                        if result.get("completed_answer")
                        else "terminal_abstention"
                    )
                ),
                "client_timing_status": "timed" if client_timed else "missing_timing",
                "server_timing_status": "timed" if server_timed else "missing_timing",
                "verified_response": bool(
                    not request_failed
                    and (
                        result.get("verified_completed_response")
                        or result.get("verified_evidence_response")
                    )
                ),
                **result,
            }
        )
    measured_rows = [row for row in raw_rows if row["included_in_percentiles"]]
    client_metrics = _metrics(measured_rows, "client_end_marker_to_terminal_ms")
    server_metrics = _metrics(measured_rows, "server_total_after_final_audio_ms")
    server_stage_latency = _server_stage_metrics(measured_rows)
    speculative_retrieval = _speculative_metrics(measured_rows)
    server_timing_evidence = (
        _server_timing_evidence(measured_rows)
        if args.mode == "voice"
        else {
            "passed": False,
            "failed_fields": [],
            "checks": {},
            "reason": "canonical_voice_timing_evidence_not_applicable_to_text_smoke",
        }
    )
    summary: dict[str, Any] = {
        "metadata": metadata,
        "client_end_marker_to_terminal": client_metrics,
        "server_total_after_final_audio": server_metrics,
        "server_stage_latency": server_stage_latency,
        "server_timing_evidence": server_timing_evidence,
        "speculative_retrieval": speculative_retrieval,
        "terminal_event_counts": dict(
            sorted(Counter(str(row.get("terminal_event")) for row in measured_rows).items())
        ),
        "language_counts": dict(
            sorted(Counter(str(row.get("language")) for row in measured_rows).items())
        ),
        "condition_counts": dict(
            sorted(Counter(str(row.get("condition")) for row in measured_rows).items())
        ),
        "source_type_counts": dict(
            sorted(Counter(str(row.get("source_type")) for row in measured_rows).items())
        ),
        "failure_count": sum(
            row.get("outcome_classification") == "request_failure" for row in measured_rows
        ),
    }
    if args.mode == "voice":
        similarities = [
            float(row["normalized_transcript_similarity"])
            for row in measured_rows
            if isinstance(row.get("normalized_transcript_similarity"), int | float)
            and not isinstance(row.get("normalized_transcript_similarity"), bool)
        ]
        matched_transcripts = sum(row.get("transcript_match") is True for row in measured_rows)
        exact_transcripts = sum(row.get("transcript_exact_match") is True for row in measured_rows)
        explicit_expected = sum(
            row.get("expected_transcript_source") == "expected_transcript" for row in measured_rows
        )
        verified_completed = sum(
            row.get("verified_completed_response") is True for row in measured_rows
        )
        verified_evidence = sum(
            row.get("verified_evidence_response") is True for row in measured_rows
        )
        verified_total = sum(row.get("verified_response") is True for row in measured_rows)
        languages = {str(row.get("language")) for row in measured_rows}
        conditions = {str(row.get("condition")).casefold() for row in measured_rows}
        durations = [
            float(row["audio_duration_ms"])
            for row in measured_rows
            if isinstance(row.get("audio_duration_ms"), int | float)
        ]
        clean_present = any("clean" in condition for condition in conditions)
        noisy_present = any(
            "noisy" in condition or "noise" in condition for condition in conditions
        )
        short_present = any(duration < 3_000 for duration in durations)
        long_present = any(duration >= 3_000 for duration in durations)
        source_labels_complete = all(
            row.get("source_type") in {"human", "synthetic"} for row in measured_rows
        )
        human_recorded_count = sum(row.get("source_type") == "human" for row in measured_rows)
        human_target_or_waiver = human_recorded_count >= 60 or bool(
            (args.human_recorded_waiver_reason or "").strip()
        )
        trailing_silence_values = [
            float(row["trailing_silence_ms"])
            for row in measured_rows
            if isinstance(row.get("trailing_silence_ms"), int | float)
        ]
        maximum_observed_trailing_silence_ms = (
            max(trailing_silence_values) if trailing_silence_values else None
        )
        expected_compatibility = metadata.get("compatibility")
        assert isinstance(expected_compatibility, Mapping)
        cold_start = (
            _cold_start_evidence(
                args.cold_start_report,
                expected_compatibility=expected_compatibility,
            )
            if args.startup_condition == "warm"
            else {
                "verified": False,
                "reason": "current_cold_report_integrity_evaluated_separately",
            }
        )
        transcript_match_coverage = matched_transcripts / measured_count
        verified_response_coverage = verified_total / measured_count
        provider_verified = (
            metadata.get("backend", {}).get("real_provider_evidence", {}).get("verified") is True
        )
        qualification_checks = {
            "minimum_distinct_samples": {
                "passed": size_qualification == "qualifying",
                "observed": measured_count,
                "required": effective_minimum_requests,
            },
            "real_provider_and_credentialed_smoke": {
                "passed": provider_verified,
                "observed": provider_verified,
                "required": True,
            },
            "explicit_distinct_expected_transcripts": {
                "passed": explicit_expected == measured_count,
                "observed": explicit_expected,
                "required": measured_count,
            },
            "transcript_match_coverage": {
                "passed": (transcript_match_coverage >= args.minimum_transcript_match_coverage),
                "observed": transcript_match_coverage,
                "required": args.minimum_transcript_match_coverage,
            },
            "verified_response_coverage": {
                "passed": (verified_response_coverage >= args.minimum_verified_response_coverage),
                "observed": verified_response_coverage,
                "required": args.minimum_verified_response_coverage,
            },
            "client_timing_coverage": {
                "passed": client_metrics["timing_coverage"] == 1.0,
                "observed": client_metrics["timing_coverage"],
                "required": 1.0,
            },
            "server_timing_coverage": {
                "passed": server_metrics["timing_coverage"] == 1.0,
                "observed": server_metrics["timing_coverage"],
                "required": 1.0,
            },
            "canonical_server_stage_evidence": {
                "passed": server_timing_evidence["passed"] is True,
                "observed": {
                    "failed_fields": server_timing_evidence["failed_fields"],
                    "checks": server_timing_evidence["checks"],
                },
                "required": "full coverage for every relevant canonical provider/internal stage",
            },
            "speculative_counter_evidence": {
                "passed": speculative_retrieval["qualification_ready"] is True,
                "observed": speculative_retrieval,
                "required": (
                    "launched/reused reported on every measured request as consistent binary "
                    "counters, with speculative_retrieval timing whenever launched"
                ),
            },
            "zero_request_failures": {
                "passed": summary["failure_count"] == 0,
                "observed": summary["failure_count"],
                "required": 0,
            },
            "primary_concurrency": {
                "passed": args.concurrency == 1,
                "observed": args.concurrency,
                "required": 1,
            },
            "required_language_groups": {
                "passed": {"hi", "en", "hi-en"}.issubset(languages),
                "observed": sorted(languages),
                "required": ["en", "hi", "hi-en"],
            },
            "clean_and_noisy_groups": {
                "passed": clean_present and noisy_present,
                "observed": sorted(conditions),
                "required": ["clean", "noisy"],
            },
            "short_and_long_groups": {
                "passed": short_present and long_present,
                "observed": {
                    "short_under_3000ms": short_present,
                    "long_at_least_3000ms": long_present,
                },
                "required": {"short_under_3000ms": True, "long_at_least_3000ms": True},
            },
            "source_labels_complete": {
                "passed": source_labels_complete,
                "observed": source_labels_complete,
                "required": True,
            },
            "query_result_cache_disabled": {
                "passed": args.cache_policy == "disabled",
                "observed": args.cache_policy,
                "required": "disabled",
            },
            "human_recorded_target_or_documented_infeasibility": {
                "passed": human_target_or_waiver,
                "observed": {
                    "human_recorded_clips": human_recorded_count,
                    "waiver_reason": args.human_recorded_waiver_reason,
                },
                "required": "60 clips or a non-empty feasibility explanation",
            },
            "real_time_audio_pacing": {
                "passed": args.pace_audio is True,
                "observed": args.pace_audio,
                "required": True,
            },
            "bounded_trailing_silence": {
                "passed": (
                    maximum_observed_trailing_silence_ms is not None
                    and maximum_observed_trailing_silence_ms <= args.maximum_trailing_silence_ms
                ),
                "observed": maximum_observed_trailing_silence_ms,
                "required_maximum_ms": args.maximum_trailing_silence_ms,
            },
            "warm_primary_links_compatible_cold_run": {
                "passed": (args.startup_condition == "warm" and cold_start["verified"] is True),
                "observed": {
                    "startup_condition": args.startup_condition,
                    "cold_start_report": cold_start,
                },
                "required": "warm primary run plus compatible cold voice report",
            },
        }
        voice_quality: dict[str, Any] = {
            "minimum_transcript_similarity": args.minimum_transcript_similarity,
            "transcript_observed_count": len(similarities),
            "transcript_match_count": matched_transcripts,
            "transcript_exact_match_count": exact_transcripts,
            "transcript_match_coverage": transcript_match_coverage,
            "mean_normalized_transcript_similarity": (
                sum(similarities) / len(similarities) if similarities else None
            ),
            "minimum_observed_transcript_similarity": (min(similarities) if similarities else None),
            "verified_completed_response_count": verified_completed,
            "verified_evidence_response_count": verified_evidence,
            "verified_response_count": verified_total,
            "verified_response_coverage": verified_response_coverage,
            "human_recorded_clip_count": human_recorded_count,
            "human_recorded_target": 60,
            "human_recorded_target_met": human_recorded_count >= 60,
            "maximum_observed_trailing_silence_ms": (maximum_observed_trailing_silence_ms),
            "cold_start_evidence": cold_start,
            "qualification_checks": qualification_checks,
        }
        summary["voice_quality"] = voice_quality
        qualifying = args.startup_condition == "warm" and all(
            bool(check["passed"]) for check in qualification_checks.values()
        )
        if args.startup_condition == "cold":
            summary["qualifying"] = False
            cold_checks = _cold_report_checks(summary)
            cold_failed_checks = [name for name, passed in cold_checks.items() if not passed]
            cold_integrity = {
                "valid": not cold_failed_checks,
                "primary_qualifying": False,
                "process_instance_id": (
                    metadata.get("compatibility", {})
                    .get("backend_identity", {})
                    .get("process", {})
                    .get("process_instance_id")
                ),
                "checks": cold_checks,
                "failed_checks": cold_failed_checks,
                "reason": (
                    None if not cold_failed_checks else "cold_start_integrity_checks_failed"
                ),
            }
            summary["cold_start_integrity"] = cold_integrity
            voice_quality["cold_start_evidence"] = {
                "verified": not cold_failed_checks,
                "current_report": True,
                "reason": cold_integrity["reason"],
            }
            metadata["qualification"] = (
                "cold_start_integrity_valid_non_primary"
                if not cold_failed_checks
                else "cold_start_integrity_invalid_non_primary"
            )
        else:
            metadata["qualification"] = (
                "qualifying_voice"
                if qualifying
                else (
                    "non_qualifying_small_smoke"
                    if size_qualification != "qualifying"
                    else "non_qualifying_voice_criteria_failed"
                )
            )
        metadata["qualifying"] = qualifying
        summary["qualifying"] = qualifying
    else:
        metadata["qualifying"] = False
        summary["qualifying"] = False
    return summary, raw_rows


def _markdown(summary: dict[str, Any]) -> str:
    metadata = summary["metadata"]
    client = summary["client_end_marker_to_terminal"]
    server = summary["server_total_after_final_audio"]
    stages = summary.get("server_stage_latency")
    timing_evidence = summary.get("server_timing_evidence")
    speculative = summary.get("speculative_retrieval")
    warning = (
        "This is a text-path smoke test and does not qualify as a voice latency result."
        if metadata["mode"] == "text-smoke"
        else "Percentiles use distinct PCM clips and exclude warmups."
    )
    quality_lines: list[str] = []
    voice_quality = summary.get("voice_quality")
    if isinstance(voice_quality, dict):
        quality_lines = [
            "",
            "## Voice qualification evidence",
            "",
            markdown_table(
                (
                    "Transcript matches",
                    "Exact matches",
                    "Match coverage",
                    "Mean similarity",
                    "Verified completed",
                    "Verified evidence",
                    "Verified coverage",
                    "Failures",
                ),
                [
                    (
                        voice_quality["transcript_match_count"],
                        voice_quality["transcript_exact_match_count"],
                        voice_quality["transcript_match_coverage"],
                        voice_quality["mean_normalized_transcript_similarity"],
                        voice_quality["verified_completed_response_count"],
                        voice_quality["verified_evidence_response_count"],
                        voice_quality["verified_response_coverage"],
                        summary["failure_count"],
                    )
                ],
            ),
            "",
            markdown_table(
                ("Qualification check", "Passed", "Observed", "Required"),
                (
                    (
                        name,
                        check["passed"],
                        check["observed"],
                        check.get("required", check.get("required_maximum_ms")),
                    )
                    for name, check in voice_quality["qualification_checks"].items()
                ),
            ),
        ]
    stage_lines: list[str] = []
    if isinstance(stages, Mapping) and stages:
        stage_lines = [
            "",
            "## Server stage latency",
            "",
            markdown_table(
                (
                    "Stage",
                    "Requests",
                    "Samples",
                    "Timing coverage",
                    "P50 ms",
                    "P70 ms",
                    "P95 ms",
                    "P100 ms (max)",
                ),
                (
                    (
                        name,
                        metric.get("request_count"),
                        metric.get("sample_count"),
                        metric.get("timing_coverage"),
                        metric.get("p50_ms"),
                        metric.get("p70_ms"),
                        metric.get("p95_ms"),
                        metric.get("p100_ms"),
                    )
                    for name, metric in stages.items()
                    if isinstance(metric, Mapping)
                ),
            ),
        ]
    timing_evidence_lines: list[str] = []
    evidence_checks = (
        timing_evidence.get("checks") if isinstance(timing_evidence, Mapping) else None
    )
    if isinstance(evidence_checks, Mapping) and evidence_checks:
        timing_evidence_lines = [
            "",
            "## Canonical timing evidence",
            "",
            markdown_table(
                ("Required field", "Scope", "Requests", "Reported", "Coverage", "Passed"),
                (
                    (
                        name,
                        evidence.get("scope"),
                        evidence.get("request_count"),
                        evidence.get("reported_request_count"),
                        evidence.get("timing_coverage"),
                        evidence.get("passed"),
                    )
                    for name, evidence in evidence_checks.items()
                    if isinstance(evidence, Mapping)
                ),
            ),
        ]
    speculative_lines: list[str] = []
    if isinstance(speculative, Mapping):
        speculative_lines = [
            "",
            "## Speculative retrieval counters",
            "",
            markdown_table(
                (
                    "Requests",
                    "Launched",
                    "Reused",
                    "Reuse rate",
                    "Timing coverage",
                    "Inconsistent rows",
                    "Invalid counters",
                    "Launched without duration",
                    "Qualification ready",
                ),
                [
                    (
                        speculative.get("request_count"),
                        speculative.get("speculative_launched_total"),
                        speculative.get("speculative_reused_total"),
                        speculative.get("reuse_rate"),
                        speculative.get("timing_coverage"),
                        speculative.get("inconsistent_row_count"),
                        speculative.get("invalid_counter_row_count"),
                        speculative.get("launched_without_duration_row_count"),
                        speculative.get("qualification_ready"),
                    )
                ],
            ),
        ]
    cold_lines: list[str] = []
    cold_integrity = summary.get("cold_start_integrity")
    if isinstance(cold_integrity, Mapping):
        cold_checks = cold_integrity.get("checks")
        cold_lines = [
            "",
            "## Cold-start integrity (non-primary)",
            "",
            (
                "This one-shot report is integrity-valid but never serves as the primary "
                "latency qualification."
                if cold_integrity.get("valid") is True
                else "This one-shot report failed one or more cold-start integrity checks."
            ),
        ]
        if isinstance(cold_checks, Mapping):
            cold_lines.extend(
                [
                    "",
                    markdown_table(
                        ("Integrity check", "Passed"),
                        ((name, passed) for name, passed in cold_checks.items()),
                    ),
                ]
            )
    return "\n".join(
        [
            "# Latency benchmark",
            "",
            f"Qualification: **{metadata['qualification']}**",
            "",
            f"> {warning}",
            "",
            markdown_table(
                (
                    "Metric",
                    "Requests",
                    "Samples",
                    "Answer coverage",
                    "Timing coverage",
                    "Excluded",
                    "P50 ms",
                    "P70 ms",
                    "P95 ms",
                    "P100 ms (max)",
                ),
                [
                    (
                        "Client marker → terminal payload",
                        client.get("request_count"),
                        client.get("sample_count"),
                        client.get("answer_coverage"),
                        client.get("timing_coverage"),
                        client.get("excluded_from_percentiles_count"),
                        client.get("p50_ms"),
                        client.get("p70_ms"),
                        client.get("p95_ms"),
                        client.get("p100_ms"),
                    ),
                    (
                        "Backend total_after_final_audio",
                        server.get("request_count"),
                        server.get("sample_count"),
                        server.get("answer_coverage"),
                        server.get("timing_coverage"),
                        server.get("excluded_from_percentiles_count"),
                        server.get("p50_ms"),
                        server.get("p70_ms"),
                        server.get("p95_ms"),
                        server.get("p100_ms"),
                    ),
                ],
            ),
            "",
            (
                f"Warmups excluded: {metadata['warmup_count']}. Concurrency: "
                f"{metadata['concurrency']}. Cache policy: {metadata['cache_policy']}."
            ),
            *stage_lines,
            *timing_evidence_lines,
            *speculative_lines,
            *quality_lines,
            *cold_lines,
            "",
            (
                "P100 is the exact maximum measured value. Raw requests, including "
                "failures and excluded warmups, are in the sibling JSONL and CSV artifacts. "
                "Missing timings remain in the denominator and are counted as excluded, "
                "never silently dropped."
            ),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.fixture is None:
        args.fixture = (
            DEFAULT_CORPUS_EVALUATION_FIXTURE
            if args.mode == "text-smoke"
            else BACKEND_ROOT / "evaluation" / "private" / "voice-latency.jsonl"
        )
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.warmup < 0:
        parser.error("--warmup must be non-negative")
    if args.minimum_requests < DEFAULT_MINIMUM_REQUESTS:
        parser.error(
            f"--minimum-requests cannot be below {DEFAULT_MINIMUM_REQUESTS}; "
            "use --allow-small-smoke for a non-qualifying smaller run"
        )
    if args.target_requests < DEFAULT_TARGET_REQUESTS:
        parser.error(f"--target-requests cannot be below {DEFAULT_TARGET_REQUESTS}")
    if args.target_requests < args.minimum_requests:
        parser.error("--target-requests must not be below --minimum-requests")
    if args.concurrency < 1:
        parser.error("--concurrency must be positive")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.mode == "voice" and args.deadline_ms is None:
        parser.error("real voice benchmarking requires an explicit --deadline-ms")
    if args.deadline_ms is not None and args.deadline_ms < 20:
        parser.error("--deadline-ms must be at least 20")
    if args.chunk_ms < 10 or args.chunk_ms > 1_000:
        parser.error("--chunk-ms must be between 10 and 1000")
    if args.maximum_trailing_silence_ms < 0:
        parser.error("--maximum-trailing-silence-ms must be non-negative")
    for name in (
        "minimum_transcript_similarity",
        "minimum_transcript_match_coverage",
        "minimum_verified_response_coverage",
    ):
        if not 0.0 <= getattr(args, name) <= 1.0:
            parser.error(f"--{name.replace('_', '-')} must be between 0 and 1")
    try:
        summary, rows = asyncio.run(run(args))
        paths = write_report_bundle(
            args.output_prefix, rows=rows, summary=summary, markdown=_markdown(summary)
        )
    except EvaluationError as exc:
        parser.exit(2, f"error: {exc}\n")
    print_artifacts(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
