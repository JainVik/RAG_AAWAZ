from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ingestion.dataset_audit import (  # noqa: E402
    DEFAULT_SHORT_PASSAGE_CHARS,
    DEFAULT_STREAM_BATCH_SIZE,
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
