from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.evaluation.thresholds import (  # noqa: E402
    query_content_sha256,
    query_ids_sha256,
)
from scripts._common import (  # noqa: E402
    DEFAULT_CORPUS_EVALUATION_FIXTURE,
    EvaluationError,
    file_sha256,
    held_out_provenance,
    load_records,
    require_text,
    select_query_and_field,
    write_json,
    write_jsonl,
)

PARTITION_SCHEMA_VERSION = 1
PARTITION_ALGORITHM = "sha256-seeded-normalized-query-content-v1"
DEVELOPMENT_FILENAME = "development-fixtures.jsonl"
FINAL_FILENAME = "final-fixtures.jsonl"
MANIFEST_FILENAME = "partition-manifest.json"


@dataclass(frozen=True, slots=True)
class PartitionArtifacts:
    development: Path
    final: Path
    manifest: Path


def _backend_path(path: Path) -> Path:
    return path if path.is_absolute() else BACKEND_ROOT / path


def _default_output_dir() -> Path:
    return _backend_path(get_settings().rag_data_dir) / "evaluation" / "partition"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically split one corpus validation fixture into disjoint "
            "development and final fixtures."
        )
    )
    parser.add_argument(
        "--fixture", type=Path, default=DEFAULT_CORPUS_EVALUATION_FIXTURE
    )
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        help="Source CorpusWriter manifest; defaults to a sibling corpus-manifest.json.",
    )
    parser.add_argument("--output-dir", type=Path, default=_default_output_dir())
    parser.add_argument(
        "--query-field",
        choices=("auto", "query", "english_query", "translated_query"),
        default="auto",
        help="Query representation whose normalized content must remain disjoint.",
    )
    count_group = parser.add_mutually_exclusive_group()
    count_group.add_argument(
        "--development-count",
        type=int,
        help="Exact development row count; defaults to floor(total rows / 2).",
    )
    count_group.add_argument(
        "--final-count",
        type=int,
        help="Exact final row count; the remaining rows become development data.",
    )
    parser.add_argument(
        "--require-final-relevance-labels",
        action="store_true",
        help=(
            "Restrict the final partition to normalized-content groups whose rows all "
            "contain non-empty relevant_canonical_ids. Requires --final-count."
        ),
    )
    parser.add_argument("--seed", type=int, default=get_settings().rag_random_seed)
    return parser


def _rank(seed: int, query_id: str) -> str:
    material = f"{PARTITION_ALGORITHM}\0{seed}\0{query_id}".encode()
    return hashlib.sha256(material).hexdigest()


def _artifact_metadata(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    content_hashes: list[str],
) -> dict[str, Any]:
    query_ids = sorted(str(row["query_id"]) for row in rows)
    return {
        "filename": path.name,
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
        "records": len(rows),
        "query_ids": query_ids,
        "query_ids_sha256": query_ids_sha256(query_ids),
        "content_hashes": content_hashes,
        "content_hash_count": len(content_hashes),
        "content_hashes_sha256": query_ids_sha256(content_hashes),
        "split": str(rows[0]["split"]),
    }


def _development_group_hashes(
    groups: dict[str, tuple[str, ...]],
    *,
    seed: int,
    requested_count: int,
    exact: bool,
) -> frozenset[str]:
    ranked_hashes = sorted(
        groups,
        key=lambda content_hash: (_rank(seed, content_hash), content_hash),
    )
    reachable: dict[int, tuple[str, ...]] = {0: ()}
    for content_hash in ranked_hashes:
        group_size = len(groups[content_hash])
        for count, selected in sorted(reachable.items(), reverse=True):
            candidate = count + group_size
            if candidate >= sum(len(query_ids) for query_ids in groups.values()):
                continue
            reachable.setdefault(candidate, (*selected, content_hash))
    if exact:
        exact_selection = reachable.get(requested_count)
        if exact_selection is None:
            raise EvaluationError(
                "--development-count cannot be satisfied without placing identical "
                "normalized query content in both partitions"
            )
        return frozenset(exact_selection)
    valid_counts = [count for count in reachable if count > 0]
    if not valid_counts:
        raise EvaluationError(
            "Validation fixture has only one normalized query-content group and "
            "cannot be split without leakage"
        )
    selected_count = min(
        valid_counts,
        key=lambda count: (abs(count - requested_count), count > requested_count, count),
    )
    return frozenset(reachable[selected_count])


