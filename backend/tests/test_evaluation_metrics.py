from __future__ import annotations

from app.evaluation.metrics import (
    RetrievalEvaluationRecord,
    grouped_retrieval_metrics,
    guardrail_confusion_counts,
    latency_metrics,
)


def test_retrieval_metrics_use_held_out_relevance_ids() -> None:
    records = [
        RetrievalEvaluationRecord(
            query_id="q1",
            relevant_ids=frozenset({"d1"}),
            retrieved_ids=("d1", "d2"),
            language="hi",
            category="factual",
        ),
        RetrievalEvaluationRecord(
            query_id="q2",
            relevant_ids=frozenset({"d3"}),
            retrieved_ids=("d4", "d3"),
            language="en",
            category="factual",
        ),
    ]
    report = grouped_retrieval_metrics(records)
    assert report["overall"]["recall_at_1"] == 0.5
    assert report["overall"]["mrr_at_10"] == 0.75
    assert set(report["by_language"]) == {"en", "hi"}


def test_latency_report_keeps_outlier_as_p100_and_reports_coverage() -> None:
    report = latency_metrics([10.0, 11.0, 250.0], total_requests=4, completed_answers=3)
    assert report["p100_ms"] == 250.0
    assert report["answer_coverage"] == 0.75


def test_guardrail_confusion_matrix_keeps_distinct_reasons() -> None:
    report = guardrail_confusion_counts(
        ["STALE_CORPUS", "UNSAFE_REQUEST"], ["STALE_CORPUS", "NO_RELEVANT_EVIDENCE"]
    )
    assert report["correct"] == 1
    assert report["confusion"]["UNSAFE_REQUEST"]["NO_RELEVANT_EVIDENCE"] == 1

