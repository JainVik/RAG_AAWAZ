from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.deadlines import Deadline  # noqa: E402
from app.evaluation.metrics import (  # noqa: E402
    RetrievalEvaluationRecord,
    grouped_retrieval_metrics,
    latency_metrics,
    retrieval_metrics,
)
from scripts._common import (  # noqa: E402
    DEFAULT_CORPUS_EVALUATION_FIXTURE,
    REPORTS_ROOT,
    EvaluationError,
    base_metadata,
    corpus_index_provenance,
    corpus_metadata,
    enforce_distinct,
    evaluation_qualification,
    final_threshold_provenance,
    held_out_provenance,
    initialized_services,
    load_records,
    markdown_table,
    print_artifacts,
    raw_dense_score_evidence,
    require_minimum_cases,
    require_text,
    select_query_and_field,
    service_index_manifest,
    write_report_bundle,
)

DEFAULT_MINIMUM_QUERIES = 500


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the initialized hybrid retriever on distinct held-out queries."
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_CORPUS_EVALUATION_FIXTURE)
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        help=(
            "Source CorpusWriter manifest for --fixture; defaults to its sibling "
            "manifest. Required with a partition outside the corpus directory."
        ),
    )
    parser.add_argument(
        "--partition-manifest",
        type=Path,
        help=(
            "Manifest emitted by split_evaluation_fixture.py; defaults to a sibling "
            "partition-manifest.json when present."
        ),
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=REPORTS_ROOT / "retrieval-eval",
        help="Artifact path without an extension.",
    )
    parser.add_argument(
        "--query-field",
        choices=("auto", "query", "english_query", "translated_query"),
        default="auto",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--minimum-queries", type=int, default=DEFAULT_MINIMUM_QUERIES)
    parser.add_argument("--deadline-ms", type=int, default=5_000)
    parser.add_argument("--allow-small-smoke", action="store_true")
    parser.add_argument(
        "--post-hoc-regression-confirmation",
        action="store_true",
        help=(
            "Record metrics after a final fixture has already influenced a change. "
            "The report is retained but cannot qualify as fresh held-out evidence."
        ),
    )
    parser.add_argument(
        "--cache-policy",
        choices=("cold", "warm", "mixed", "uncontrolled"),
        default="uncontrolled",
    )
    return parser


def _string_list(value: Any, *, row: int, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise EvaluationError(f"Row {row} requires {field!r} as an array of strings")
    return list(dict.fromkeys(item.strip() for item in value if item.strip()))


def _prepare_fixture(
    records: list[dict[str, Any]], *, query_field: str, limit: int | None
) -> list[dict[str, Any]]:
    if limit is not None:
        if limit < 1:
            raise EvaluationError("--limit must be positive")
        records = records[:limit]
    prepared: list[dict[str, Any]] = []
    for row_number, record in enumerate(records, start=1):
        query, query_source_field = select_query_and_field(
            record, preferred=query_field, row=row_number
        )
        relevant = _string_list(
            record.get("relevant_canonical_ids"),
            row=row_number,
            field="relevant_canonical_ids",
        )
        if not relevant:
            raise EvaluationError(
                f"Row {row_number} has no relevance labels; retrieval evaluation requires "
                "held-out is_selected labels"
            )
        prepared.append(
            {
                **record,
                "_evaluation_query": query,
                "_query_source_field": query_source_field,
            }
        )
    enforce_distinct(prepared, id_field="query_id", content_field="_evaluation_query")
    return prepared


async def run(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_records = load_records(args.fixture)
    provenance = held_out_provenance(
        args.fixture,
        source_records,
        corpus_manifest=getattr(args, "corpus_manifest", None),
        partition_manifest=getattr(args, "partition_manifest", None),
        query_field=args.query_field,
    )
    fixture_rows = _prepare_fixture(source_records, query_field=args.query_field, limit=args.limit)
    size_qualification = require_minimum_cases(
        len(fixture_rows),
        max(DEFAULT_MINIMUM_QUERIES, args.minimum_queries),
        suite="Retrieval evaluation",
        allow_small_smoke=args.allow_small_smoke,
    )
    evaluation_records: list[RetrievalEvaluationRecord] = []
    raw_rows: list[dict[str, Any]] = []

    async with initialized_services() as services:
        orchestrator = services.orchestrator
        assert orchestrator is not None
        index_manifest_path, index_manifest = service_index_manifest(services)
        index_provenance = corpus_index_provenance(
            provenance,
            index_manifest_path=index_manifest_path,
            index_manifest=index_manifest,
        )
        threshold_provenance = final_threshold_provenance(
            services,
            final_fixture_sha256=provenance["fixture_sha256"],
            final_query_ids=[str(row["query_id"]) for row in fixture_rows],
            final_queries=[str(row["_evaluation_query"]) for row in fixture_rows],
            index_manifest_path=index_manifest_path,
            index_manifest=index_manifest,
        )
        if orchestrator.retriever.final_limit < 10:
            raise EvaluationError(
                "Retriever final_limit must be at least 10 to measure Recall@10, "
                "MRR@10, and nDCG@10 without truncation"
            )
        for row_number, fixture in enumerate(fixture_rows, start=1):
            query_id = require_text(fixture, "query_id", row=row_number)
            query = require_text(fixture, "_evaluation_query", row=row_number)
            relevant = frozenset(
                _string_list(
                    fixture.get("relevant_canonical_ids"),
                    row=row_number,
                    field="relevant_canonical_ids",
                )
            )
            started_ns = time.perf_counter_ns()
            error: dict[str, str] | None = None
            plan: Any | None = None
            retrieved_ids: tuple[str, ...] = ()
            agreement: float | None = None
            sparse_failed: bool | None = None
            score_evidence = raw_dense_score_evidence(())
            try:
                language_hint = (
                    "en"
                    if fixture["_query_source_field"] == "english_query"
                    else fixture.get("language")
                )
                plan = orchestrator.router.route(query, language_hint=language_hint)
            except Exception as exc:
                error = {
                    "kind": "configuration",
                    "stage": "routing",
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            if error is None:
                try:
                    fallback_ms = max(1, args.deadline_ms - 1)
                    result = await orchestrator.retriever.retrieve(
                        query,
                        plan,
                        Deadline.after_ms(args.deadline_ms, fallback_ms),
                    )
                    retrieved_ids = tuple(hit.canonical_doc_id for hit in result.fused_hits)
                    agreement = result.agreement
                    sparse_failed = result.sparse_failed
                    score_evidence = raw_dense_score_evidence(result.fused_hits)
                    if sparse_failed:
                        error = {
                            "kind": "request",
                            "stage": "sparse_retrieval",
                            "type": "SparseBranchFailure",
                            "message": "Sparse retrieval failed; dense-only fallback retained",
                        }
                except Exception as exc:
                    error = {
                        "kind": "request",
                        "stage": "retrieval",
                        "type": type(exc).__name__,
                        "message": str(exc),
                    }
            duration_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
            language = (
                "en"
                if fixture["_query_source_field"] == "english_query"
                else str(
                    fixture.get("language")
                    or (plan.language.value if plan is not None else "unknown")
                )
            )
            category = str(
                fixture.get("category") or (plan.category if plan is not None else "routing_failed")
            )
            metric_record = RetrievalEvaluationRecord(
                query_id=query_id,
                relevant_ids=relevant,
                retrieved_ids=retrieved_ids,
                language=language,
                category=category,
            )
            evaluation_records.append(metric_record)
            per_query = retrieval_metrics([metric_record])
            raw_rows.append(
                {
                    "query_id": query_id,
                    "query": query,
                    "query_source_field": fixture["_query_source_field"],
                    "language": language,
                    "category": category,
                    "relevant_ids": sorted(relevant),
                    "retrieved_ids": list(retrieved_ids),
                    "duration_ms": duration_ms,
                    "evidence_agreement": agreement,
                    "sparse_failed": sparse_failed,
                    "success": error is None,
                    "error": error,
                    **score_evidence,
                    "recall_at_1": per_query["recall_at_1"],
                    "recall_at_5": per_query["recall_at_5"],
                    "recall_at_10": per_query["recall_at_10"],
                    "reciprocal_rank_at_10": per_query["mrr_at_10"],
                    "ndcg_at_10": per_query["ndcg_at_10"],
                }
            )

        metrics = grouped_retrieval_metrics(evaluation_records)
        request_failures = sum(
            row["error"] is not None and row["error"].get("kind") == "request" for row in raw_rows
        )
        configuration_failures = sum(
            row["error"] is not None and row["error"].get("kind") == "configuration"
            for row in raw_rows
        )
        failures = request_failures + configuration_failures
        successful_requests = sum(bool(row["success"]) for row in raw_rows)
        hit_count = sum(
            bool(set(row["relevant_ids"]) & set(row["retrieved_ids"])) for row in raw_rows
        )
        qualification = evaluation_qualification(
            size_qualification=size_qualification,
            provenance=provenance,
            index_provenance=index_provenance,
            thresholds=threshold_provenance,
            expected_requests=len(fixture_rows),
            recorded_requests=len(raw_rows),
            successful_requests=successful_requests,
            request_failures=request_failures,
            configuration_failures=configuration_failures,
            additional_checks={
                "fresh_untouched_final_evaluation": (
                    not args.post_hoc_regression_confirmation
                )
            },
        )
        metadata = base_metadata(
            command="run_retrieval_eval",
            fixture=args.fixture,
            cache_policy=args.cache_policy,
            concurrency=1,
            qualification=qualification["status"],
        )
        metadata["corpus"] = corpus_metadata(services)
        metadata["held_out_provenance"] = provenance
        metadata["corpus_index_provenance"] = index_provenance
        metadata["frozen_thresholds"] = threshold_provenance
        metadata["qualifying"] = qualification["qualifying"]
        metadata["qualification_checks"] = qualification
        metadata["query_field"] = args.query_field
        metadata["deadline_ms"] = args.deadline_ms
        metadata["evaluation_interpretation"] = (
            "post_hoc_regression_confirmation"
            if args.post_hoc_regression_confirmation
            else "fresh_held_out_evaluation"
        )
        metadata["score_contract"] = {
            key: raw_dense_score_evidence(())[key]
            for key in ("score_kind", "score_contract_version")
        }

    summary: dict[str, Any] = {
        "metadata": metadata,
        "metrics": metrics,
        "latency": latency_metrics(
            [float(row["duration_ms"]) for row in raw_rows],
            total_requests=len(raw_rows),
            completed_answers=successful_requests,
        ),
        "retrieval_hit_coverage": hit_count / len(raw_rows),
        "retrieval_completion_coverage": qualification["retrieval_completion_coverage"],
        "failure_count": failures,
        "request_failure_count": request_failures,
        "configuration_failure_count": configuration_failures,
    }
    return summary, raw_rows


def _markdown(summary: dict[str, Any]) -> str:
    overall = summary["metrics"]["overall"]
    latency = summary["latency"]
    metadata = summary["metadata"]
    lines = [
        "# Retrieval evaluation",
        "",
        f"Qualification: **{metadata['qualification']}**",
        "",
        markdown_table(
            (
                "Queries",
                "Recall@1",
                "Recall@5",
                "Recall@10",
                "MRR@10",
                "nDCG@10",
                "Hit coverage",
                "Retrieval completion",
                "Request failures",
                "Configuration failures",
            ),
            [
                (
                    overall["query_count"],
                    overall["recall_at_1"],
                    overall["recall_at_5"],
                    overall["recall_at_10"],
                    overall["mrr_at_10"],
                    overall["ndcg_at_10"],
                    summary["retrieval_hit_coverage"],
                    summary["retrieval_completion_coverage"],
                    summary["request_failure_count"],
                    summary["configuration_failure_count"],
                )
            ],
        ),
        "",
        "## End-to-end retrieval latency",
        "",
        markdown_table(
            ("Samples", "Mean (ms)", "P50 (ms)", "P70 (ms)", "P95 (ms)", "P100 (ms)"),
            [
                (
                    latency["sample_count"],
                    latency.get("mean_ms", "n/a"),
                    latency.get("p50_ms", "n/a"),
                    latency.get("p70_ms", "n/a"),
                    latency.get("p95_ms", "n/a"),
                    latency.get("p100_ms", "n/a"),
                )
            ],
        ),
        "",
        "## Per-language metrics",
        "",
        markdown_table(
            ("Language", "Queries", "Recall@10", "MRR@10", "nDCG@10"),
            (
                (
                    name,
                    values["query_count"],
                    values["recall_at_10"],
                    values["mrr_at_10"],
                    values["ndcg_at_10"],
                )
                for name, values in summary["metrics"]["by_language"].items()
            ),
        ),
        "",
        "## Per-category metrics",
        "",
        markdown_table(
            ("Category", "Queries", "Recall@10", "MRR@10", "nDCG@10"),
            (
                (
                    name,
                    values["query_count"],
                    values["recall_at_10"],
                    values["mrr_at_10"],
                    values["ndcg_at_10"],
                )
                for name, values in summary["metrics"]["by_category"].items()
            ),
        ),
        "",
        (
            "Raw row-level results are in the sibling JSONL and CSV artifacts. "
            "Hardware, package, corpus, cache, and concurrency metadata are in the "
            "JSON summary."
        ),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.minimum_queries < DEFAULT_MINIMUM_QUERIES:
        parser.error(
            f"--minimum-queries cannot be below {DEFAULT_MINIMUM_QUERIES}; "
            "use --allow-small-smoke for a non-qualifying smaller run"
        )
    if args.deadline_ms < 20:
        parser.error("--deadline-ms must be at least 20")
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