def _has_relevance_labels(row: dict[str, Any]) -> bool:
    value = row.get("relevant_canonical_ids")
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def run(args: argparse.Namespace) -> tuple[dict[str, Any], PartitionArtifacts]:
    fixture = _backend_path(Path(args.fixture))
    corpus_manifest = (
        _backend_path(Path(args.corpus_manifest))
        if args.corpus_manifest is not None
        else fixture.with_name("corpus-manifest.json")
    )
    output_dir = _backend_path(Path(args.output_dir))
    if output_dir.resolve() == fixture.parent.resolve():
        raise EvaluationError(
            "--output-dir must differ from the source corpus directory so derived "
            "partition evidence cannot shadow the source manifest"
        )

    source_rows = load_records(fixture)
    source_provenance = held_out_provenance(
        fixture,
        source_rows,
        corpus_manifest=corpus_manifest,
    )
    if source_provenance.get("qualifying") is not True:
        failed = source_provenance.get("failed_checks") or [
            source_provenance.get("status", "invalid_provenance")
        ]
        raise EvaluationError(
            "Source validation fixture is not bound to its corpus manifest: "
            + ", ".join(str(item) for item in failed)
        )
    source_splits = {
        str(row.get("split") or "").strip().casefold() for row in source_rows
    }
    if source_splits != {"validation"}:
        raise EvaluationError(
            "Fixture partitioning requires source rows from the validation split"
        )
    if len(source_rows) < 2:
        raise EvaluationError(
            "Fixture partitioning requires at least two validation queries"
        )

    rows_by_id: dict[str, dict[str, Any]] = {}
    grouped_ids: dict[str, list[str]] = {}
    for row_number, row in enumerate(source_rows, start=1):
        query_id = require_text(row, "query_id", row=row_number)
        if query_id in rows_by_id:
            raise EvaluationError(f"Duplicate query_id {query_id!r} in source fixture")
        query, _source_field = select_query_and_field(
            row,
            row=row_number,
            preferred=str(args.query_field),
        )
        content_hash = query_content_sha256(query)
        rows_by_id[query_id] = row
        grouped_ids.setdefault(content_hash, []).append(query_id)

    groups = {
        content_hash: tuple(sorted(query_ids))
        for content_hash, query_ids in grouped_ids.items()
    }

    final_count_arg = getattr(args, "final_count", None)
    require_final_relevance = bool(
        getattr(args, "require_final_relevance_labels", False)
    )
    if require_final_relevance and final_count_arg is None:
        raise EvaluationError(
            "--require-final-relevance-labels requires an explicit --final-count"
        )

    if final_count_arg is not None:
        requested_final_count = int(final_count_arg)
        if not 1 <= requested_final_count < len(rows_by_id):
            raise EvaluationError(
                "--final-count must leave at least one development and one final row"
            )
        eligible_final_groups = {
            content_hash: query_ids
            for content_hash, query_ids in groups.items()
            if not require_final_relevance
            or all(_has_relevance_labels(rows_by_id[query_id]) for query_id in query_ids)
        }
        final_group_hashes = _development_group_hashes(
            eligible_final_groups,
            seed=int(args.seed),
            requested_count=requested_final_count,
            exact=True,
        )
        final_ids = frozenset(
            query_id
            for content_hash in final_group_hashes
            for query_id in groups[content_hash]
        )
        development_ids = frozenset(set(rows_by_id).difference(final_ids))
        development_group_hashes = frozenset(
            set(groups).difference(final_group_hashes)
        )
        requested_development_count = len(rows_by_id) - requested_final_count
    else:
        requested_development_count = (
            len(rows_by_id) // 2
            if args.development_count is None
            else int(args.development_count)
        )
        if not 1 <= requested_development_count < len(rows_by_id):
            raise EvaluationError(
                "--development-count must leave at least one development and one final row"
            )
        development_group_hashes = _development_group_hashes(
            groups,
            seed=int(args.seed),
            requested_count=requested_development_count,
            exact=args.development_count is not None,
        )
        development_ids = frozenset(
            query_id
            for content_hash in development_group_hashes
            for query_id in groups[content_hash]
        )
        final_ids = frozenset(set(rows_by_id).difference(development_ids))
        final_group_hashes = frozenset(
            set(groups).difference(development_group_hashes)
        )
        requested_final_count = len(final_ids)

    development_count = len(development_ids)

    development_rows = [
        {
            **rows_by_id[query_id],
            "split": "development",
            "is_answerable": True,
        }
        for query_id in sorted(development_ids)
    ]
    final_rows = [
        {**rows_by_id[query_id], "split": "final", "is_answerable": True}
        for query_id in sorted(final_ids)
    ]
    artifacts = PartitionArtifacts(
        development=output_dir / DEVELOPMENT_FILENAME,
        final=output_dir / FINAL_FILENAME,
        manifest=output_dir / MANIFEST_FILENAME,
    )
    write_jsonl(artifacts.development, development_rows)
    write_jsonl(artifacts.final, final_rows)

    source_query_ids = sorted(rows_by_id)
    manifest: dict[str, Any] = {
        "schema_version": PARTITION_SCHEMA_VERSION,
        "artifact_type": "evaluation_fixture_partition",
        "algorithm": {
            "name": PARTITION_ALGORITHM,
            "seed": int(args.seed),
            "query_field": str(args.query_field),
            "requested_development_count": requested_development_count,
            "requested_final_count": requested_final_count,
            "development_count": development_count,
            "final_count": len(final_ids),
            "require_final_relevance_labels": require_final_relevance,
            "content_group_count": len(groups),
        },
        "source": {
            "fixture": {
                "filename": fixture.name,
                "sha256": file_sha256(fixture),
                "bytes": fixture.stat().st_size,
                "records": len(source_rows),
                "query_ids": source_query_ids,
                "query_ids_sha256": query_ids_sha256(source_query_ids),
                "content_hashes": sorted(groups),
                "content_hash_count": len(groups),
                "content_hashes_sha256": query_ids_sha256(sorted(groups)),
                "split": "validation",
            },
            "corpus_manifest": {
                "filename": corpus_manifest.name,
                "sha256": file_sha256(corpus_manifest),
            },
            "dataset": source_provenance.get("dataset"),
        },
        "partitions": {
            "development": _artifact_metadata(
                artifacts.development,
                development_rows,
                content_hashes=sorted(development_group_hashes),
            ),
            "final": _artifact_metadata(
                artifacts.final,
                final_rows,
                content_hashes=sorted(final_group_hashes),
            ),
        },
        "checks": {
            "query_ids_disjoint": not development_ids.intersection(final_ids),
            "union_matches_source": development_ids.union(final_ids)
            == set(source_query_ids),
            "normalized_query_content_disjoint": not development_group_hashes.intersection(
                final_group_hashes
            ),
            "content_groups_cover_source": development_group_hashes.union(
                final_group_hashes
            )
            == set(groups),
            "source_provenance_verified": True,
            "final_relevance_labels_complete": not require_final_relevance
            or all(_has_relevance_labels(row) for row in final_rows),
        },
    }
    if not all(manifest["checks"].values()):
        raise EvaluationError("Internal partition integrity check failed")
    write_json(artifacts.manifest, manifest)
    return manifest, artifacts


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest, artifacts = run(args)
    except (EvaluationError, OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Development fixture: {artifacts.development}")
    print(f"Final fixture: {artifacts.final}")
    print(f"Partition manifest: {artifacts.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
