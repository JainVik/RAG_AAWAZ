from __future__ import annotations

import argparse
import itertools
import math
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.evaluation.thresholds import (  # noqa: E402
    RAW_DENSE_SCORE_CONTRACT_VERSION,
    RAW_DENSE_SCORE_KIND,
    RetrievalArtifactBinding,
    freeze_development_thresholds,
    retrieval_runtime_contract,
    retrieval_runtime_contract_sha256,
)
from app.retrieval.router import TIDE_ROUTER_CONTRACT_VERSION  # noqa: E402
from scripts._common import (  # noqa: E402
    REPORTS_ROOT,
    EvaluationError,
    base_metadata,
    enforce_distinct,
    file_sha256,
    load_json_object,
    load_records,
    markdown_table,
    print_artifacts,
    require_text,
    select_query,
    write_report_bundle,
)


def _backend_path(path: Path) -> Path:
    return path if path.is_absolute() else BACKEND_ROOT / path


def _runtime_threshold_path() -> Path:
    return _backend_path(get_settings().rag_thresholds_path)


def _runtime_index_manifest_path() -> Path:
    return _backend_path(get_settings().rag_data_dir) / "index" / "index-manifest.json"


def _runtime_corpus_manifest_path() -> Path:
    return _backend_path(get_settings().rag_data_dir) / "corpus" / "corpus-manifest.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calibrate deterministic answerability thresholds on development data only."
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument(
        "--frozen-output",
        type=Path,
        default=_runtime_threshold_path(),
        help="Defaults to Settings.rag_thresholds_path used by DefaultServices.",
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=REPORTS_ROOT / "threshold-calibration",
    )
    parser.add_argument(
        "--objective",
        choices=("balanced_accuracy", "f1", "accuracy"),
        default="balanced_accuracy",
    )
    parser.add_argument("--grid-points", type=int, default=16)
    parser.add_argument(
        "--corpus-manifest", type=Path, default=_runtime_corpus_manifest_path()
    )
    parser.add_argument(
        "--index-manifest", type=Path, default=_runtime_index_manifest_path()
    )
    return parser


def _bool(value: Any, *, row: int) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"true", "1", "yes", "answerable"}:
            return True
        if lowered in {"false", "0", "no", "unanswerable"}:
            return False
    raise EvaluationError(f"Row {row} is_answerable must be a boolean")


