from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ingestion.dataset_audit import (  # noqa: E402
    DEFAULT_CANDIDATE_CORPUS_SIZES,
    DEFAULT_DENSE_VECTOR_SIZE,
    DEFAULT_EMBEDDING_VECTORS_PER_SECOND,
    DEFAULT_SHORT_PASSAGE_CHARS,
    DEFAULT_STREAM_BATCH_SIZE,
    DEFAULT_UPSERT_POINTS_PER_SECOND,
    LANGUAGE_FILES,
    DatasetFileUnavailable,
    audit_records,
    combine_audit_reports,
    stream_dataset,
    write_audit_reports,
)


def build_parser() -> argparse.ArgumentParser:
    reports_dir = BACKEND_ROOT / "evaluation" / "reports"
    parser = argparse.ArgumentParser(
        description="Audit bounded MSMARCO-XI language streams without downloading the corpus."
    )
    parser.add_argument("--languages", nargs="+", choices=sorted(LANGUAGE_FILES), default=["hi"])
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=("train", "validation"),
        default=["train", "validation"],
    )
    parser.add_argument("--max-rows", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_STREAM_BATCH_SIZE)
    parser.add_argument(
        "--short-passage-chars", type=int, default=DEFAULT_SHORT_PASSAGE_CHARS
    )
    parser.add_argument("--max-malformed-examples", type=int, default=20)
    parser.add_argument(
        "--candidate-corpus-sizes",
        nargs="+",
        type=int,
        default=list(DEFAULT_CANDIDATE_CORPUS_SIZES),
        help="Unique-passage targets used for explicitly heuristic scaling estimates.",
    )
    parser.add_argument("--dense-vector-size", type=int, default=DEFAULT_DENSE_VECTOR_SIZE)
    parser.add_argument(
        "--assumed-embedding-vectors-per-second",
        type=float,
        default=DEFAULT_EMBEDDING_VECTORS_PER_SECOND,
    )
    parser.add_argument(
        "--assumed-upsert-points-per-second",
        type=float,
        default=DEFAULT_UPSERT_POINTS_PER_SECOND,
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=reports_dir / "dataset-audit.json",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=reports_dir / "dataset-audit.md",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_rows < 1:
        parser.error("--max-rows must be positive")
    if not 1 <= args.batch_size <= 4096:
        parser.error("--batch-size must be between 1 and 4096")
    if args.short_passage_chars < 0:
        parser.error("--short-passage-chars must be non-negative")
    if args.max_malformed_examples < 0:
        parser.error("--max-malformed-examples must be non-negative")
    if any(size < 1 for size in args.candidate_corpus_sizes):
        parser.error("--candidate-corpus-sizes values must be positive")
    if args.dense_vector_size < 1:
        parser.error("--dense-vector-size must be positive")
    if args.assumed_embedding_vectors_per_second <= 0:
        parser.error("--assumed-embedding-vectors-per-second must be positive")
    if args.assumed_upsert_points_per_second <= 0:
        parser.error("--assumed-upsert-points-per-second must be positive")

    reports = []
    for language in args.languages:
        for split in args.splits:
            try:
                dataset = stream_dataset(
                    language,
                    split,
                    batch_size=args.batch_size,
                )
            except DatasetFileUnavailable as exc:
                parser.error(str(exc))
            reports.append(
                audit_records(
                    dataset,
                    language=language,
                    split=split,
                    max_rows=args.max_rows,
                    observed_schema=getattr(dataset, "features", None),
                    batch_size=args.batch_size,
                    short_passage_chars=args.short_passage_chars,
                    max_malformed_examples=args.max_malformed_examples,
                    candidate_corpus_sizes=args.candidate_corpus_sizes,
                    dense_vector_size=args.dense_vector_size,
                    embedding_vectors_per_second=(
                        args.assumed_embedding_vectors_per_second
                    ),
                    upsert_points_per_second=args.assumed_upsert_points_per_second,
                )
            )

    combined = combine_audit_reports(reports)
    json_path, markdown_path = write_audit_reports(
        combined,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    rows = sum(report["sampling"]["rows_sampled"] for report in reports)
    print(f"Audited {rows} rows across {len(reports)} language/split stream(s).")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
