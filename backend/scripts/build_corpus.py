from __future__ import annotations

import argparse
import json
import sys
from itertools import islice
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.ingestion.corpus_writer import (  # noqa: E402
    CorpusBuildConfig,
    build_corpus_artifacts,
)
from app.ingestion.dataset_audit import (  # noqa: E402
    DEFAULT_STREAM_BATCH_SIZE,
    LANGUAGE_FILES,
    stream_dataset,
)

SOURCE_COLUMNS = (
    "source_lang",
    "target_lang",
    "meta",
    "query_id",
    "passages",
    # The following fields are read only to produce the physically separate
    # evaluation fixture artifact. CorpusWriter never copies them to corpus.jsonl.
    "Eng_Query",
    "Eng_Answer",
    "query",
    "Answer",
)


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    default_language = settings.rag_language if settings.rag_language in LANGUAGE_FILES else "hi"
    parser = argparse.ArgumentParser(
        description="Build a deterministic, leak-free MSMARCO-XI passage corpus."
    )
    parser.add_argument(
        "--language", choices=sorted(LANGUAGE_FILES), default=default_language
    )
    parser.add_argument("--split", choices=("train", "validation"), default="train")
    parser.add_argument(
        "--target-unique-passages",
        type=int,
        default=settings.rag_development_passages,
    )
    parser.add_argument("--seed", type=int, default=settings.rag_random_seed)
    parser.add_argument("--shuffle-buffer-size", type=int, default=10_000)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_STREAM_BATCH_SIZE)
    parser.add_argument("--checkpoint-every", type=int, default=100)
    parser.add_argument("--max-source-rows", type=int)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=settings.rag_data_dir / "corpus",
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--skip-malformed",
        action="store_true",
        help="Skip malformed passage arrays instead of failing the build.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.target_unique_passages < 1:
        parser.error("--target-unique-passages must be positive")
    if args.shuffle_buffer_size < 1:
        parser.error("--shuffle-buffer-size must be positive")
    if not 1 <= args.batch_size <= 4096:
        parser.error("--batch-size must be between 1 and 4096")
    if args.checkpoint_every < 1:
        parser.error("--checkpoint-every must be positive")
    if args.max_source_rows is not None and args.max_source_rows < 1:
        parser.error("--max-source-rows must be positive")

    records: Any = stream_dataset(
        args.language,
        args.split,
        batch_size=args.batch_size,
        columns=SOURCE_COLUMNS,
    )
    if args.max_source_rows is not None:
        records = islice(records, args.max_source_rows)

    result = build_corpus_artifacts(
        records,
        CorpusBuildConfig(
            output_dir=args.output_dir,
            target_unique_passages=args.target_unique_passages,
            language=args.language,
            split=args.split,
            seed=args.seed,
            shuffle_buffer_size=args.shuffle_buffer_size,
            checkpoint_every=args.checkpoint_every,
            strict=not args.skip_malformed,
            resume=not args.no_resume,
        ),
    )
    print(json.dumps(result.manifest, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Corpus: {result.corpus_path}")
    print(f"Evaluation fixtures: {result.evaluation_path}")
    print(f"Manifest: {result.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
