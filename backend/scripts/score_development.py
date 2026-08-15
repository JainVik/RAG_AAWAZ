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
from app.evaluation.thresholds import (  # noqa: E402
    RetrievalArtifactBinding,
    retrieval_runtime_contract_sha256,
)
from app.retrieval.router import TIDE_ROUTER_CONTRACT_VERSION  # noqa: E402
from scripts._common import (  # noqa: E402
    FIXTURES_ROOT,
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
    raw_dense_score_evidence,
    require_text,
    select_query_and_field,
    service_index_manifest,
    write_report_bundle,
)

DEFAULT_UNANSWERABLE_FIXTURE = FIXTURES_ROOT / "development-unanswerable.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure versioned raw-dense and branch-agreement signals on an explicit "
            "development fixture for calibrate_thresholds.py."
        )
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument(
        "--unanswerable-fixture",
        type=Path,
        default=DEFAULT_UNANSWERABLE_FIXTURE,
        help=(
            "Explicit development-only negative cases appended to --fixture. "
            "Defaults to the bundled static-corpus unanswerable fixture."
        ),
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=REPORTS_ROOT / "development-retrieval-scores",
    )
    parser.add_argument(
        "--query-field",
        choices=("auto", "query", "english_query", "translated_query"),
        default="auto",
    )
    parser.add_argument("--deadline-ms", type=int, default=5_000)
    parser.add_argument(
        "--cache-policy",
        choices=("disabled", "cold", "warm", "mixed", "uncontrolled"),
        default="disabled",
    )
    return parser


def _answerable(value: Any, *, row: int) -> bool:
    if isinstance(value, bool):
        return value
    raise EvaluationError(
        f"Row {row} must declare is_answerable as a JSON boolean; labels may not be inferred"
    )


