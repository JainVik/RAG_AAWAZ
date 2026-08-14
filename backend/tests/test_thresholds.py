from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.evaluation.thresholds import (
    FrozenThresholds,
    RetrievalArtifactBinding,
    freeze_development_thresholds,
    load_frozen_thresholds,
    query_content_sha256,
    query_ids_sha256,
    retrieval_runtime_contract_sha256,
)
from app.retrieval.router import TIDE_ROUTER_CONTRACT_VERSION
from app.services import DefaultServices


def _threshold_values() -> dict[str, object]:
    query_ids = ("q1",)
    content_hashes = (query_content_sha256("query one"),)
    return {
        "development_fixture_sha256": "a" * 64,
        "development_query_ids": query_ids,
        "development_query_count": len(query_ids),
        "development_query_ids_sha256": query_ids_sha256(query_ids),
        "development_query_content_hashes": content_hashes,
        "development_query_content_count": len(content_hashes),
        "development_query_content_hashes_sha256": query_ids_sha256(
            content_hashes
        ),
        "frozen_at": datetime.now(UTC),
        "minimum_answer_score": 0.2,
        "minimum_score_margin": 0.01,
        "minimum_evidence_agreement": 0.1,
    }


def test_thresholds_are_frozen_before_final_evaluation(tmp_path: Path) -> None:
    fixture = tmp_path / "development.jsonl"
    fixture.write_text(
        '{"query_id":"q1","query":"query one"}\n', encoding="utf-8"
    )
    output = tmp_path / "thresholds.json"

    frozen = freeze_development_thresholds(
        output,
        fixture,
        minimum_answer_score=0.2,
        minimum_score_margin=0.01,
        minimum_evidence_agreement=0.1,
    )
    loaded = load_frozen_thresholds(output)
    assert loaded == frozen
    assert loaded.source_split == "development"


def test_final_split_cannot_be_used_to_freeze_thresholds(tmp_path: Path) -> None:
    fixture = tmp_path / "final.jsonl"
    fixture.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="development"):
        freeze_development_thresholds(
            tmp_path / "thresholds.json",
            fixture,
            minimum_answer_score=0.2,
            minimum_score_margin=0.01,
            minimum_evidence_agreement=0.1,
            source_split="final",
        )


def test_runtime_rejects_mismatched_or_schema_v1_threshold_binding(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    index_dir = data_dir / "index"
    index_dir.mkdir(parents=True)
    index_path = index_dir / "index-manifest.json"
    index = {
        "collection": "chunks",
        "corpus_manifest_sha256": "a" * 64,
        "chunk_build_id": "c" * 64,
        "dense_model": "model",
        "model_revision": "revision",
        "checksums": {"corpus": "b" * 64},
    }
    index_path.write_text(json.dumps(index), encoding="utf-8")
    development = tmp_path / "development.jsonl"
    development.write_text(
        '{"query_id":"development","query":"development query"}\n',
        encoding="utf-8",
    )
    threshold_path = tmp_path / "frozen.json"
    settings = Settings(
        rag_data_dir=data_dir,
        rag_thresholds_path=threshold_path,
        qdrant_collection="chunks",
        rag_dense_model="model",
        rag_dense_model_revision="revision",
    )

    mismatch = RetrievalArtifactBinding(
        index_manifest_sha256="f" * 64,
        corpus_manifest_sha256="a" * 64,
        corpus_artifact_sha256="b" * 64,
        chunk_build_id="c" * 64,
        collection="chunks",
        dense_model="model",
        model_revision="revision",
        retrieval_contract_version=TIDE_ROUTER_CONTRACT_VERSION,
        retrieval_contract_sha256=retrieval_runtime_contract_sha256(settings),
    )
    frozen = freeze_development_thresholds(
        threshold_path,
        development,
        minimum_answer_score=0.2,
        minimum_score_margin=0.01,
        minimum_evidence_agreement=0.1,
        retrieval_artifacts=mismatch,
    )
    services = DefaultServices(settings)
    assert services._configure_thresholds(index_manifest=index) is False
    assert services._checks["thresholds"]["ready"] is False
    assert "index_manifest_sha256_mismatch" in services._checks["thresholds"][
        "binding_errors"
    ]

    threshold_path.write_text(
        frozen.model_copy(update={"schema_version": 1}).model_dump_json(),
        encoding="utf-8",
    )
    assert services._configure_thresholds(index_manifest=index) is False
    assert services._checks["thresholds"]["binding_errors"] == [
        "schema_version_must_be_3"
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("minimum_answer_score", math.nan),
        ("minimum_answer_score", math.inf),
        ("minimum_answer_score", -math.inf),
        ("minimum_answer_score", 1.0001),
        ("minimum_answer_score", -1.0001),
        ("minimum_score_margin", math.nan),
        ("minimum_score_margin", math.inf),
        ("minimum_score_margin", -0.0001),
        ("minimum_evidence_agreement", math.nan),
        ("minimum_evidence_agreement", math.inf),
        ("minimum_evidence_agreement", 1.0001),
    ],
)
def test_frozen_thresholds_reject_nonfinite_or_out_of_range_values(
    field: str, value: float
) -> None:
    values = _threshold_values()
    values[field] = value
    with pytest.raises(ValidationError):
        FrozenThresholds.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("development_fixture_sha256", "not-a-sha256"),
        ("frozen_at", "2026-01-01T00:00:00"),
        ("frozen_at", "2026-01-01T05:30:00+05:30"),
    ],
)
def test_frozen_thresholds_require_sha256_and_utc_aware_timestamp(
    field: str, value: str
) -> None:
    values = _threshold_values()
    values["frozen_at"] = "2026-01-01T00:00:00Z"
    values[field] = value
    with pytest.raises(ValidationError):
        FrozenThresholds.model_validate(values)


