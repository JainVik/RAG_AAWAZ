from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts._common import (  # noqa: E402
    REPORTS_ROOT,
    EvaluationError,
    file_sha256,
    load_json_object,
    markdown_table,
    print_artifacts,
    utc_now_iso,
    write_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare qualifying held-out retrieval reports from independently built "
            "corpus/index sizes and quantify marginal quality, latency, and storage changes."
        )
    )
    parser.add_argument(
        "reports",
        nargs="+",
        type=Path,
        help="Two or more JSON summaries emitted by run_retrieval_eval.py.",
    )
    parser.add_argument(
        "--minimum-recall-gain",
        type=float,
        default=0.01,
        help=(
            "Absolute Recall@10 gain required to justify moving to the next corpus "
            "size (default: 0.01)."
        ),
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=REPORTS_ROOT / "corpus-scaling-comparison",
        help="Output path without an extension.",
    )
    return parser


def _mapping(value: Any, *, field: str, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationError(f"{path}: {field} must be an object")
    return value


def _number(value: Any, *, field: str, path: Path, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvaluationError(f"{path}: {field} must be numeric")
    result = float(value)
    if positive and result <= 0:
        raise EvaluationError(f"{path}: {field} must be positive")
    return result


def _compatibility(metadata: dict[str, Any], *, path: Path) -> dict[str, Any]:
    fixture = _mapping(metadata.get("fixture"), field="metadata.fixture", path=path)
    thresholds = _mapping(
        metadata.get("frozen_thresholds"),
        field="metadata.frozen_thresholds",
        path=path,
    )
    artifacts = _mapping(
        thresholds.get("retrieval_artifacts"),
        field="metadata.frozen_thresholds.retrieval_artifacts",
        path=path,
    )
    return {
        "fixture_sha256": fixture.get("sha256"),
        "query_field": metadata.get("query_field"),
        "deadline_ms": metadata.get("deadline_ms"),
        "cache_policy": metadata.get("cache_policy"),
        "concurrency": metadata.get("concurrency"),
        "dense_model": artifacts.get("dense_model"),
        "model_revision": artifacts.get("model_revision"),
        "retrieval_contract_version": artifacts.get("retrieval_contract_version"),
        "retrieval_contract_sha256": artifacts.get("retrieval_contract_sha256"),
    }


def _candidate(path: Path) -> dict[str, Any]:
    report = load_json_object(path)
    metadata = _mapping(report.get("metadata"), field="metadata", path=path)
    if metadata.get("command") != "run_retrieval_eval":
        raise EvaluationError(f"{path}: expected a run_retrieval_eval report")
    metrics = _mapping(report.get("metrics"), field="metrics", path=path)
    overall = _mapping(metrics.get("overall"), field="metrics.overall", path=path)
    latency = _mapping(report.get("latency"), field="latency", path=path)
    corpus = _mapping(metadata.get("corpus"), field="metadata.corpus", path=path)
    if corpus.get("available") is not True:
        raise EvaluationError(f"{path}: corpus/index metadata is unavailable")

    document_count = int(
        _number(
            corpus.get("document_count"),
            field="metadata.corpus.document_count",
            path=path,
            positive=True,
        )
    )
    point_count = int(
        _number(
            corpus.get("point_count", corpus.get("chunk_count")),
            field="metadata.corpus.point_count",
            path=path,
            positive=True,
        )
    )
    disk_bytes = int(
        _number(
            corpus.get("disk_bytes", corpus.get("index_size_bytes")),
            field="metadata.corpus.disk_bytes",
            path=path,
            positive=True,
        )
    )
    build_seconds = _number(
        corpus.get("build_time_seconds"),
        field="metadata.corpus.build_time_seconds",
        path=path,
        positive=True,
    )
    return {
        "report_path": str(path.resolve()),
        "report_sha256": file_sha256(path),
        "qualifying": metadata.get("qualifying") is True,
        "qualification": metadata.get("qualification"),
        "document_count": document_count,
        "point_count": point_count,
        "vectors_per_document": point_count / document_count,
        "artifact_disk_bytes": disk_bytes,
        "build_time_seconds": build_seconds,
        "recall_at_1": _number(overall.get("recall_at_1"), field="recall_at_1", path=path),
        "recall_at_5": _number(overall.get("recall_at_5"), field="recall_at_5", path=path),
        "recall_at_10": _number(overall.get("recall_at_10"), field="recall_at_10", path=path),
        "mrr_at_10": _number(overall.get("mrr_at_10"), field="mrr_at_10", path=path),
        "ndcg_at_10": _number(overall.get("ndcg_at_10"), field="ndcg_at_10", path=path),
        "latency_mean_ms": _number(latency.get("mean_ms"), field="latency.mean_ms", path=path),
        "latency_p50_ms": _number(latency.get("p50_ms"), field="latency.p50_ms", path=path),
        "latency_p95_ms": _number(latency.get("p95_ms"), field="latency.p95_ms", path=path),
        "latency_p100_ms": _number(latency.get("p100_ms"), field="latency.p100_ms", path=path),
        "collection": corpus.get("collection"),
        "corpus_manifest_sha256": corpus.get("corpus_manifest_sha256"),
        "compatibility": _compatibility(metadata, path=path),
    }


def compare_reports(report_paths: list[Path], *, minimum_recall_gain: float) -> dict[str, Any]:
    if len(report_paths) < 2:
        raise EvaluationError("At least two retrieval reports are required")
    if not 0 <= minimum_recall_gain <= 1:
        raise EvaluationError("minimum_recall_gain must be between 0 and 1")

    candidates = sorted(
        (_candidate(path) for path in report_paths),
        key=lambda item: int(item["document_count"]),
    )
    document_counts = [int(item["document_count"]) for item in candidates]
    if len(set(document_counts)) != len(document_counts):
        raise EvaluationError("Each report must represent a distinct document count")

    compatibility = candidates[0]["compatibility"]
    mismatches = [
        {
            "report_path": candidate["report_path"],
            "fields": sorted(
                key
                for key, value in candidate["compatibility"].items()
                if value != compatibility.get(key)
            ),
        }
        for candidate in candidates[1:]
        if candidate["compatibility"] != compatibility
    ]
    if mismatches:
        raise EvaluationError(
            f"Reports are not comparable under one fixture/query/runtime contract: {mismatches}"
        )

    marginal: list[dict[str, Any]] = []
    recommended_documents = document_counts[-1]
    stop_reason = "largest_measured_candidate_required"
    for previous, current in zip(candidates, candidates[1:], strict=False):
        disk_delta = int(current["artifact_disk_bytes"]) - int(previous["artifact_disk_bytes"])
        recall_delta = float(current["recall_at_10"]) - float(previous["recall_at_10"])
        row = {
            "from_document_count": previous["document_count"],
            "to_document_count": current["document_count"],
            "recall_at_10_delta": recall_delta,
            "mrr_at_10_delta": float(current["mrr_at_10"]) - float(previous["mrr_at_10"]),
            "ndcg_at_10_delta": float(current["ndcg_at_10"]) - float(previous["ndcg_at_10"]),
            "latency_p95_ms_delta": float(current["latency_p95_ms"])
            - float(previous["latency_p95_ms"]),
            "artifact_disk_bytes_delta": disk_delta,
            "build_time_seconds_delta": float(current["build_time_seconds"])
            - float(previous["build_time_seconds"]),
            "recall_gain_meets_threshold": recall_delta > minimum_recall_gain,
        }
        marginal.append(row)
        if (
            recall_delta <= minimum_recall_gain
            and stop_reason == "largest_measured_candidate_required"
        ):
            recommended_documents = int(previous["document_count"])
            stop_reason = "next_candidate_recall_gain_not_material"

    checks = {
        "at_least_two_candidates": len(candidates) >= 2,
        "all_source_reports_qualifying": all(
            bool(candidate["qualifying"]) for candidate in candidates
        ),
        "same_held_out_fixture_and_runtime_contract": not mismatches,
        "distinct_document_counts": len(set(document_counts)) == len(document_counts),
        "distinct_corpus_manifests": len(
            {candidate["corpus_manifest_sha256"] for candidate in candidates}
        )
        == len(candidates),
        "distinct_collections": len({candidate["collection"] for candidate in candidates})
        == len(candidates),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": 1,
        "created_at": utc_now_iso(),
        "method": {
            "quality_metric": "absolute_recall_at_10_gain",
            "minimum_recall_gain": minimum_recall_gain,
            "selection_rule": (
                "Choose the smaller candidate before the first larger candidate whose "
                "absolute Recall@10 gain is at or below the threshold. Always inspect "
                "latency/storage deltas and robustness slices before production selection."
            ),
            "storage_scope": "local deterministic index artifacts, not live Qdrant resident memory",
        },
        "compatibility": compatibility,
        "candidates": candidates,
        "marginal_changes": marginal,
        "recommendation": {
            "document_count": recommended_documents,
            "reason": stop_reason,
            "provisional": bool(failed),
        },
        "qualification": {
            "qualifying": not failed,
            "status": "qualifying" if not failed else f"non_qualifying_{failed[0]}",
            "checks": checks,
            "failed_checks": failed,
        },
    }


def _markdown(summary: dict[str, Any]) -> str:
    candidates = summary["candidates"]
    changes = summary["marginal_changes"]
    recommendation = summary["recommendation"]
    qualification = summary["qualification"]
    lines = [
        "# Corpus scaling comparison",
        "",
        f"Qualification: **{qualification['status']}**",
        "",
        markdown_table(
            (
                "Documents",
                "Vectors",
                "Recall@10",
                "MRR@10",
                "nDCG@10",
                "P95 ms",
                "Artifact bytes",
                "Build seconds",
            ),
            (
                (
                    row["document_count"],
                    row["point_count"],
                    row["recall_at_10"],
                    row["mrr_at_10"],
                    row["ndcg_at_10"],
                    row["latency_p95_ms"],
                    row["artifact_disk_bytes"],
                    row["build_time_seconds"],
                )
                for row in candidates
            ),
        ),
        "",
        "## Marginal changes",
        "",
        markdown_table(
            (
                "From",
                "To",
                "Recall@10 delta",
                "MRR@10 delta",
                "P95 delta ms",
                "Artifact-byte delta",
                "Material gain",
            ),
            (
                (
                    row["from_document_count"],
                    row["to_document_count"],
                    row["recall_at_10_delta"],
                    row["mrr_at_10_delta"],
                    row["latency_p95_ms_delta"],
                    row["artifact_disk_bytes_delta"],
                    row["recall_gain_meets_threshold"],
                )
                for row in changes
            ),
        ),
        "",
        "## Recommendation",
        "",
        f"Measured stopping candidate: **{recommendation['document_count']} documents**.",
        f"Reason: `{recommendation['reason']}`.",
        "",
        (
            "This is provisional whenever qualification fails. Artifact bytes describe "
            "the deterministic local index outputs; measure live Qdrant storage and resident "
            "memory separately before deployment."
        ),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary = compare_reports(args.reports, minimum_recall_gain=args.minimum_recall_gain)
        json_path = args.output_prefix.with_suffix(".json")
        markdown_path = args.output_prefix.with_suffix(".md")
        write_json(json_path, summary)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(_markdown(summary) + "\n", encoding="utf-8")
        print_artifacts({"json": json_path, "markdown": markdown_path})
    except (EvaluationError, OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
