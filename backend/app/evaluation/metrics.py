from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.telemetry.recorder import nearest_rank_percentile


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationRecord:
    query_id: str
    relevant_ids: frozenset[str]
    retrieved_ids: tuple[str, ...]
    language: str = "unknown"
    category: str = "unknown"


def _recall(record: RetrievalEvaluationRecord, k: int) -> float:
    if not record.relevant_ids:
        return 0.0
    found = record.relevant_ids.intersection(record.retrieved_ids[:k])
    return len(found) / len(record.relevant_ids)


def _reciprocal_rank(record: RetrievalEvaluationRecord, k: int = 10) -> float:
    for rank, document_id in enumerate(record.retrieved_ids[:k], start=1):
        if document_id in record.relevant_ids:
            return 1.0 / rank
    return 0.0


def _ndcg(record: RetrievalEvaluationRecord, k: int = 10) -> float:
    gains = [
        1.0 / math.log2(rank + 1)
        for rank, document_id in enumerate(record.retrieved_ids[:k], start=1)
        if document_id in record.relevant_ids
    ]
    dcg = sum(gains)
    ideal_count = min(k, len(record.relevant_ids))
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / ideal if ideal else 0.0


def retrieval_metrics(records: Sequence[RetrievalEvaluationRecord]) -> dict[str, float | int]:
    if not records:
        return {
            "query_count": 0,
            "answerable_query_count": 0,
            "recall_at_1": 0.0,
            "recall_at_5": 0.0,
            "recall_at_10": 0.0,
            "mrr_at_10": 0.0,
            "ndcg_at_10": 0.0,
        }
    divisor = len(records)
    return {
        "query_count": divisor,
        "answerable_query_count": sum(bool(record.relevant_ids) for record in records),
        "recall_at_1": sum(_recall(record, 1) for record in records) / divisor,
        "recall_at_5": sum(_recall(record, 5) for record in records) / divisor,
        "recall_at_10": sum(_recall(record, 10) for record in records) / divisor,
        "mrr_at_10": sum(_reciprocal_rank(record) for record in records) / divisor,
        "ndcg_at_10": sum(_ndcg(record) for record in records) / divisor,
    }


def grouped_retrieval_metrics(
    records: Sequence[RetrievalEvaluationRecord],
) -> dict[str, Any]:
    languages: defaultdict[str, list[RetrievalEvaluationRecord]] = defaultdict(list)
    categories: defaultdict[str, list[RetrievalEvaluationRecord]] = defaultdict(list)
    for record in records:
        languages[record.language].append(record)
        categories[record.category].append(record)
    return {
        "overall": retrieval_metrics(records),
        "by_language": {
            key: retrieval_metrics(value) for key, value in sorted(languages.items())
        },
        "by_category": {
            key: retrieval_metrics(value) for key, value in sorted(categories.items())
        },
    }


def latency_metrics(
    durations_ms: Sequence[float], *, total_requests: int, completed_answers: int
) -> dict[str, float | int]:
    if not durations_ms:
        return {
            "request_count": total_requests,
            "sample_count": 0,
            "completed_answer_count": completed_answers,
            "answer_coverage": completed_answers / total_requests if total_requests else 0.0,
        }
    return {
        "request_count": total_requests,
        "sample_count": len(durations_ms),
        "completed_answer_count": completed_answers,
        "answer_coverage": completed_answers / total_requests if total_requests else 0.0,
        "p50_ms": nearest_rank_percentile(durations_ms, 50),
        "p70_ms": nearest_rank_percentile(durations_ms, 70),
        "p95_ms": nearest_rank_percentile(durations_ms, 95),
        "p100_ms": max(durations_ms),
        "mean_ms": sum(durations_ms) / len(durations_ms),
    }


def guardrail_confusion_counts(
    expected: Iterable[str], observed: Iterable[str]
) -> dict[str, Any]:
    matrix: defaultdict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
    count = 0
    correct = 0
    for expected_reason, observed_reason in zip(expected, observed, strict=True):
        count += 1
        matrix[expected_reason][observed_reason] += 1
        correct += expected_reason == observed_reason
    return {
        "case_count": count,
        "correct": correct,
        "accuracy": correct / count if count else 0.0,
        "confusion": {
            expected_key: dict(sorted(row.items()))
            for expected_key, row in sorted(matrix.items())
        },
    }


def freeze_thresholds(
    path: str,
    thresholds: Mapping[str, float],
    *,
    development_fixture_hash: str,
) -> dict[str, Any]:
    """Return the canonical payload written by calibration tooling before final evaluation."""

    return {
        "schema_version": 1,
        "status": "frozen",
        "development_fixture_hash": development_fixture_hash,
        "thresholds": dict(sorted(thresholds.items())),
        "path": path,
    }

