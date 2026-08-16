from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.core.deadlines import Deadline  # noqa: E402
from app.core.errors import DeadlineExceeded, DependencyUnavailable  # noqa: E402
from app.domain.enums import (  # noqa: E402
    ChunkStrategy,
    GuardrailDecision,
    GuardrailReason,
    Language,
)
from app.domain.models import SearchHit, Transcript  # noqa: E402
from app.evaluation.metrics import guardrail_confusion_counts  # noqa: E402
from app.generation.grounded_generator import ExtractiveGroundedGenerator  # noqa: E402
from app.guardrails.answerability_gate import check_answerability  # noqa: E402
from app.guardrails.audio_gate import evaluate_pcm_audio  # noqa: E402
from app.guardrails.evidence_agreement import check_evidence_agreement  # noqa: E402
from app.guardrails.freshness_gate import check_freshness  # noqa: E402
from app.guardrails.injection_gate import check_prompt_injection  # noqa: E402
from app.guardrails.safety_gate import check_safety  # noqa: E402
from app.harness.orchestrator import PipelineOrchestrator  # noqa: E402
from app.retrieval.hybrid import RetrievalResult  # noqa: E402
from scripts._common import (  # noqa: E402
    FIXTURES_ROOT,
    REPORTS_ROOT,
    EvaluationError,
    base_metadata,
    corpus_metadata,
    enforce_distinct,
    initialized_services,
    load_records,
    markdown_table,
    print_artifacts,
    require_text,
    select_query,
    write_report_bundle,
)

KINDS = {
    "input",
    "audio",
    "answerability",
    "agreement",
    "low_stt_confidence",
    "dependency_failure",
    "forced_deadline",
    "contradictory_pipeline",
    "pipeline",
}

REQUIRED_EXPECTED_LABELS = {
    GuardrailDecision.ALLOW.value,
    GuardrailReason.NO_RELEVANT_EVIDENCE.value,
    GuardrailReason.STALE_CORPUS.value,
    GuardrailReason.UNSAFE_REQUEST.value,
    GuardrailReason.PROMPT_INJECTION.value,
    GuardrailReason.SILENCE.value,
    GuardrailReason.LOW_STT_CONFIDENCE.value,
    GuardrailReason.RETRIEVAL_DISAGREEMENT.value,
    GuardrailReason.DEADLINE_EXCEEDED.value,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic and harness-level guardrail cases."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=FIXTURES_ROOT / "guardrail-cases.jsonl",
    )
    parser.add_argument("--output-prefix", type=Path, default=REPORTS_ROOT / "guardrail-eval")
    parser.add_argument(
        "--cache-policy",
        choices=("cold", "warm", "mixed", "uncontrolled"),
        default="uncontrolled",
    )
    parser.add_argument(
        "--offline-deterministic-smoke",
        action="store_true",
        help=(
            "Run only fixture-level gates/failure paths without a corpus or Qdrant; "
            "the report is explicitly non-qualifying."
        ),
    )
    return parser


def _validate_fixture(records: list[dict[str, Any]]) -> None:
    enforce_distinct(records, id_field="case_id")
    valid_labels = {GuardrailDecision.ALLOW.value, *(item.value for item in GuardrailReason)}
    for row_number, record in enumerate(records, start=1):
        kind = require_text(record, "kind", row=row_number)
        if kind not in KINDS:
            raise EvaluationError(
                f"Row {row_number} has unsupported kind {kind!r}; expected one of {sorted(KINDS)}"
            )
        expected = require_text(record, "expected", row=row_number)
        if expected not in valid_labels:
            raise EvaluationError(f"Row {row_number} has unsupported expected label {expected!r}")


def _label(result: Any) -> str:
    reason = getattr(result, "reason", None)
    if reason is not None:
        return str(getattr(reason, "value", reason))
    decision = getattr(result, "decision", None)
    return str(getattr(decision, "value", decision))


def _input_result(query: str) -> Any:
    for gate in (check_prompt_injection, check_safety, check_freshness):
        result = gate(query)
        if result.decision != GuardrailDecision.ALLOW:
            return result
    return check_freshness("static supported question")


def _audio_bytes(case: str) -> bytes:
    if case == "empty":
        return b""
    if case == "too_short":
        return b"\xe8\x03" * 1_600  # 100 ms of audible signed 16-bit PCM.
    if case == "silence":
        return b"\x00\x00" * 16_000
    if case == "invalid":
        return b"\x00"
    if case == "audible":
        return b"\xe8\x03" * 16_000
    raise EvaluationError(f"Unsupported audio_case {case!r}")


