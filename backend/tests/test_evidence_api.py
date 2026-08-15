from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api import evidence


def test_repository_evidence_summary_is_artifact_backed() -> None:
    if not (evidence.DATA_DIR / "index" / "index-manifest.json").is_file():
        pytest.skip("repository evidence artifacts are intentionally not committed")
    summary = evidence.build_evidence_summary()
    retrieval_artifact = json.loads(
        (evidence.REPORTS_DIR / "final" / "retrieval-eval.json").read_text(
            encoding="utf-8"
        )
    )
    metadata = retrieval_artifact["metadata"]
    expected_qualifying = bool(
        metadata.get("qualifying")
        and metadata.get("qualification_checks", {}).get("qualifying")
    )

    assert summary.schema_version == "2.0.0"
    assert summary.retrieval.sample_count == 500
    assert summary.retrieval.qualifying is expected_qualifying
    if metadata.get("evaluation_interpretation") == "post_hoc_regression_confirmation":
        assert summary.retrieval.qualifying is False
        assert "fresh_untouched_final_evaluation" in summary.retrieval.failed_checks
    assert summary.retrieval.recall_at_10 is not None
    assert summary.retrieval.source_artifact_sha256
    assert summary.corpus.document_count == 10_005
    assert summary.corpus.indexed_chunks_count == 112_114
    assert summary.corpus.verified is True
    assert summary.dataset_audit.audited_row_count == 20
    assert summary.corpus_scaling.status == "not_measured"
    assert summary.voice_latency.status == "not_measured"


def test_missing_artifacts_remain_explicitly_not_measured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # This endpoint must never replace missing evidence with demonstration numbers.
    monkeypatch.setattr(evidence, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(evidence, "DATA_DIR", tmp_path / "data")

    summary = evidence.build_evidence_summary()

    assert summary.retrieval.status == "not_measured"
    assert summary.retrieval.recall_at_10 is None
    assert summary.corpus.document_count is None
    assert summary.guardrails.sample_count == 0
    assert summary.provenance.audit_trail_valid is False


def test_invalid_artifact_is_reported_without_server_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reports = tmp_path / "reports"
    final = reports / "final"
    final.mkdir(parents=True)
    (final / "retrieval-eval.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(evidence, "REPORTS_DIR", reports)
    monkeypatch.setattr(evidence, "DATA_DIR", tmp_path / "data")

    summary = evidence.build_evidence_summary()
    payload = json.loads(summary.model_dump_json())

    assert payload["retrieval"]["status"] == "invalid"
    assert payload["retrieval"]["qualifying"] is False