def _prepare(
    records: list[dict[str, Any]], *, query_field: str
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for row_number, record in enumerate(records, start=1):
        split = require_text(record, "split", row=row_number)
        if split != "development":
            raise EvaluationError(
                f"Row {row_number} belongs to split {split!r}; scoring accepts only an "
                "explicit development split"
            )
        query, source = select_query_and_field(
            record, row=row_number, preferred=query_field
        )
        prepared.append(
            {
                **record,
                "query_id": require_text(record, "query_id", row=row_number),
                "query": query,
                "query_source_field": source,
                "is_answerable": _answerable(
                    record.get("is_answerable"), row=row_number
                ),
            }
        )
    enforce_distinct(prepared, id_field="query_id", content_field="query")
    if {row["is_answerable"] for row in prepared} != {False, True}:
        raise EvaluationError(
            "Development scoring requires both answerable and intentionally unanswerable cases"
        )
    return prepared


def _load_scoring_records(
    fixture: Path, unanswerable_fixture: Path
) -> list[dict[str, Any]]:
    answerable_records = load_records(fixture)
    unanswerable_records = load_records(unanswerable_fixture)
    for row_number, record in enumerate(unanswerable_records, start=1):
        if record.get("is_answerable") is not False:
            raise EvaluationError(
                f"Unanswerable fixture row {row_number} must declare "
                "is_answerable=false"
            )
        if record.get("split") != "development":
            raise EvaluationError(
                f"Unanswerable fixture row {row_number} must belong to the "
                "development split"
            )
    return [*answerable_records, *unanswerable_records]


def _binding(
    path: Path, manifest: dict[str, Any], settings: Any
) -> RetrievalArtifactBinding:
    checksums = manifest.get("checksums")
    checksums = checksums if isinstance(checksums, dict) else {}
    return RetrievalArtifactBinding(
        index_manifest_sha256=file_sha256(path),
        corpus_manifest_sha256=manifest.get("corpus_manifest_sha256"),
        corpus_artifact_sha256=checksums.get("corpus"),
        chunk_build_id=manifest.get("chunk_build_id"),
        collection=manifest.get("collection"),
        dense_model=manifest.get("dense_model"),
        model_revision=manifest.get("model_revision"),
        retrieval_contract_version=TIDE_ROUTER_CONTRACT_VERSION,
        retrieval_contract_sha256=retrieval_runtime_contract_sha256(settings),
    )


async def run(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = _prepare(
        _load_scoring_records(args.fixture, args.unanswerable_fixture),
        query_field=args.query_field,
    )
    raw_rows: list[dict[str, Any]] = []
    async with initialized_services() as services:
        orchestrator = services.orchestrator
        assert orchestrator is not None
        index_manifest_path, index_manifest = service_index_manifest(services)
        artifact_binding = _binding(
            index_manifest_path, index_manifest, services.settings
        )
        binding_payload = artifact_binding.model_dump(mode="json")
        for row in records:
            query = str(row["query"])
            language_hint = (
                "en"
                if row["query_source_field"] == "english_query"
                else row.get("language")
            )
            plan = orchestrator.router.route(query, language_hint=language_hint)
            started_ns = time.perf_counter_ns()
            result = await orchestrator.retriever.retrieve(
                query,
                plan,
                Deadline.after_ms(args.deadline_ms, max(1, args.deadline_ms - 1)),
            )
            duration_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
            if result.sparse_failed:
                raise EvaluationError(
                    f"Sparse retrieval failed while scoring development query {row['query_id']!r}"
                )
            scores = raw_dense_score_evidence(result.fused_hits)
            if scores["top_raw_dense_similarity"] is None:
                raise EvaluationError(
                    f"No raw dense score was returned for development query {row['query_id']!r}"
                )
            raw_rows.append(
                {
                    "query_id": row["query_id"],
                    "query": query,
                    "query_source_field": row["query_source_field"],
                    "split": "development",
                    "is_answerable": row["is_answerable"],
                    "language": row.get("language"),
                    "category": row.get("category"),
                    "evidence_agreement": result.agreement,
                    "dense_hit_count": len(result.dense_hits),
                    "sparse_hit_count": len(result.sparse_hits),
                    "fused_hit_count": len(result.fused_hits),
                    "duration_ms": duration_ms,
                    "retrieval_artifacts": binding_payload,
                    **scores,
                }
            )
        metadata = base_metadata(
            command="score_development",
            fixture=args.fixture,
            cache_policy=args.cache_policy,
            concurrency=1,
            qualification="development_score_export",
        )
        metadata.update(
            {
                "qualifying": True,
                "query_field": args.query_field,
                "deadline_ms": args.deadline_ms,
                "unanswerable_fixture": {
                    "path": str(Path(args.unanswerable_fixture).resolve()),
                    "sha256": file_sha256(args.unanswerable_fixture),
                },
                "case_count": len(raw_rows),
                "answerable_count": sum(bool(row["is_answerable"]) for row in raw_rows),
                "unanswerable_count": sum(
                    not bool(row["is_answerable"]) for row in raw_rows
                ),
                "retrieval_artifacts": binding_payload,
                "corpus": corpus_metadata(services),
                "output_contract": (
                    "Pass the sibling JSONL artifact to calibrate_thresholds.py --fixture"
                ),
            }
        )
    return {"metadata": metadata}, raw_rows


def _markdown(summary: dict[str, Any]) -> str:
    metadata = summary["metadata"]
    return "\n".join(
        [
            "# Development retrieval score export",
            "",
            (
                "These are measured raw-dense similarity, margin, and dense/sparse "
                "agreement signals from the active index. They are calibration input, "
                "not final-evaluation results."
            ),
            "",
            markdown_table(
                ("Cases", "Answerable", "Unanswerable", "Deadline (ms)"),
                [
                    (
                        metadata["case_count"],
                        metadata["answerable_count"],
                        metadata["unanswerable_count"],
                        metadata["deadline_ms"],
                    )
                ],
            ),
            "",
            "Use the sibling JSONL as `calibrate_thresholds.py --fixture`.",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.deadline_ms < 20:
        parser.error("--deadline-ms must be at least 20")
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