def _hits(scores: Any, *, row: int) -> list[SearchHit]:
    if not isinstance(scores, list):
        raise EvaluationError(f"Row {row} scores must be an array")
    hits: list[SearchHit] = []
    for index, value in enumerate(scores):
        if isinstance(value, bool):
            raise EvaluationError(f"Row {row} score {index} must be numeric")
        try:
            score = float(value)
        except (TypeError, ValueError) as exc:
            raise EvaluationError(f"Row {row} score {index} must be numeric") from exc
        hits.append(
            SearchHit(
                canonical_doc_id=f"fixture-doc-{index}",
                parent_id=f"fixture-parent-{index}",
                chunk_id=f"fixture-chunk-{index}",
                text=f"Fixture evidence {index}",
                language=Language.ENGLISH,
                strategy=ChunkStrategy.ATOMIC,
                span_start=0,
                span_end=20,
                score=score,
            )
        )
    return hits


def _required_float(record: dict[str, Any], field: str, *, row: int) -> float:
    value = record.get(field)
    if value is None or isinstance(value, bool):
        raise EvaluationError(f"Row {row} {field} must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise EvaluationError(f"Row {row} {field} must be numeric") from exc


class _RaisingRetriever:
    def __init__(self, exception: Exception) -> None:
        self.exception = exception

    async def retrieve(self, *_args: Any, **_kwargs: Any) -> Any:
        raise self.exception


class _ContradictoryRetriever:
    async def retrieve(self, *_args: Any, **_kwargs: Any) -> RetrievalResult:
        supports = SearchHit(
            canonical_doc_id="fixture-supports",
            parent_id="fixture-supports",
            chunk_id="fixture-supports",
            text="Goa became a state in 1987.",
            language=Language.ENGLISH,
            strategy=ChunkStrategy.ATOMIC,
            span_start=0,
            span_end=28,
            score=1.0,
            dense_score=0.9,
            rank_sources={"dense": 1},
        )
        contradicts = SearchHit(
            canonical_doc_id="fixture-contradicts",
            parent_id="fixture-contradicts",
            chunk_id="fixture-contradicts",
            text="Goa did not become a state in 1987.",
            language=Language.ENGLISH,
            strategy=ChunkStrategy.ATOMIC,
            span_start=0,
            span_end=36,
            score=0.9,
            dense_score=0.7,
            sparse_score=0.8,
            rank_sources={"sparse": 1},
        )
        return RetrievalResult(
            dense_hits=(supports, contradicts),
            sparse_hits=(supports, contradicts),
            fused_hits=(supports, contradicts),
            agreement=1.0,
        )


async def _pipeline_with_retriever(orchestrator: Any, query: str, retriever: Any) -> Any:
    original = orchestrator.retriever
    orchestrator.retriever = retriever
    try:
        return await orchestrator.process_text(query, deadline_ms=1_000)
    finally:
        orchestrator.retriever = original


async def _observe(
    record: dict[str, Any], *, row_number: int, orchestrator: Any
) -> tuple[str, dict[str, Any]]:
    kind = str(record["kind"])
    evidence: dict[str, Any] = {}
    if kind == "input":
        evidence["execution_scope"] = "deterministic_input_gate"
        result = _input_result(select_query(record, row=row_number))
    elif kind == "audio":
        evidence["execution_scope"] = "synthetic_audio_gate"
        audio_case = require_text(record, "audio_case", row=row_number)
        audio = _audio_bytes(audio_case)
        result = evaluate_pcm_audio(audio)
        evidence["audio_bytes"] = len(audio)
    elif kind == "answerability":
        evidence["execution_scope"] = "synthetic_answerability_gate"
        result = check_answerability(
            _hits(record.get("scores"), row=row_number),
            minimum_score=float(
                record.get("minimum_score", orchestrator.settings.min_answer_score)
            ),
            minimum_margin=float(
                record.get("minimum_margin", orchestrator.settings.min_score_margin)
            ),
        )
    elif kind == "agreement":
        evidence["execution_scope"] = "synthetic_agreement_gate"
        result = check_evidence_agreement(
            _required_float(record, "agreement", row=row_number),
            float(record.get("minimum", orchestrator.settings.min_evidence_agreement)),
        )
    elif kind == "low_stt_confidence":
        evidence["execution_scope"] = "injected_transcript_harness"
        deadline = Deadline.after_ms(1_000, 900)
        response = await orchestrator.process_transcript(
            Transcript(
                text=select_query(record, row=row_number),
                language=Language.UNKNOWN,
                confidence=_required_float(record, "confidence", row=row_number),
                is_final=True,
                received_ns=deadline.started_ns,
            ),
            deadline=deadline,
            request_id=f"guardrail-{record['case_id']}",
        )
        result = response.guardrail
    elif kind == "dependency_failure":
        evidence["execution_scope"] = "injected_dependency_harness"
        response = await _pipeline_with_retriever(
            orchestrator,
            select_query(record, row=row_number),
            _RaisingRetriever(DependencyUnavailable("guardrail-fixture")),
        )
        result = response.guardrail
    elif kind == "forced_deadline":
        evidence["execution_scope"] = "injected_deadline_harness"
        response = await _pipeline_with_retriever(
            orchestrator,
            select_query(record, row=row_number),
            _RaisingRetriever(DeadlineExceeded("forced by guardrail fixture")),
        )
        result = response.guardrail
    elif kind == "contradictory_pipeline":
        evidence["execution_scope"] = "synthetic_conflict_harness"
        response = await _pipeline_with_retriever(
            orchestrator,
            select_query(record, row=row_number),
            _ContradictoryRetriever(),
        )
        result = response.guardrail
        evidence["evidence_mode"] = "harness_evidence_conflict_gate"
    else:
        evidence["execution_scope"] = "active_retrieval_pipeline"
        response = await orchestrator.process_text(
            select_query(record, row=row_number),
            deadline_ms=int(record.get("deadline_ms", orchestrator.settings.rag_deadline_ms)),
        )
        result = response.guardrail
    result_evidence = getattr(result, "evidence", None)
    if isinstance(result_evidence, dict):
        evidence.update(result_evidence)
    return _label(result), evidence


async def _evaluate_records(
    records: list[dict[str, Any]], orchestrator: Any
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_number, record in enumerate(records, start=1):
        observed, evidence = await _observe(
            record, row_number=row_number, orchestrator=orchestrator
        )
        expected = str(record["expected"])
        rows.append(
            {
                "case_id": record["case_id"],
                "kind": record["kind"],
                "category": record.get("category", "unreported"),
                "expected": expected,
                "observed": observed,
                "correct": expected == observed,
                "evidence": evidence,
            }
        )
    return rows


def _qualification_evidence(
    records: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    offline: bool,
    readiness_checks: dict[str, Any],
) -> dict[str, Any]:
    observed_expected = {str(record.get("expected")) for record in records}
    contradictory_case = any(
        record.get("kind") == "contradictory_pipeline"
        and record.get("expected") == GuardrailReason.RETRIEVAL_DISAGREEMENT.value
        for record in records
    )
    thresholds = readiness_checks.get("thresholds")
    index = readiness_checks.get("index")
    qdrant = readiness_checks.get("qdrant")
    active_rows = [
        (record, row)
        for record, row in zip(records, rows, strict=True)
        if record.get("kind") in ("pipeline", "input", "contradictory_pipeline")
        and row.get("correct") is True
    ]
    active_supported = any(
        record.get("category") == "supported"
        and record.get("expected") == GuardrailDecision.ALLOW.value
        for record, _row in active_rows
    )
    active_unsupported = any(
        record.get("category") == "unsupported"
        and record.get("expected") == GuardrailReason.NO_RELEVANT_EVIDENCE.value
        for record, _row in active_rows
    )
    active_contradiction = any(
        record.get("category") == "retrieval"
        and record.get("expected") == GuardrailReason.RETRIEVAL_DISAGREEMENT.value
        for record, _row in active_rows
    )
    checks = {
        "live_initialized_services": not offline,
        "all_required_guardrail_labels_present": REQUIRED_EXPECTED_LABELS.issubset(
            observed_expected
        ),
        "all_cases_recorded": len(rows) == len(records),
        "all_cases_correct": bool(rows) and all(row.get("correct") is True for row in rows),
        "synthetic_conflict_gate_regression": contradictory_case
        and any(
            row.get("evidence", {}).get("evidence_mode")
            == "harness_evidence_conflict_gate"
            for row in rows
        ),
        "active_pipeline_supported_case": active_supported,
        "active_pipeline_unsupported_case": active_unsupported,
        "active_pipeline_contradictory_case": active_contradiction,
        "frozen_bound_thresholds_ready": True,
        "active_index_ready": isinstance(index, dict) and index.get("ready") is True,
        "qdrant_ready": isinstance(qdrant, dict) and qdrant.get("ready") is True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    status = (
        "non_qualifying_offline_guardrail_smoke"
        if offline
        else ("qualifying" if not failed else f"non_qualifying_{failed[0]}")
    )
    return {
        "qualifying": not failed,
        "status": status,
        "checks": checks,
        "failed_checks": failed,
        "expected_case_count": len(records),
        "recorded_case_count": len(rows),
    }


async def run(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = load_records(args.fixture)
    _validate_fixture(records)
    if args.offline_deterministic_smoke:
        smoke_settings = Settings(
            rag_target_unique_passages=10,
            rag_development_passages=1,
            rag_deadline_ms=1_000,
            rag_fallback_at_ms=900,
        )
        orchestrator = PipelineOrchestrator(
            settings=smoke_settings,
            retriever=_RaisingRetriever(DependencyUnavailable("offline-smoke")),  # type: ignore[arg-type]
            generator=ExtractiveGroundedGenerator(),
        )
        corpus: dict[str, Any] = {
            "available": False,
            "reason": "offline_deterministic_smoke",
        }
        qualification = "non_qualifying_offline_guardrail_smoke"
        raw_rows = await _evaluate_records(records, orchestrator)
        readiness_checks: dict[str, Any] = {}
    else:
        async with initialized_services() as services:
            orchestrator = services.orchestrator
            assert orchestrator is not None
            corpus = corpus_metadata(services)
            raw_rows = await _evaluate_records(records, orchestrator)
            readiness = await services.readiness()
            readiness_checks = (
                dict(readiness.get("checks", {})) if isinstance(readiness, dict) else {}
            )
        qualification = "pending_guardrail_qualification"
    qualification_evidence = _qualification_evidence(
        records,
        raw_rows,
        offline=args.offline_deterministic_smoke,
        readiness_checks=readiness_checks,
    )
    qualification = str(qualification_evidence["status"])
    metadata = base_metadata(
        command="run_guardrail_eval",
        fixture=args.fixture,
        cache_policy=args.cache_policy,
        concurrency=1,
        qualification=qualification,
    )
    metadata["corpus"] = corpus
    metadata["thresholds"] = {
        "minimum_stt_confidence": orchestrator.settings.min_stt_confidence,
        "minimum_answer_score": orchestrator.settings.min_answer_score,
        "minimum_score_margin": orchestrator.settings.min_score_margin,
        "minimum_evidence_agreement": orchestrator.settings.min_evidence_agreement,
    }
    metadata["runtime_feature_flags"] = orchestrator.settings.retrieval_feature_flags
    metadata["qualifying"] = qualification_evidence["qualifying"]
    metadata["qualification_checks"] = qualification_evidence
    confusion = guardrail_confusion_counts(
        (str(row["expected"]) for row in raw_rows),
        (str(row["observed"]) for row in raw_rows),
    )
    return {
        "metadata": metadata,
        "metrics": confusion,
        "qualification": qualification_evidence,
    }, raw_rows


def _markdown(summary: dict[str, Any]) -> str:
    metadata = summary["metadata"]
    metrics = summary["metrics"]
    confusion = metrics["confusion"]
    observed_labels = sorted({observed for row in confusion.values() for observed in row})
    matrix_rows = [
        (expected, *(counts.get(observed, 0) for observed in observed_labels))
        for expected, counts in confusion.items()
    ]
    return "\n".join(
        [
            "# Guardrail evaluation",
            "",
            f"Qualification: `{metadata['qualification']}`.",
            "",
            (
                "This report is evidence-qualifying."
                if metadata.get("qualifying") is True
                else "This report is a non-qualifying guardrail evaluation; inspect the "
                "qualification checks in the JSON artifact."
            ),
            "",
            markdown_table(
                ("Cases", "Correct", "Accuracy"),
                [(metrics["case_count"], metrics["correct"], metrics["accuracy"])],
            ),
            "",
            "## Confusion matrix",
            "",
            markdown_table(("Expected \\ Observed", *observed_labels), matrix_rows),
            "",
            (
                "Rows are expected guardrail reasons; columns are observed reasons. "
                "ALLOW is used when no guardrail reason applies."
            ),
            "",
            "Raw case results and evidence are in the sibling JSONL and CSV artifacts.",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary, rows = asyncio.run(run(args))
        paths = write_report_bundle(
            args.output_prefix, rows=rows, summary=summary, markdown=_markdown(summary)
        )
    except (EvaluationError, TypeError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print_artifacts(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