def test_binding_sha_fields_and_corrupt_json_numbers_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        RetrievalArtifactBinding(index_manifest_sha256="bad")
    with pytest.raises(ValidationError):
        RetrievalArtifactBinding(chunk_build_id="not-a-build-sha256")

    artifact = tmp_path / "corrupt-thresholds.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "status": "frozen",
                "source_split": "development",
                "score_kind": "raw_dense_similarity",
                "score_contract_version": "raw-dense-similarity-v1",
                "development_fixture_sha256": "a" * 64,
                "frozen_at": "2026-01-01T00:00:00Z",
                "minimum_answer_score": math.nan,
                "minimum_score_margin": 0.01,
                "minimum_evidence_agreement": 0.1,
                "retrieval_artifacts": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_frozen_thresholds(artifact)


def test_service_rejects_corrupt_threshold_without_mutating_settings(
    tmp_path: Path,
) -> None:
    threshold_path = tmp_path / "corrupt-thresholds.json"
    threshold_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "status": "frozen",
                "source_split": "development",
                "score_kind": "raw_dense_similarity",
                "score_contract_version": "raw-dense-similarity-v1",
                "development_fixture_sha256": "a" * 64,
                "frozen_at": "2026-01-01T00:00:00Z",
                "minimum_answer_score": math.inf,
                "minimum_score_margin": 0.01,
                "minimum_evidence_agreement": 0.1,
                "retrieval_artifacts": None,
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(rag_thresholds_path=threshold_path, min_answer_score=0.3)
    services = DefaultServices(settings)

    assert services._configure_thresholds(index_manifest={}) is False
    assert services.settings.min_answer_score == 0.3
    assert services._checks["thresholds"]["reason"] == "invalid_frozen_thresholds"


def test_service_reconstructs_settings_through_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    index_dir = data_dir / "index"
    index_dir.mkdir(parents=True)
    index_path = index_dir / "index-manifest.json"
    index = {
        "collection": "chunks",
        "corpus_manifest_sha256": "a" * 64,
        "chunk_build_id": "c" * 64,
        "dense_model": "model",
        "model_revision": "revision",
        "checksums": {"corpus": "b" * 64},
    }
    index_path.write_text(json.dumps(index), encoding="utf-8")
    fixture = tmp_path / "development.jsonl"
    fixture.write_text(
        '{"query_id":"development","query":"development query"}\n',
        encoding="utf-8",
    )
    threshold_path = tmp_path / "frozen.json"
    settings = Settings(
        rag_data_dir=data_dir,
        rag_thresholds_path=threshold_path,
        qdrant_collection="chunks",
        rag_dense_model="model",
        rag_dense_model_revision="revision",
    )
    freeze_development_thresholds(
        threshold_path,
        fixture,
        minimum_answer_score=0.25,
        minimum_score_margin=0.02,
        minimum_evidence_agreement=0.15,
        retrieval_artifacts=RetrievalArtifactBinding(
            index_manifest_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
            corpus_manifest_sha256="a" * 64,
            corpus_artifact_sha256="b" * 64,
            chunk_build_id="c" * 64,
            collection="chunks",
            dense_model="model",
            model_revision="revision",
            retrieval_contract_version=TIDE_ROUTER_CONTRACT_VERSION,
            retrieval_contract_sha256=retrieval_runtime_contract_sha256(settings),
        ),
    )
    services = DefaultServices(settings)
    original_validate = Settings.model_validate
    validated: list[object] = []

    def validating_spy(value: object) -> Settings:
        validated.append(value)
        return original_validate(value)

    monkeypatch.setattr(Settings, "model_validate", validating_spy)

    assert services._configure_thresholds(index_manifest=index) is True
    assert validated
    assert services.settings.min_answer_score == 0.25
