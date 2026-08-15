from __future__ import annotations

import csv
import ctypes
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import tempfile
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPORTS_ROOT = BACKEND_ROOT / "evaluation" / "reports"
FIXTURES_ROOT = BACKEND_ROOT / "evaluation" / "fixtures"
DEFAULT_CORPUS_EVALUATION_FIXTURE = BACKEND_ROOT / "data" / "corpus" / "evaluation-fixtures.jsonl"
HELD_OUT_SPLITS = frozenset({"validation", "final"})


class EvaluationError(RuntimeError):
    """An actionable evaluation setup or data error."""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise EvaluationError(f"Could not read artifact {path}: {exc}") from exc
    return digest.hexdigest()


def _require_object(value: Any, *, source: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EvaluationError(f"{source} must contain a JSON object")
    return {str(key): item for key, item in value.items()}


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EvaluationError(f"Required JSON artifact does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"Could not parse JSON artifact {path}: {exc}") from exc
    return _require_object(value, source=str(path))


def load_records(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL, JSON-array, or CSV fixture without silently dropping rows."""

    if not path.is_file():
        raise EvaluationError(f"Required evaluation fixture does not exist: {path}")
    records: list[dict[str, Any]] = []
    try:
        if path.suffix.casefold() == ".jsonl":
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise EvaluationError(
                            f"Invalid JSON on {path}:{line_number}: {exc.msg}"
                        ) from exc
                    records.append(_require_object(value, source=f"{path}:{line_number}"))
        elif path.suffix.casefold() == ".csv":
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    raise EvaluationError(f"CSV fixture has no header: {path}")
                records.extend(dict(row) for row in reader)
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, list):
                raise EvaluationError(f"JSON fixture must be an array: {path}")
            records.extend(
                _require_object(row, source=f"{path}[{index}]") for index, row in enumerate(value)
            )
    except EvaluationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"Could not read fixture {path}: {exc}") from exc
    if not records:
        raise EvaluationError(f"Evaluation fixture contains no records: {path}")
    return records


def require_text(record: Mapping[str, Any], field: str, *, row: int) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(f"Row {row} requires a non-empty {field!r}")
    return value.strip()


def select_query(record: Mapping[str, Any], *, row: int, preferred: str = "auto") -> str:
    """Select a fixture query while supporting corpus-writer field names."""

    return select_query_and_field(record, row=row, preferred=preferred)[0]


def select_query_and_field(
    record: Mapping[str, Any], *, row: int, preferred: str = "auto"
) -> tuple[str, str]:
    """Return selected query text and its source field."""

    candidates: tuple[str, ...]
    if preferred == "translated_query":
        candidates = ("translated_query",)
    elif preferred == "english_query":
        candidates = ("english_query", "query")
    elif preferred == "query":
        candidates = ("query", "english_query")
    elif preferred == "auto":
        language = str(record.get("language") or "").strip().casefold()
        if language == "hi" or language.startswith("hi-") or language == "hindi":
            candidates = ("translated_query", "english_query", "query")
        else:
            candidates = ("english_query", "query", "translated_query")
    else:
        raise EvaluationError(f"Unsupported preferred query field: {preferred!r}")
    for field in candidates:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip(), field
    raise EvaluationError(
        f"Row {row} has no usable query for query field {preferred!r}; checked {list(candidates)}"
    )


def normalize_distinct_text(value: str) -> str:
    return " ".join(value.casefold().split())


def enforce_distinct(
    records: Sequence[Mapping[str, Any]],
    *,
    id_field: str,
    content_field: str | None = None,
) -> None:
    seen_ids: dict[str, int] = {}
    seen_content: dict[str, int] = {}
    for row_number, record in enumerate(records, start=1):
        identifier = require_text(record, id_field, row=row_number)
        if identifier in seen_ids:
            raise EvaluationError(
                f"Duplicate {id_field} {identifier!r} in rows "
                f"{seen_ids[identifier]} and {row_number}; benchmark inputs must be distinct"
            )
        seen_ids[identifier] = row_number
        if content_field is None:
            continue
        content = normalize_distinct_text(require_text(record, content_field, row=row_number))
        if content in seen_content:
            raise EvaluationError(
                f"Repeated normalized {content_field} in rows "
                f"{seen_content[content]} and {row_number}; repeated queries are not allowed"
            )
        seen_content[content] = row_number


def require_minimum_cases(
    count: int,
    minimum: int,
    *,
    suite: str,
    allow_small_smoke: bool,
) -> str:
    if count >= minimum:
        return "qualifying"
    if not allow_small_smoke:
        raise EvaluationError(
            f"{suite} requires at least {minimum} distinct cases; found {count}. "
            "Use --allow-small-smoke only for a non-qualifying smoke run."
        )
    return "non_qualifying_small_smoke"


def _declared_query_ids(
    value: Any,
) -> tuple[tuple[str, ...], bool]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return (), False
    stripped = [item.strip() for item in value]
    if any(not item for item in stripped) or len(set(stripped)) != len(stripped):
        return (), False
    normalized = tuple(sorted(stripped))
    return normalized, list(normalized) == value


def _record_query_ids(
    records: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, ...], bool]:
    identifiers: list[str] = []
    for record in records:
        value = record.get("query_id")
        if not isinstance(value, str) or not value.strip():
            return (), False
        identifiers.append(value.strip())
    if len(set(identifiers)) != len(identifiers):
        return (), False
    return tuple(sorted(identifiers)), bool(identifiers)


def _record_query_content_hashes(
    records: Sequence[Mapping[str, Any]],
    *,
    query_field: str,
) -> tuple[tuple[str, ...], bool]:
    from app.evaluation.thresholds import query_content_sha256

    hashes: set[str] = set()
    try:
        for row_number, record in enumerate(records, start=1):
            query, _source = select_query_and_field(
                record,
                row=row_number,
                preferred=query_field,
            )
            hashes.add(query_content_sha256(query))
    except (EvaluationError, ValueError):
        return (), False
    return tuple(sorted(hashes)), bool(hashes)


def _partitioned_held_out_provenance(
    fixture: Path,
    records: Sequence[Mapping[str, Any]],
    *,
    corpus_manifest_path: Path,
    partition_manifest_path: Path,
    query_field: str,
) -> dict[str, Any]:
    """Validate a deterministic final partition against its source corpus build."""

    from app.evaluation.thresholds import query_ids_sha256

    fixture_hash = file_sha256(fixture)
    evidence: dict[str, Any] = {
        "qualifying": False,
        "status": "partition_manifest_missing",
        "manifest_path": str(corpus_manifest_path.resolve()),
        "partition_manifest_path": str(partition_manifest_path.resolve()),
        "fixture_sha256": fixture_hash,
        "allowed_splits": ["final"],
        "checks": {
            "manifest_exists": corpus_manifest_path.is_file(),
            "partition_manifest_exists": partition_manifest_path.is_file(),
        },
    }
    if not corpus_manifest_path.is_file() or not partition_manifest_path.is_file():
        return evidence

    corpus_manifest = load_json_object(corpus_manifest_path)
    partition_manifest = load_json_object(partition_manifest_path)
    dataset = corpus_manifest.get("dataset")
    corpus_artifacts = corpus_manifest.get("artifacts")
    source_fixture_artifact = (
        corpus_artifacts.get("evaluation_fixtures")
        if isinstance(corpus_artifacts, Mapping)
        else None
    )
    corpus_artifact = (
        corpus_artifacts.get("corpus") if isinstance(corpus_artifacts, Mapping) else None
    )
    source = partition_manifest.get("source")
    source_fixture = source.get("fixture") if isinstance(source, Mapping) else None
    source_corpus_manifest = source.get("corpus_manifest") if isinstance(source, Mapping) else None
    partitions = partition_manifest.get("partitions")
    development = partitions.get("development") if isinstance(partitions, Mapping) else None
    final = partitions.get("final") if isinstance(partitions, Mapping) else None

    source_ids, source_ids_valid = _declared_query_ids(
        source_fixture.get("query_ids") if isinstance(source_fixture, Mapping) else None
    )
    development_ids, development_ids_valid = _declared_query_ids(
        development.get("query_ids") if isinstance(development, Mapping) else None
    )
    final_ids, final_ids_valid = _declared_query_ids(
        final.get("query_ids") if isinstance(final, Mapping) else None
    )
    source_content_hashes, source_content_hashes_valid = _declared_query_ids(
        source_fixture.get("content_hashes") if isinstance(source_fixture, Mapping) else None
    )
    development_content_hashes, development_content_hashes_valid = _declared_query_ids(
        development.get("content_hashes") if isinstance(development, Mapping) else None
    )
    final_content_hashes, final_content_hashes_valid = _declared_query_ids(
        final.get("content_hashes") if isinstance(final, Mapping) else None
    )
    source_content_hashes_valid = source_content_hashes_valid and all(
        len(item) == 64 and all(character in "0123456789abcdef" for character in item)
        for item in source_content_hashes
    )
    development_content_hashes_valid = development_content_hashes_valid and all(
        len(item) == 64 and all(character in "0123456789abcdef" for character in item)
        for item in development_content_hashes
    )
    final_content_hashes_valid = final_content_hashes_valid and all(
        len(item) == 64 and all(character in "0123456789abcdef" for character in item)
        for item in final_content_hashes
    )
    observed_ids, observed_ids_valid = _record_query_ids(records)
    observed_content_hashes, observed_content_hashes_valid = _record_query_content_hashes(
        records, query_field=query_field
    )
    row_splits = [str(record.get("split") or "").strip().casefold() for record in records]
    row_languages = [str(record.get("language") or "").strip().casefold() for record in records]
    dataset_language = (
        str(dataset.get("language") or "").strip().casefold()
        if isinstance(dataset, Mapping)
        else ""
    )
    source_fixture_hash = (
        str(source_fixture.get("sha256") or "").strip().casefold()
        if isinstance(source_fixture, Mapping)
        else ""
    )
    source_manifest_fixture_hash = (
        str(source_fixture_artifact.get("sha256") or "").strip().casefold()
        if isinstance(source_fixture_artifact, Mapping)
        else ""
    )
    corpus_hash = (
        str(corpus_artifact.get("sha256") or "").strip().casefold()
        if isinstance(corpus_artifact, Mapping)
        else ""
    )
    corpus_manifest_hash = file_sha256(corpus_manifest_path)

    def metadata_matches_ids(metadata: Any, identifiers: tuple[str, ...]) -> bool:
        return bool(
            isinstance(metadata, Mapping)
            and metadata.get("records") == len(identifiers)
            and metadata.get("query_ids_sha256") == query_ids_sha256(identifiers)
        )

    def metadata_matches_content_hashes(metadata: Any, content_hashes: tuple[str, ...]) -> bool:
        return bool(
            isinstance(metadata, Mapping)
            and metadata.get("content_hash_count") == len(content_hashes)
            and metadata.get("content_hashes_sha256") == query_ids_sha256(content_hashes)
        )

    algorithm = partition_manifest.get("algorithm")

    checks = {
        "manifest_exists": True,
        "partition_manifest_exists": True,
        "partition_schema_version_is_1": partition_manifest.get("schema_version") == 1,
        "partition_artifact_type": partition_manifest.get("artifact_type")
        == "evaluation_fixture_partition",
        "partition_algorithm_is_supported": isinstance(algorithm, Mapping)
        and algorithm.get("name") == "sha256-seeded-normalized-query-content-v1",
        "partition_query_field_matches_evaluation": isinstance(algorithm, Mapping)
        and algorithm.get("query_field") == query_field,
        "dataset_identity_declared": bool(
            isinstance(dataset, Mapping)
            and str(dataset.get("id") or "").strip()
            and str(dataset.get("revision") or "").strip()
        ),
        "source_dataset_split_is_validation": isinstance(dataset, Mapping)
        and str(dataset.get("split") or "").strip().casefold() == "validation",
        "partition_binds_corpus_manifest": isinstance(source_corpus_manifest, Mapping)
        and source_corpus_manifest.get("sha256") == corpus_manifest_hash,
        "source_fixture_matches_corpus_manifest": bool(source_fixture_hash)
        and source_fixture_hash == source_manifest_fixture_hash,
        "source_fixture_count_matches_corpus_manifest": bool(
            isinstance(source_fixture, Mapping)
            and isinstance(source_fixture_artifact, Mapping)
            and source_fixture.get("records") == source_fixture_artifact.get("records")
        ),
        "source_query_ids_valid": source_ids_valid
        and metadata_matches_ids(source_fixture, source_ids),
        "development_query_ids_valid": development_ids_valid
        and metadata_matches_ids(development, development_ids),
        "final_query_ids_valid": final_ids_valid and metadata_matches_ids(final, final_ids),
        "source_content_hashes_valid": source_content_hashes_valid
        and metadata_matches_content_hashes(source_fixture, source_content_hashes),
        "development_content_hashes_valid": development_content_hashes_valid
        and metadata_matches_content_hashes(development, development_content_hashes),
        "final_content_hashes_valid": final_content_hashes_valid
        and metadata_matches_content_hashes(final, final_content_hashes),
        "partitions_are_disjoint": not set(development_ids).intersection(final_ids),
        "partitions_cover_source": set(development_ids).union(final_ids) == set(source_ids),
        "partition_content_is_disjoint": not set(development_content_hashes).intersection(
            final_content_hashes
        ),
        "partition_content_covers_source": set(development_content_hashes).union(
            final_content_hashes
        )
        == set(source_content_hashes),
        "all_fixture_rows_are_final": bool(row_splits) and set(row_splits) == {"final"},
        "all_fixture_rows_declare_one_language": bool(row_languages)
        and all(row_languages)
        and len(set(row_languages)) == 1,
        "fixture_language_matches_source": bool(row_languages)
        and len(set(row_languages)) == 1
        and row_languages[0] == dataset_language,
        "fixture_query_ids_match_final_partition": observed_ids_valid and observed_ids == final_ids,
        "fixture_content_matches_final_partition": observed_content_hashes_valid
        and observed_content_hashes == final_content_hashes,
        "fixture_sha256_matches_partition": isinstance(final, Mapping)
        and final.get("sha256") == fixture_hash,
        "fixture_bytes_match_partition": isinstance(final, Mapping)
        and final.get("bytes") == fixture.stat().st_size,
        "fixture_record_count_matches_partition": isinstance(final, Mapping)
        and final.get("records") == len(records),
        "corpus_artifact_sha256_declared": len(corpus_hash) == 64,
    }
    failed = [name for name, passed in checks.items() if not passed]
    evidence.update(
        {
            "qualifying": not failed,
            "status": ("verified_partitioned_held_out" if not failed else "invalid_provenance"),
            # The active index binds the source corpus manifest, not the derived
            # partition manifest. Preserve that identity for corpus_index_provenance.
            "manifest_sha256": corpus_manifest_hash,
            "partition_manifest_sha256": file_sha256(partition_manifest_path),
            "dataset": dict(dataset) if isinstance(dataset, Mapping) else None,
            "fixture_artifact": dict(final) if isinstance(final, Mapping) else None,
            "corpus_artifact_sha256": corpus_hash or None,
            "checks": checks,
            "failed_checks": failed,
        }
    )
    return evidence


def held_out_provenance(
    fixture: Path,
    records: Sequence[Mapping[str, Any]],
    *,
    corpus_manifest: Path | None = None,
    partition_manifest: Path | None = None,
    query_field: str = "auto",
) -> dict[str, Any]:
    """Validate that a fixture is the held-out artifact recorded by a corpus build."""

    manifest_path = corpus_manifest or fixture.with_name("corpus-manifest.json")
    partition_path = partition_manifest
    if partition_path is None:
        candidate = fixture.with_name("partition-manifest.json")
        if candidate.is_file():
            partition_path = candidate
    if partition_path is not None:
        return _partitioned_held_out_provenance(
            fixture,
            records,
            corpus_manifest_path=manifest_path,
            partition_manifest_path=partition_path,
            query_field=query_field,
        )
    fixture_hash = file_sha256(fixture)
    evidence: dict[str, Any] = {
        "qualifying": False,
        "status": "corpus_manifest_missing",
        "manifest_path": str(manifest_path.resolve()),
        "fixture_sha256": fixture_hash,
        "allowed_splits": sorted(HELD_OUT_SPLITS),
        "checks": {"manifest_exists": manifest_path.is_file()},
    }
    if not manifest_path.is_file():
        return evidence

    manifest = load_json_object(manifest_path)
    dataset = manifest.get("dataset")
    artifacts = manifest.get("artifacts")
    fixture_artifact = (
        artifacts.get("evaluation_fixtures") if isinstance(artifacts, Mapping) else None
    )
    corpus_artifact = artifacts.get("corpus") if isinstance(artifacts, Mapping) else None
    manifest_split = (
        str(dataset.get("split") or "").strip().casefold() if isinstance(dataset, Mapping) else ""
    )
    manifest_language = (
        str(dataset.get("language") or "").strip().casefold()
        if isinstance(dataset, Mapping)
        else ""
    )
    row_splits = [str(record.get("split") or "").strip().casefold() for record in records]
    row_languages = [str(record.get("language") or "").strip().casefold() for record in records]
    expected_fixture_hash = (
        str(fixture_artifact.get("sha256") or "").strip().casefold()
        if isinstance(fixture_artifact, Mapping)
        else ""
    )
    expected_fixture_records = (
        fixture_artifact.get("records") if isinstance(fixture_artifact, Mapping) else None
    )
    corpus_hash = (
        str(corpus_artifact.get("sha256") or "").strip().casefold()
        if isinstance(corpus_artifact, Mapping)
        else ""
    )
    checks = {
        "manifest_exists": True,
        "dataset_identity_declared": bool(
            isinstance(dataset, Mapping)
            and str(dataset.get("id") or "").strip()
            and str(dataset.get("revision") or "").strip()
        ),
        "manifest_split_is_held_out": manifest_split in HELD_OUT_SPLITS,
        "all_fixture_rows_declare_one_split": bool(row_splits)
        and all(row_splits)
        and len(set(row_splits)) == 1,
        "fixture_split_matches_manifest": bool(row_splits)
        and len(set(row_splits)) == 1
        and row_splits[0] == manifest_split,
        "all_fixture_rows_declare_one_language": bool(row_languages)
        and all(row_languages)
        and len(set(row_languages)) == 1,
        "fixture_language_matches_manifest": bool(row_languages)
        and len(set(row_languages)) == 1
        and row_languages[0] == manifest_language,
        "fixture_sha256_matches_manifest": bool(expected_fixture_hash)
        and expected_fixture_hash == fixture_hash,
        "fixture_record_count_matches_manifest": isinstance(expected_fixture_records, int)
        and not isinstance(expected_fixture_records, bool)
        and expected_fixture_records == len(records),
        "corpus_artifact_sha256_declared": len(corpus_hash) == 64,
    }
    failed = [name for name, passed in checks.items() if not passed]
    evidence.update(
        {
            "qualifying": not failed,
            "status": "verified_held_out" if not failed else "invalid_provenance",
            "manifest_sha256": file_sha256(manifest_path),
            "dataset": dict(dataset) if isinstance(dataset, Mapping) else None,
            "fixture_artifact": (
                dict(fixture_artifact) if isinstance(fixture_artifact, Mapping) else None
            ),
            "corpus_artifact_sha256": corpus_hash or None,
            "checks": checks,
            "failed_checks": failed,
        }
    )
    return evidence


def service_index_manifest(services: Any) -> tuple[Path, dict[str, Any]]:
    path = getattr(services, "index_manifest_path", None)
    if not isinstance(path, Path) or not path.is_file():
        raise EvaluationError("Final evaluation requires DefaultServices.index_manifest_path")
    return path, load_json_object(path)


def corpus_index_provenance(
    provenance: Mapping[str, Any],
    *,
    index_manifest_path: Path,
    index_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Require the active index to be derived from the fixture's corpus manifest."""

    expected_manifest_hash = provenance.get("manifest_sha256")
    expected_corpus_hash = provenance.get("corpus_artifact_sha256")
    observed_manifest_hash = index_manifest.get("corpus_manifest_sha256")
    checksums = index_manifest.get("checksums")
    observed_corpus_hash = checksums.get("corpus") if isinstance(checksums, Mapping) else None
    mismatches: list[str] = []
    if (
        expected_manifest_hash
        and observed_manifest_hash
        and expected_manifest_hash != observed_manifest_hash
    ):
        mismatches.append("corpus_manifest_sha256")
    if (
        expected_corpus_hash
        and observed_corpus_hash
        and expected_corpus_hash != observed_corpus_hash
    ):
        mismatches.append("corpus_artifact_sha256")
    if mismatches:
        raise EvaluationError(
            "Evaluation fixture provenance conflicts with the active index: "
            + ", ".join(mismatches)
        )
    checks = {
        "held_out_provenance_verified": provenance.get("qualifying") is True,
        "index_declares_corpus_manifest_sha256": bool(observed_manifest_hash),
        "corpus_manifest_sha256_matches_index": bool(expected_manifest_hash)
        and expected_manifest_hash == observed_manifest_hash,
        "index_declares_corpus_artifact_sha256": bool(observed_corpus_hash),
        "corpus_artifact_sha256_matches_index": bool(expected_corpus_hash)
        and expected_corpus_hash == observed_corpus_hash,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "qualifying": not failed,
        "status": "verified" if not failed else "incomplete",
        "index_manifest_path": str(index_manifest_path.resolve()),
        "index_manifest_sha256": file_sha256(index_manifest_path),
        "expected_corpus_manifest_sha256": expected_manifest_hash,
        "observed_corpus_manifest_sha256": observed_manifest_hash,
        "expected_corpus_artifact_sha256": expected_corpus_hash,
        "observed_corpus_artifact_sha256": observed_corpus_hash,
        "checks": checks,
        "failed_checks": failed,
    }


def final_threshold_provenance(
    services: Any,
    *,
    final_fixture_sha256: str,
    final_query_ids: Sequence[str],
    final_queries: Sequence[str],
    index_manifest_path: Path,
    index_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate development-frozen thresholds against a final evaluation/index."""

    settings = getattr(services, "settings", None)
    path = getattr(settings, "rag_thresholds_path", None)
    if not isinstance(path, Path):
        return {
            "qualifying": False,
            "status": "runtime_threshold_path_unavailable",
        }
    if not path.is_file():
        return {
            "qualifying": False,
            "status": "frozen_thresholds_missing",
            "path": str(path.resolve()),
        }
    try:
        from app.evaluation.thresholds import (
            frozen_threshold_binding_errors,
            load_frozen_thresholds,
            query_content_sha256,
            query_ids_sha256,
            retrieval_runtime_contract,
            retrieval_runtime_contract_sha256,
        )
        from app.retrieval.router import TIDE_ROUTER_CONTRACT_VERSION

        frozen = load_frozen_thresholds(path)
    except Exception as exc:
        raise EvaluationError(f"Invalid frozen threshold artifact {path}: {exc}") from exc
    if frozen.development_fixture_sha256 == final_fixture_sha256:
        raise EvaluationError(
            "Final evaluation fixture is identical to the development threshold fixture"
        )

    normalized_final_query_ids: list[str] = []
    for identifier in final_query_ids:
        if not isinstance(identifier, str) or not identifier.strip():
            raise EvaluationError("Final evaluation requires non-empty string query_id values")
        normalized_final_query_ids.append(identifier.strip())
    if not normalized_final_query_ids:
        raise EvaluationError("Final evaluation contains no query IDs")
    if len(set(normalized_final_query_ids)) != len(normalized_final_query_ids):
        raise EvaluationError("Final evaluation query IDs must be unique")
    final_ids = tuple(sorted(normalized_final_query_ids))
    overlapping_ids = sorted(set(final_ids).intersection(frozen.development_query_ids))
    if overlapping_ids:
        preview = ", ".join(overlapping_ids[:10])
        suffix = "" if len(overlapping_ids) <= 10 else ", ..."
        raise EvaluationError(
            "Final evaluation query IDs overlap the development threshold fixture: "
            f"{preview}{suffix}"
        )
    if len(final_queries) != len(final_ids):
        raise EvaluationError(
            "Final evaluation requires one selected query text for every query ID"
        )
    try:
        final_content_hashes = tuple(
            sorted({query_content_sha256(query) for query in final_queries})
        )
    except (AttributeError, ValueError) as exc:
        raise EvaluationError("Final evaluation contains an invalid selected query text") from exc
    overlapping_content_hashes = sorted(
        set(final_content_hashes).intersection(frozen.development_query_content_hashes)
    )
    if overlapping_content_hashes:
        raise EvaluationError(
            "Final evaluation contains normalized query content used during "
            "development threshold calibration"
        )

    try:
        runtime_contract = retrieval_runtime_contract(settings)
        runtime_contract_sha256 = retrieval_runtime_contract_sha256(settings)
    except (AttributeError, TypeError, ValueError) as exc:
        raise EvaluationError(
            "Final evaluation could not derive the active retrieval runtime contract"
        ) from exc

    binding = frozen.retrieval_artifacts
    bound = binding.model_dump(mode="json") if binding is not None else {}
    checksums = index_manifest.get("checksums")
    observed = {
        "index_manifest_sha256": file_sha256(index_manifest_path),
        "corpus_manifest_sha256": index_manifest.get("corpus_manifest_sha256"),
        "corpus_artifact_sha256": (
            checksums.get("corpus") if isinstance(checksums, Mapping) else None
        ),
        "chunk_build_id": index_manifest.get("chunk_build_id"),
        "collection": index_manifest.get("collection"),
        "dense_model": index_manifest.get("dense_model"),
        "model_revision": index_manifest.get("model_revision"),
        "retrieval_contract_version": TIDE_ROUTER_CONTRACT_VERSION,
        "retrieval_contract_sha256": runtime_contract_sha256,
    }
    binding_errors = frozen_threshold_binding_errors(
        frozen,
        index_manifest=index_manifest,
        index_manifest_sha256=str(observed["index_manifest_sha256"]),
        runtime_settings=settings,
    )
    mismatches = sorted(
        error.removesuffix("_mismatch") for error in binding_errors if error.endswith("_mismatch")
    )
    if mismatches:
        raise EvaluationError(
            "Frozen thresholds conflict with the active retrieval artifacts/runtime: "
            + ", ".join(sorted(mismatches))
        )
    checks = {
        "threshold_schema_version_is_3": frozen.schema_version == 3,
        "raw_dense_score_contract": frozen.score_kind == "raw_dense_similarity"
        and frozen.score_contract_version == "raw-dense-similarity-v1",
        "development_fixture_differs_from_final": True,
        "development_query_ids_recorded": frozen.development_query_count
        == len(frozen.development_query_ids),
        "development_and_final_query_ids_disjoint": not overlapping_ids,
        "development_and_final_query_content_disjoint": not overlapping_content_hashes,
        "retrieval_artifacts_bound": binding is not None,
        **{
            f"{name}_bound_and_matching": value is not None
            and bound.get(name) is not None
            and bound.get(name) == value
            for name, value in observed.items()
        },
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "qualifying": not failed,
        "status": "verified" if not failed else "incomplete_binding",
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
        "schema_version": frozen.schema_version,
        "development_fixture_sha256": frozen.development_fixture_sha256,
        "development_query_count": frozen.development_query_count,
        "development_query_ids_sha256": frozen.development_query_ids_sha256,
        "development_query_content_count": frozen.development_query_content_count,
        "development_query_content_hashes_sha256": (frozen.development_query_content_hashes_sha256),
        "final_query_count": len(final_ids),
        "final_query_ids_sha256": query_ids_sha256(final_ids),
        "final_query_content_count": len(final_content_hashes),
        "final_query_content_hashes_sha256": query_ids_sha256(final_content_hashes),
        "retrieval_runtime_contract": runtime_contract,
        "retrieval_artifacts": bound or None,
        "binding_errors": binding_errors,
        "checks": checks,
        "failed_checks": failed,
    }


def evaluation_qualification(
    *,
    size_qualification: str,
    provenance: Mapping[str, Any],
    index_provenance: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    expected_requests: int,
    recorded_requests: int,
    successful_requests: int,
    request_failures: int,
    configuration_failures: int,
    additional_checks: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build a fail-closed qualification decision from explicit evidence."""

    coverage = successful_requests / expected_requests if expected_requests else 0.0
    checks = {
        "minimum_distinct_cases": size_qualification == "qualifying",
        "verified_held_out_provenance": provenance.get("qualifying") is True,
        "fixture_matches_active_index": index_provenance.get("qualifying") is True,
        "development_thresholds_bound_to_active_index": thresholds.get("qualifying") is True,
        "all_requests_recorded": recorded_requests == expected_requests,
        "zero_request_failures": request_failures == 0,
        "zero_configuration_failures": configuration_failures == 0,
        "full_retrieval_coverage": successful_requests == expected_requests,
        **dict(additional_checks or {}),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "qualifying": not failed,
        "status": "qualifying" if not failed else f"non_qualifying_{failed[0]}",
        "checks": checks,
        "failed_checks": failed,
        "expected_requests": expected_requests,
        "recorded_requests": recorded_requests,
        "successful_requests": successful_requests,
        "request_failure_count": request_failures,
        "configuration_failure_count": configuration_failures,
        "retrieval_completion_coverage": coverage,
    }


def raw_dense_score_evidence(hits: Sequence[Any]) -> dict[str, Any]:
    """Export the exact raw-dense score contract used by answerability gating."""

    from app.evaluation.thresholds import (
        RAW_DENSE_SCORE_CONTRACT_VERSION,
        RAW_DENSE_SCORE_KIND,
    )

    scores = sorted(
        (float(score) for hit in hits if (score := getattr(hit, "dense_score", None)) is not None),
        reverse=True,
    )
    top = scores[0] if scores else None
    second = scores[1] if len(scores) > 1 else None
    return {
        "score_kind": RAW_DENSE_SCORE_KIND,
        "score_contract_version": RAW_DENSE_SCORE_CONTRACT_VERSION,
        "raw_dense_score_count": len(scores),
        "top_raw_dense_similarity": top,
        "second_raw_dense_similarity": second,
        "raw_dense_similarity_margin": (
            top - (second if second is not None else 0.0) if top is not None else None
        ),
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write(
        path,
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
        + "\n",
    )


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise EvaluationError("Refusing to write an empty raw-results JSONL artifact")
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, default=_json_default) + "\n"
        for row in rows
    )
    _atomic_write(path, text)


def _csv_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise EvaluationError("Refusing to write an empty raw-results CSV artifact")
    fields = sorted({str(key) for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: _csv_value(row.get(field)) for field in fields})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_report_bundle(
    output_prefix: Path,
    *,
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    markdown: str,
) -> dict[str, Path]:
    paths = {
        "jsonl": output_prefix.with_suffix(".jsonl"),
        "csv": output_prefix.with_suffix(".csv"),
        "json": output_prefix.with_suffix(".json"),
        "markdown": output_prefix.with_suffix(".md"),
    }
    write_jsonl(paths["jsonl"], rows)
    write_csv(paths["csv"], rows)
    write_json(paths["json"], summary)
    _atomic_write(paths["markdown"], markdown.rstrip() + "\n")
    return paths


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    def cell(value: Any) -> str:
        if isinstance(value, float):
            rendered = f"{value:.6f}".rstrip("0").rstrip(".")
        elif isinstance(value, dict | list | tuple):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        elif value is None:
            rendered = "—"
        else:
            rendered = str(value)
        return rendered.replace("|", "\\|").replace("\n", " ")

    header = "| " + " | ".join(cell(item) for item in headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(cell(item) for item in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def package_versions(names: Sequence[str] | None = None) -> dict[str, str]:
    packages = names or (
        "awaaz-tiderag",
        "fastapi",
        "httpx",
        "numpy",
        "pydantic",
        "qdrant-client",
        "sentence-transformers",
        "websockets",
    )
    versions: dict[str, str] = {}
    for name in packages:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def hardware_metadata() -> dict[str, Any]:
    memory_bytes: int | None = None
    if hasattr(os, "sysconf"):
        try:
            memory_bytes = int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
        except (OSError, ValueError, TypeError):
            memory_bytes = None
    elif platform.system() == "Windows":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        kernel32 = ctypes.windll.kernel32
        if kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            memory_bytes = int(status.total_physical)
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine() or "unreported",
        "processor": platform.processor() or "unreported",
        "logical_cpu_count": os.cpu_count(),
        "physical_memory_bytes": memory_bytes,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
    }


def base_metadata(
    *,
    command: str,
    fixture: Path,
    cache_policy: str,
    concurrency: int,
    qualification: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": utc_now_iso(),
        "command": command,
        "qualification": qualification,
        "fixture": {
            "path": str(fixture.resolve()),
            "sha256": file_sha256(fixture),
        },
        "cache_policy": cache_policy,
        "concurrency": concurrency,
        "hardware": hardware_metadata(),
        "hardware_scope": "machine running this evaluation command",
        "packages": package_versions(),
        "packages_scope": "Python environment running this evaluation command",
    }


def corpus_metadata(services: Any) -> dict[str, Any]:
    """Collect local manifest metadata without making up unavailable counts."""

    runtime: dict[str, Any] = {}
    settings = getattr(services, "settings", None)
    feature_flags = getattr(settings, "retrieval_feature_flags", None)
    if isinstance(feature_flags, dict):
        runtime["feature_flags"] = dict(feature_flags)
    enabled_strategies = getattr(settings, "enabled_chunk_strategies", None)
    if isinstance(enabled_strategies, tuple):
        runtime["enabled_dense_strategies"] = [
            str(strategy.value) for strategy in enabled_strategies
        ]

    manifest_path = getattr(services, "index_manifest_path", None)
    if isinstance(manifest_path, Path) and manifest_path.is_file():
        try:
            manifest = load_json_object(manifest_path)
        except EvaluationError as exc:
            return {
                "available": False,
                "reason": str(exc),
                "path": str(manifest_path),
                "runtime": runtime,
            }
        wanted = (
            "collection",
            "point_count",
            "chunk_count",
            "document_count",
            "chunk_build_id",
            "corpus_manifest_sha256",
            "index_size_bytes",
            "build_duration_ms",
            "disk_bytes",
            "build_time_seconds",
            "dense_model",
            "model_revision",
            "dense_vector_size",
            "strategy_counts",
            "strategies",
            "feature_flags",
            "enabled_dense_strategies",
            "sparse_vectors_built",
        )
        return {
            "available": True,
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": file_sha256(manifest_path),
            "runtime": runtime,
            **{key: manifest[key] for key in wanted if key in manifest},
        }
    return {
        "available": False,
        "reason": "DefaultServices did not expose an existing index manifest",
        "runtime": runtime,
    }


@asynccontextmanager
async def initialized_services() -> AsyncIterator[Any]:
    """Initialize the real service container and require retrieval readiness."""

    try:
        from app.core.config import get_settings
        from app.services import DefaultServices
    except ImportError as exc:
        raise EvaluationError(
            "The application service container is unavailable; install backend dependencies "
            "and provide app.services.DefaultServices"
        ) from exc
    services = DefaultServices(get_settings())
    try:
        await services.initialize()
        orchestrator = getattr(services, "orchestrator", None)
        if orchestrator is None:
            readiness = await services.readiness() if hasattr(services, "readiness") else None
            raise EvaluationError(
                "DefaultServices initialized without an orchestrator/retriever. "
                f"Build the corpus/index and start Qdrant first. Readiness: {readiness!r}"
            )
        if getattr(orchestrator, "retriever", None) is None:
            raise EvaluationError("DefaultServices.orchestrator has no retriever")
        if hasattr(services, "readiness"):
            readiness = await services.readiness()
            checks = readiness.get("checks", {}) if isinstance(readiness, Mapping) else {}
            unavailable = {
                name: checks.get(name)
                for name in ("index", "model", "qdrant")
                if not isinstance(checks.get(name), Mapping)
                or checks[name].get("ready") is not True
            }
            if unavailable:
                raise EvaluationError(
                    "Retrieval services are not ready; build the corpus/index and start "
                    f"Qdrant first. Failed checks: {unavailable!r}"
                )
        yield services
    finally:
        try:
            await services.close()
        except Exception as exc:
            if sys.exc_info()[0] is None:
                raise EvaluationError(f"Failed to close DefaultServices cleanly: {exc}") from exc


def print_artifacts(paths: Mapping[str, Path]) -> None:
    for kind, path in paths.items():
        print(f"{kind.upper()}: {path}")


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"expected an integer, got {value!r}") from exc
    if parsed < 1:
        raise ValueError("value must be positive")
    return parsed
