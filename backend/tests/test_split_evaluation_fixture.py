from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

from app.evaluation.thresholds import query_content_sha256
from scripts import split_evaluation_fixture
from scripts._common import (
    EvaluationError,
    file_sha256,
    held_out_provenance,
    load_records,
)


def _source_fixture(root: Path) -> tuple[Path, Path, list[dict[str, Any]]]:
    root.mkdir(parents=True, exist_ok=True)
    fixture = root / "evaluation-fixtures.jsonl"
    translated_queries = (
        "गोवा कहाँ है?",
        "गोवा कहाँ है",
        "गोवा राज्य कब बना?",
        "पणजी कहाँ है?",
        "गोवा की राजधानी क्या है?",
        "गोवा में कौन सी भाषा बोली जाती है?",
    )
    rows = [
        {
            "query_id": f"q{index}",
            "english_query": f"English query {index}",
            "translated_query": translated_query,
            "relevant_canonical_ids": [f"document-{index}"],
            "language": "hi",
            "split": "validation",
        }
        for index, translated_query in enumerate(translated_queries)
    ]
    fixture.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )
    corpus_manifest = root / "corpus-manifest.json"
    corpus_manifest.write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "dataset": {
                    "id": "fixture/dataset",
                    "revision": "fixed-revision",
                    "language": "hi",
                    "split": "validation",
                },
                "artifacts": {
                    "corpus": {"sha256": "a" * 64},
                    "evaluation_fixtures": {
                        "sha256": file_sha256(fixture),
                        "records": len(rows),
                    },
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return fixture, corpus_manifest, rows


def _args(
    fixture: Path,
    corpus_manifest: Path,
    output_dir: Path,
    *,
    development_count: int | None = None,
) -> Namespace:
    return Namespace(
        fixture=fixture,
        corpus_manifest=corpus_manifest,
        output_dir=output_dir,
        development_count=development_count,
        final_count=None,
        require_final_relevance_labels=False,
        seed=2026,
        query_field="auto",
    )


def test_split_is_deterministic_content_disjoint_and_provenance_verifiable(
    tmp_path: Path,
) -> None:
    fixture, corpus_manifest, source_rows = _source_fixture(tmp_path / "source")
    first, first_artifacts = split_evaluation_fixture.run(
        _args(fixture, corpus_manifest, tmp_path / "first")
    )
    second, second_artifacts = split_evaluation_fixture.run(
        _args(fixture, corpus_manifest, tmp_path / "second")
    )

    assert first == second
    assert first_artifacts.development.read_bytes() == second_artifacts.development.read_bytes()
    assert first_artifacts.final.read_bytes() == second_artifacts.final.read_bytes()
    assert first_artifacts.manifest.read_bytes() == second_artifacts.manifest.read_bytes()

    development_rows = load_records(first_artifacts.development)
    final_rows = load_records(first_artifacts.final)
    assert all(row["is_answerable"] is True for row in development_rows)
    assert all(row["is_answerable"] is True for row in final_rows)
    development_ids = {str(row["query_id"]) for row in development_rows}
    final_ids = {str(row["query_id"]) for row in final_rows}
    assert development_ids.isdisjoint(final_ids)
    assert development_ids.union(final_ids) == {
        str(row["query_id"]) for row in source_rows
    }
    # Punctuation variants normalize to one content group and can never straddle.
    assert query_content_sha256("गोवा कहाँ है?") == query_content_sha256("गोवा कहाँ है")
    assert ({"q0", "q1"} <= development_ids) or ({"q0", "q1"} <= final_ids)
    development_hashes = set(
        first["partitions"]["development"]["content_hashes"]
    )
    final_hashes = set(first["partitions"]["final"]["content_hashes"])
    assert development_hashes.isdisjoint(final_hashes)

    evidence = held_out_provenance(
        first_artifacts.final,
        final_rows,
        corpus_manifest=corpus_manifest,
        partition_manifest=first_artifacts.manifest,
        query_field="auto",
    )
    assert evidence["qualifying"] is True
    assert evidence["status"] == "verified_partitioned_held_out"


def test_explicit_count_cannot_split_a_duplicate_content_group(tmp_path: Path) -> None:
    fixture, corpus_manifest, rows = _source_fixture(tmp_path / "source")
    # Leave two content groups of size two, so one row cannot be selected safely.
    rows = rows[:4]
    rows[2]["translated_query"] = "पणजी राजधानी है!"
    rows[3]["translated_query"] = "पणजी राजधानी है"
    fixture.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )
    manifest = json.loads(corpus_manifest.read_text(encoding="utf-8"))
    manifest["artifacts"]["evaluation_fixtures"] = {
        "sha256": file_sha256(fixture),
        "records": len(rows),
    }
    corpus_manifest.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    with pytest.raises(EvaluationError, match="cannot be satisfied"):
        split_evaluation_fixture.run(
            _args(
                fixture,
                corpus_manifest,
                tmp_path / "partition",
                development_count=1,
            )
        )


def test_partition_provenance_rejects_content_hash_overlap(tmp_path: Path) -> None:
    fixture, corpus_manifest, _rows = _source_fixture(tmp_path / "source")
    manifest, artifacts = split_evaluation_fixture.run(
        _args(fixture, corpus_manifest, tmp_path / "partition")
    )
    final_rows = load_records(artifacts.final)
    manifest["partitions"]["final"]["content_hashes"].append(
        manifest["partitions"]["development"]["content_hashes"][0]
    )
    manifest["partitions"]["final"]["content_hashes"].sort()
    # Leaving the digest/count untouched also demonstrates fail-closed metadata checks.
    artifacts.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    evidence = held_out_provenance(
        artifacts.final,
        final_rows,
        corpus_manifest=corpus_manifest,
        partition_manifest=artifacts.manifest,
        query_field="auto",
    )
    assert evidence["qualifying"] is False
    assert evidence["checks"]["partition_content_is_disjoint"] is False


def test_final_partition_can_require_relevance_labels(tmp_path: Path) -> None:
    fixture, corpus_manifest, rows = _source_fixture(tmp_path / "source")
    rows[0]["relevant_canonical_ids"] = []
    rows[1]["relevant_canonical_ids"] = []
    fixture.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )
    source_manifest = json.loads(corpus_manifest.read_text(encoding="utf-8"))
    source_manifest["artifacts"]["evaluation_fixtures"] = {
        "sha256": file_sha256(fixture),
        "records": len(rows),
    }
    corpus_manifest.write_text(
        json.dumps(source_manifest, sort_keys=True), encoding="utf-8"
    )
    args = _args(fixture, corpus_manifest, tmp_path / "partition")
    args.final_count = 3
    args.require_final_relevance_labels = True

    manifest, artifacts = split_evaluation_fixture.run(args)
    final_rows = load_records(artifacts.final)

    assert len(final_rows) == 3
    assert all(row["relevant_canonical_ids"] for row in final_rows)
    assert manifest["checks"]["final_relevance_labels_complete"] is True
