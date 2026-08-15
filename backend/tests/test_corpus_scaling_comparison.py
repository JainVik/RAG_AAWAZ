from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts._common import EvaluationError
from scripts.compare_corpus_sizes import compare_reports


def _report(
    path: Path,
    *,
    documents: int,
    recall: float,
    p95_ms: float,
    collection: str,
    corpus_hash: str,
    fixture_hash: str = "f" * 64,
    qualifying: bool = True,
) -> Path:
    payload = {
        "metadata": {
            "command": "run_retrieval_eval",
            "qualifying": qualifying,
            "qualification": "qualifying" if qualifying else "non_qualifying_fixture",
            "fixture": {"sha256": fixture_hash},
            "query_field": "auto",
            "deadline_ms": 5000,
            "cache_policy": "warm",
            "concurrency": 1,
            "corpus": {
                "available": True,
                "document_count": documents,
                "point_count": documents * 4,
                "disk_bytes": documents * 1000,
                "build_time_seconds": documents / 10,
                "collection": collection,
                "corpus_manifest_sha256": corpus_hash,
            },
            "frozen_thresholds": {
                "retrieval_artifacts": {
                    "dense_model": "intfloat/multilingual-e5-small",
                    "model_revision": "revision",
                    "retrieval_contract_version": "router-v1",
                    "retrieval_contract_sha256": "r" * 64,
                }
            },
        },
        "metrics": {
            "overall": {
                "recall_at_1": recall - 0.2,
                "recall_at_5": recall - 0.05,
                "recall_at_10": recall,
                "mrr_at_10": recall - 0.25,
                "ndcg_at_10": recall - 0.15,
            }
        },
        "latency": {
            "mean_ms": p95_ms - 10,
            "p50_ms": p95_ms - 20,
            "p95_ms": p95_ms,
            "p100_ms": p95_ms + 10,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_comparison_selects_smaller_candidate_when_gain_is_not_material(
    tmp_path: Path,
) -> None:
    small = _report(
        tmp_path / "10k.json",
        documents=10_000,
        recall=0.80,
        p95_ms=100,
        collection="corpus-10k",
        corpus_hash="1" * 64,
    )
    medium = _report(
        tmp_path / "25k.json",
        documents=25_000,
        recall=0.805,
        p95_ms=130,
        collection="corpus-25k",
        corpus_hash="2" * 64,
    )

    summary = compare_reports([medium, small], minimum_recall_gain=0.01)

    assert summary["qualification"]["qualifying"] is True
    assert summary["recommendation"] == {
        "document_count": 10_000,
        "reason": "next_candidate_recall_gain_not_material",
        "provisional": False,
    }
    assert summary["marginal_changes"][0]["artifact_disk_bytes_delta"] == 15_000_000


def test_nonqualifying_source_makes_recommendation_provisional(tmp_path: Path) -> None:
    first = _report(
        tmp_path / "first.json",
        documents=10,
        recall=0.5,
        p95_ms=10,
        collection="first",
        corpus_hash="1" * 64,
        qualifying=False,
    )
    second = _report(
        tmp_path / "second.json",
        documents=20,
        recall=0.7,
        p95_ms=20,
        collection="second",
        corpus_hash="2" * 64,
    )

    summary = compare_reports([first, second], minimum_recall_gain=0.01)

    assert summary["qualification"]["qualifying"] is False
    assert summary["recommendation"]["provisional"] is True


def test_comparison_rejects_different_held_out_fixtures(tmp_path: Path) -> None:
    first = _report(
        tmp_path / "first.json",
        documents=10,
        recall=0.5,
        p95_ms=10,
        collection="first",
        corpus_hash="1" * 64,
    )
    second = _report(
        tmp_path / "second.json",
        documents=20,
        recall=0.7,
        p95_ms=20,
        collection="second",
        corpus_hash="2" * 64,
        fixture_hash="a" * 64,
    )

    with pytest.raises(EvaluationError, match="not comparable"):
        compare_reports([first, second], minimum_recall_gain=0.01)