def _number(
    record: dict[str, Any],
    field: str,
    *,
    row: int,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = record.get(field)
    if value is None or isinstance(value, bool):
        raise EvaluationError(f"Row {row} {field} must be numeric")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise EvaluationError(f"Row {row} {field} must be numeric") from exc
    if not math.isfinite(parsed):
        raise EvaluationError(f"Row {row} {field} must be finite")
    if minimum is not None and parsed < minimum:
        raise EvaluationError(f"Row {row} {field} must be at least {minimum}")
    if maximum is not None and parsed > maximum:
        raise EvaluationError(f"Row {row} {field} must be at most {maximum}")
    return parsed


def _prepare(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    common_binding: RetrievalArtifactBinding | None = None
    for row_number, record in enumerate(records, start=1):
        split = require_text(record, "split", row=row_number)
        if split != "development":
            raise EvaluationError(
                f"Row {row_number} belongs to split {split!r}; calibration may use only "
                "the development split"
            )
        score_kind = require_text(record, "score_kind", row=row_number)
        score_contract_version = require_text(
            record, "score_contract_version", row=row_number
        )
        if score_kind != RAW_DENSE_SCORE_KIND:
            raise EvaluationError(
                f"Row {row_number} score_kind must be {RAW_DENSE_SCORE_KIND!r}; "
                "fused/RRF scores cannot calibrate answerability"
            )
        if score_contract_version != RAW_DENSE_SCORE_CONTRACT_VERSION:
            raise EvaluationError(
                f"Row {row_number} score_contract_version must be "
                f"{RAW_DENSE_SCORE_CONTRACT_VERSION!r}"
            )
        top_score = _number(
            record,
            "top_raw_dense_similarity",
            row=row_number,
            minimum=-1.0,
            maximum=1.0,
        )
        if "raw_dense_similarity_margin" in record:
            margin = _number(
                record,
                "raw_dense_similarity_margin",
                row=row_number,
                minimum=0.0,
            )
        else:
            margin = top_score - _number(
                record,
                "second_raw_dense_similarity",
                row=row_number,
                minimum=-1.0,
                maximum=1.0,
            )
        agreement = _number(
            record,
            "evidence_agreement",
            row=row_number,
            minimum=0.0,
            maximum=1.0,
        )
        raw_binding = record.get("retrieval_artifacts")
        if raw_binding is None:
            raise EvaluationError(
                f"Row {row_number} requires retrieval_artifacts from score_development.py"
            )
        try:
            row_binding = RetrievalArtifactBinding.model_validate(raw_binding)
        except ValidationError as exc:
            raise EvaluationError(
                f"Row {row_number} retrieval_artifacts is invalid: {exc}"
            ) from exc
        if common_binding is None:
            common_binding = row_binding
        elif row_binding != common_binding:
            raise EvaluationError(
                f"Row {row_number} retrieval_artifacts differs from earlier scored rows"
            )
        if margin < 0:
            raise EvaluationError(f"Row {row_number} score margin must not be negative")
        if not 0 <= agreement <= 1:
            raise EvaluationError(
                f"Row {row_number} evidence_agreement must be between 0 and 1"
            )
        prepared.append(
            {
                **record,
                "query_id": require_text(record, "query_id", row=row_number),
                "query": select_query(record, row=row_number),
                "is_answerable": _bool(record.get("is_answerable"), row=row_number),
                "top_raw_dense_similarity": top_score,
                "raw_dense_similarity_margin": margin,
                "score_kind": score_kind,
                "score_contract_version": score_contract_version,
                "evidence_agreement": agreement,
                "retrieval_artifacts": row_binding.model_dump(mode="json"),
            }
        )
    enforce_distinct(prepared, id_field="query_id", content_field="query")
    if {row["is_answerable"] for row in prepared} != {False, True}:
        raise EvaluationError(
            "Calibration fixture must include both answerable and unanswerable development cases"
        )
    return prepared


def _require_active_retrieval_binding(
    records: list[dict[str, Any]],
    active_binding: RetrievalArtifactBinding | None,
) -> RetrievalArtifactBinding:
    if active_binding is None:
        raise EvaluationError(
            "Calibration requires existing corpus/index manifests to bind frozen thresholds"
        )
    mismatched: list[str] = []
    for record in records:
        try:
            observed = RetrievalArtifactBinding.model_validate(
                record.get("retrieval_artifacts")
            )
        except ValidationError:
            mismatched.append(str(record["query_id"]))
            continue
        if observed != active_binding:
            mismatched.append(str(record["query_id"]))
    if mismatched:
        raise EvaluationError(
            "Scored rows do not match the active retrieval artifact binding: "
            + ", ".join(mismatched)
        )
    return active_binding


def _grid(values: list[float], points: int, *, anchors: tuple[float, ...]) -> list[float]:
    unique = sorted(set(values).union(anchors))
    if len(unique) <= points:
        return unique
    indices = {
        round(position * (len(unique) - 1) / (points - 1))
        for position in range(points)
    }
    return [unique[index] for index in sorted(indices)]


def _binary_metrics(expected: list[bool], observed: list[bool]) -> dict[str, float | int]:
    tp = sum(want and got for want, got in zip(expected, observed, strict=True))
    tn = sum(not want and not got for want, got in zip(expected, observed, strict=True))
    fp = sum(not want and got for want, got in zip(expected, observed, strict=True))
    fn = sum(want and not got for want, got in zip(expected, observed, strict=True))
    count = len(expected)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {
        "case_count": count,
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "accuracy": (tp + tn) / count if count else 0.0,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "balanced_accuracy": (recall + specificity) / 2,
        "answer_coverage": sum(observed) / count if count else 0.0,
    }


def _corpus_metadata(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "available": False,
            "reason": (
                "Calibration consumes precomputed development retrieval scores; "
                "no existing corpus manifest supplied"
            ),
            "path": str(path.resolve()) if path is not None else None,
        }
    return {
        "available": True,
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
        "manifest": load_json_object(path),
    }


def _retrieval_artifact_binding(
    *,
    index_manifest_path: Path | None,
    corpus_manifest_path: Path | None,
    runtime_settings: Any,
) -> tuple[RetrievalArtifactBinding | None, dict[str, Any]]:
    index_manifest = (
        load_json_object(index_manifest_path)
        if index_manifest_path is not None and index_manifest_path.is_file()
        else None
    )
    corpus_manifest_hash = (
        file_sha256(corpus_manifest_path)
        if corpus_manifest_path is not None and corpus_manifest_path.is_file()
        else None
    )
    if index_manifest is None:
        return None, {
            "status": "unbound",
            "reason": "No active index manifest was available at calibration",
        }

    declared_corpus_manifest_hash = (
        index_manifest.get("corpus_manifest_sha256")
        if index_manifest is not None
        else None
    )
    if (
        corpus_manifest_hash
        and declared_corpus_manifest_hash
        and corpus_manifest_hash != declared_corpus_manifest_hash
    ):
        raise EvaluationError(
            "Calibration corpus manifest does not match the supplied index manifest"
        )
    checksums = index_manifest.get("checksums") if index_manifest is not None else None
    binding = RetrievalArtifactBinding(
        index_manifest_sha256=(
            file_sha256(index_manifest_path)
            if index_manifest is not None and index_manifest_path is not None
            else None
        ),
        corpus_manifest_sha256=(
            corpus_manifest_hash or declared_corpus_manifest_hash
        ),
        corpus_artifact_sha256=(
            checksums.get("corpus") if isinstance(checksums, dict) else None
        ),
        chunk_build_id=(
            index_manifest.get("chunk_build_id") if index_manifest is not None else None
        ),
        collection=(
            index_manifest.get("collection") if index_manifest is not None else None
        ),
        dense_model=(
            index_manifest.get("dense_model") if index_manifest is not None else None
        ),
        model_revision=(
            index_manifest.get("model_revision") if index_manifest is not None else None
        ),
        retrieval_contract_version=TIDE_ROUTER_CONTRACT_VERSION,
        retrieval_contract_sha256=retrieval_runtime_contract_sha256(runtime_settings),
    )
    return binding, {
        "status": "bound",
        "index_manifest_path": (
            str(index_manifest_path.resolve())
            if index_manifest is not None and index_manifest_path is not None
            else None
        ),
        "corpus_manifest_path": (
            str(corpus_manifest_path.resolve())
            if corpus_manifest_hash and corpus_manifest_path is not None
            else None
        ),
        "retrieval_runtime_contract": retrieval_runtime_contract(runtime_settings),
        "binding": binding.model_dump(mode="json"),
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = _prepare(load_records(args.fixture))
    runtime_settings = get_settings()
    binding, binding_evidence = _retrieval_artifact_binding(
        index_manifest_path=getattr(args, "index_manifest", None),
        corpus_manifest_path=getattr(args, "corpus_manifest", None),
        runtime_settings=runtime_settings,
    )
    binding = _require_active_retrieval_binding(records, binding)
    score_grid = _grid(
        [row["top_raw_dense_similarity"] for row in records],
        args.grid_points,
        anchors=(-1.0,),
    )
    margin_grid = _grid(
        [row["raw_dense_similarity_margin"] for row in records],
        args.grid_points,
        anchors=(0.0,),
    )
    agreement_grid = _grid(
        [row["evidence_agreement"] for row in records],
        args.grid_points,
        anchors=(0.0, 1.0),
    )
    expected = [bool(row["is_answerable"]) for row in records]
    candidates: list[dict[str, Any]] = []
    for score, margin, agreement in itertools.product(
        score_grid, margin_grid, agreement_grid
    ):
        observed = [
            row["top_raw_dense_similarity"] >= score
            and row["raw_dense_similarity_margin"] >= margin
            and row["evidence_agreement"] >= agreement
            for row in records
        ]
        candidates.append(
            {
                "minimum_answer_score": score,
                "minimum_score_margin": margin,
                "minimum_evidence_agreement": agreement,
                "score_kind": RAW_DENSE_SCORE_KIND,
                "score_contract_version": RAW_DENSE_SCORE_CONTRACT_VERSION,
                **_binary_metrics(expected, observed),
            }
        )
    selected = max(
        candidates,
        key=lambda item: (
            item[args.objective],
            item["f1"],
            item["accuracy"],
            -item["false_positive"],
            -item["false_negative"],
            item["minimum_answer_score"],
            item["minimum_score_margin"],
            item["minimum_evidence_agreement"],
        ),
    )
    frozen = freeze_development_thresholds(
        args.frozen_output,
        args.fixture,
        minimum_answer_score=float(selected["minimum_answer_score"]),
        minimum_score_margin=float(selected["minimum_score_margin"]),
        minimum_evidence_agreement=float(selected["minimum_evidence_agreement"]),
        source_split="development",
        retrieval_artifacts=binding,
        development_query_contents=[str(row["query"]) for row in records],
    )
    metadata = base_metadata(
        command="calibrate_thresholds",
        fixture=args.fixture,
        cache_policy="not_applicable_precomputed_scores",
        concurrency=1,
        qualification="development_only_calibration",
    )
    metadata.update(
        {
            "objective": args.objective,
            "score_kind": RAW_DENSE_SCORE_KIND,
            "score_contract_version": RAW_DENSE_SCORE_CONTRACT_VERSION,
            "grid_points_per_dimension_max": args.grid_points,
            "candidate_count": len(candidates),
            "corpus": _corpus_metadata(args.corpus_manifest),
            "retrieval_artifact_binding": binding_evidence,
        }
    )
    summary = {
        "metadata": metadata,
        "selected": selected,
        "frozen_thresholds": frozen.model_dump(mode="json"),
        "frozen_output": str(args.frozen_output.resolve()),
        "frozen_output_sha256": file_sha256(args.frozen_output),
    }
    return summary, candidates


def _markdown(summary: dict[str, Any]) -> str:
    selected = summary["selected"]
    metadata = summary["metadata"]
    return "\n".join(
        [
            "# Development threshold calibration",
            "",
            (
                "> These thresholds were selected only from the development split "
                "and frozen before final evaluation."
            ),
            "",
            markdown_table(
                (
                    "Objective",
                    "Min answer score",
                    "Min score margin",
                    "Min evidence agreement",
                    "Balanced accuracy",
                    "F1",
                    "Accuracy",
                    "Answer coverage",
                ),
                [
                    (
                        metadata["objective"],
                        selected["minimum_answer_score"],
                        selected["minimum_score_margin"],
                        selected["minimum_evidence_agreement"],
                        selected["balanced_accuracy"],
                        selected["f1"],
                        selected["accuracy"],
                        selected["answer_coverage"],
                    )
                ],
            ),
            "",
            (
                f"Evaluated {metadata['candidate_count']} deterministic threshold "
                f"combinations. Frozen artifact: `{summary['frozen_output']}`."
            ),
            "",
            "Every candidate and its confusion counts are in the sibling JSONL and CSV artifacts.",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.grid_points < 2 or args.grid_points > 50:
        parser.error("--grid-points must be between 2 and 50")
    try:
        summary, rows = run(args)
        paths = write_report_bundle(
            args.output_prefix, rows=rows, summary=summary, markdown=_markdown(summary)
        )
    except (EvaluationError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"FROZEN: {args.frozen_output}")
    print_artifacts(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
