from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.domain.enums import ChunkStrategy, Language
from app.evaluation.thresholds import (
    RetrievalArtifactBinding,
    freeze_development_thresholds,
    retrieval_runtime_contract_sha256,
)
from app.retrieval.router import TIDE_ROUTER_CONTRACT_VERSION
from scripts import (
    calibrate_thresholds,
    run_ablation,
    run_guardrail_eval,
    score_development,
)
from scripts._common import (
    EvaluationError,
    corpus_index_provenance,
    evaluation_qualification,
    final_threshold_provenance,
    held_out_provenance,
    raw_dense_score_evidence,
    select_query_and_field,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _calibration_binding() -> dict[str, str]:
    return {
        "index_manifest_sha256": "1" * 64,
        "corpus_manifest_sha256": "2" * 64,
        "corpus_artifact_sha256": "3" * 64,
        "chunk_build_id": "4" * 64,
        "collection": "calibration-index",
        "dense_model": "model",
        "model_revision": "revision",
        "retrieval_contract_version": TIDE_ROUTER_CONTRACT_VERSION,
        "retrieval_contract_sha256": "5" * 64,
    }


def test_calibration_grid_preserves_mandatory_guardrail_anchors() -> None:
    values = [index / 100 for index in range(100)]
    grid = calibrate_thresholds._grid(values, 16, anchors=(0.05, 1.0))

    assert len(grid) <= 16
    assert 0.05 in grid
    assert 1.0 in grid


def _fixture_and_manifest(
    root: Path, *, split: str = "validation"
) -> tuple[Path, Path, list[dict[str, object]]]:
    root.mkdir(parents=True, exist_ok=True)
    fixture = root / "evaluation-fixtures.jsonl"
    rows: list[dict[str, object]] = [
        {
            "query_id": "q1",
            "english_query": "Where is Goa?",
            "translated_query": "गोवा कहाँ है?",
            "relevant_canonical_ids": ["d1"],
            "language": "hi",
            "split": split,
        },
        {
            "query_id": "q2",
            "english_query": "When was Goa formed?",
            "translated_query": "गोवा कब बना?",
            "relevant_canonical_ids": ["d2"],
            "language": "hi",
            "split": split,
        },
    ]
    fixture.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest = root / "corpus-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "artifact_version": 1,
                "dataset": {
                    "id": "fixture/dataset",
                    "revision": "fixed-revision",
                    "language": "hi",
                    "split": split,
                },
                "artifacts": {
                    "corpus": {"sha256": "a" * 64},
                    "evaluation_fixtures": {
                        "sha256": _sha256(fixture),
                        "records": len(rows),
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return fixture, manifest, rows


def _index_manifest(provenance: dict[str, object]) -> dict[str, object]:
    return {
        "collection": "chunks-final",
        "corpus_manifest_sha256": provenance["manifest_sha256"],
        "chunk_build_id": "c" * 64,
        "dense_model": "model",
        "model_revision": "revision",
        "checksums": {
            "corpus": provenance["corpus_artifact_sha256"],
            "chunks": "b" * 64,
        },
    }


def test_hindi_auto_query_prefers_translation_but_english_is_supported() -> None:
    row = {
        "language": "hi",
        "translated_query": "हिंदी प्रश्न",
        "english_query": "English question",
        "query": "legacy question",
    }
    assert select_query_and_field(row, row=1) == ("हिंदी प्रश्न", "translated_query")
    assert select_query_and_field(row, row=1, preferred="english_query") == (
        "English question",
        "english_query",
    )


def test_held_out_provenance_requires_manifest_hash_count_and_validation_split(
    tmp_path: Path,
) -> None:
    fixture, manifest, rows = _fixture_and_manifest(tmp_path)
    evidence = held_out_provenance(fixture, rows, corpus_manifest=manifest)
    assert evidence["qualifying"] is True
    assert evidence["status"] == "verified_held_out"

    train_fixture, train_manifest, train_rows = _fixture_and_manifest(
        tmp_path / "train", split="train"
    )
    train = held_out_provenance(train_fixture, train_rows, corpus_manifest=train_manifest)
    assert train["qualifying"] is False
    assert train["checks"]["manifest_split_is_held_out"] is False


def test_corpus_index_mismatch_is_rejected(tmp_path: Path) -> None:
    fixture, manifest, rows = _fixture_and_manifest(tmp_path)
    provenance = held_out_provenance(fixture, rows, corpus_manifest=manifest)
    index_path = tmp_path / "index-manifest.json"
    index_path.write_text("{}", encoding="utf-8")
    index = _index_manifest(provenance)
    index["corpus_manifest_sha256"] = "f" * 64
    with pytest.raises(EvaluationError, match="active index"):
        corpus_index_provenance(
            provenance,
            index_manifest_path=index_path,
            index_manifest=index,
        )


def test_qualification_requires_full_success_not_only_enough_rows() -> None:
    decision = evaluation_qualification(
        size_qualification="qualifying",
        provenance={"qualifying": True},
        index_provenance={"qualifying": True},
        thresholds={"qualifying": True},
        expected_requests=500,
        recorded_requests=500,
        successful_requests=499,
        request_failures=1,
        configuration_failures=0,
    )
    assert decision["qualifying"] is False
    assert decision["checks"]["full_retrieval_coverage"] is False
    assert decision["checks"]["zero_request_failures"] is False


def test_final_thresholds_are_bound_and_development_fixture_cannot_be_reused(
    tmp_path: Path,
) -> None:
    final_fixture, manifest, rows = _fixture_and_manifest(tmp_path)
    provenance = held_out_provenance(final_fixture, rows, corpus_manifest=manifest)
    index_path = tmp_path / "index-manifest.json"
    index = _index_manifest(provenance)
    index_path.write_text(json.dumps(index), encoding="utf-8")
    development_fixture = tmp_path / "development.jsonl"
    development_fixture.write_text(
        '{"query_id":"development","query":"development query"}\n',
        encoding="utf-8",
    )
    thresholds_path = tmp_path / "frozen-thresholds.json"
    settings = Settings(
        rag_thresholds_path=thresholds_path,
        qdrant_collection="chunks-final",
        rag_dense_model="model",
        rag_dense_model_revision="revision",
    )
    index_checksums = index["checksums"]
    assert isinstance(index_checksums, dict)
    binding = RetrievalArtifactBinding(
        index_manifest_sha256=_sha256(index_path),
        corpus_manifest_sha256=str(index["corpus_manifest_sha256"]),
        corpus_artifact_sha256=str(index_checksums["corpus"]),
        chunk_build_id="c" * 64,
        collection="chunks-final",
        dense_model="model",
        model_revision="revision",
        retrieval_contract_version=TIDE_ROUTER_CONTRACT_VERSION,
        retrieval_contract_sha256=retrieval_runtime_contract_sha256(settings),
    )
    freeze_development_thresholds(
        thresholds_path,
        development_fixture,
        minimum_answer_score=0.2,
        minimum_score_margin=0.01,
        minimum_evidence_agreement=0.1,
        retrieval_artifacts=binding,
    )
    services = SimpleNamespace(settings=settings)
    evidence = final_threshold_provenance(
        services,
        final_fixture_sha256=_sha256(final_fixture),
        final_query_ids=[str(row["query_id"]) for row in rows],
        final_queries=[str(row["translated_query"]) for row in rows],
        index_manifest_path=index_path,
        index_manifest=index,
    )
    assert evidence["qualifying"] is True

    reused_path = tmp_path / "reused-thresholds.json"
    freeze_development_thresholds(
        reused_path,
        final_fixture,
        minimum_answer_score=0.2,
        minimum_score_margin=0.01,
        minimum_evidence_agreement=0.1,
        retrieval_artifacts=binding,
    )
    services.settings.rag_thresholds_path = reused_path
    with pytest.raises(EvaluationError, match="identical"):
        final_threshold_provenance(
            services,
            final_fixture_sha256=_sha256(final_fixture),
            final_query_ids=[str(row["query_id"]) for row in rows],
            final_queries=[str(row["translated_query"]) for row in rows],
            index_manifest_path=index_path,
            index_manifest=index,
        )

    overlapping_id_fixture = tmp_path / "overlapping-id-development.jsonl"
    overlapping_id_fixture.write_text(
        '{"query_id":"q1","query":"different development text"}\n',
        encoding="utf-8",
    )
    freeze_development_thresholds(
        reused_path,
        overlapping_id_fixture,
        minimum_answer_score=0.2,
        minimum_score_margin=0.01,
        minimum_evidence_agreement=0.1,
        retrieval_artifacts=binding,
    )
    with pytest.raises(EvaluationError, match="query IDs overlap"):
        final_threshold_provenance(
            services,
            final_fixture_sha256=_sha256(final_fixture),
            final_query_ids=[str(row["query_id"]) for row in rows],
            final_queries=[str(row["translated_query"]) for row in rows],
            index_manifest_path=index_path,
            index_manifest=index,
        )

    overlapping_content_fixture = tmp_path / "overlapping-content-development.jsonl"
    overlapping_content_fixture.write_text(
        json.dumps(
            {
                "query_id": "development-only",
                "query": rows[0]["translated_query"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    freeze_development_thresholds(
        reused_path,
        overlapping_content_fixture,
        minimum_answer_score=0.2,
        minimum_score_margin=0.01,
        minimum_evidence_agreement=0.1,
        retrieval_artifacts=binding,
    )
    with pytest.raises(EvaluationError, match="normalized query content"):
        final_threshold_provenance(
            services,
            final_fixture_sha256=_sha256(final_fixture),
            final_query_ids=[str(row["query_id"]) for row in rows],
            final_queries=[str(row["translated_query"]) for row in rows],
            index_manifest_path=index_path,
            index_manifest=index,
        )


def test_calibration_default_matches_runtime_threshold_setting() -> None:
    args = calibrate_thresholds.build_parser().parse_args(["--fixture", "development.jsonl"])
    assert args.frozen_output == calibrate_thresholds._runtime_threshold_path()
    assert args.frozen_output.as_posix().endswith("data/calibration/frozen-thresholds.json")


def test_calibration_accepts_only_versioned_raw_dense_scores() -> None:
    rows = [
        {
            "query_id": f"q{index}",
            "query": f"query {index}",
            "split": "development",
            "is_answerable": bool(index),
            "top_raw_dense_similarity": 0.8 if index else 0.1,
            "raw_dense_similarity_margin": 0.2,
            "evidence_agreement": 0.5,
            "score_kind": "raw_dense_similarity",
            "score_contract_version": "raw-dense-similarity-v1",
            "retrieval_artifacts": _calibration_binding(),
        }
        for index in range(2)
    ]
    prepared = calibrate_thresholds._prepare(rows)
    assert prepared[1]["top_raw_dense_similarity"] == 0.8

    ambiguous = [dict(row) for row in rows]
    ambiguous[0].pop("top_raw_dense_similarity")
    ambiguous[0]["top_score"] = 0.1
    with pytest.raises(EvaluationError, match="top_raw_dense_similarity"):
        calibrate_thresholds._prepare(ambiguous)

    missing_binding = [dict(row) for row in rows]
    missing_binding[0].pop("retrieval_artifacts")
    with pytest.raises(EvaluationError, match="requires retrieval_artifacts"):
        calibrate_thresholds._prepare(missing_binding)

    mismatched_binding = [dict(row) for row in rows]
    mismatched_binding[1]["retrieval_artifacts"] = {
        **_calibration_binding(),
        "collection": "different-index",
    }
    with pytest.raises(EvaluationError, match="differs from earlier"):
        calibrate_thresholds._prepare(mismatched_binding)


def test_calibration_scored_binding_must_match_active_binding() -> None:
    records = [
        {
            "query_id": "q1",
            "retrieval_artifacts": _calibration_binding(),
        }
    ]
    active = RetrievalArtifactBinding.model_validate(_calibration_binding())
    assert calibrate_thresholds._require_active_retrieval_binding(records, active) == active

    mismatched = active.model_copy(update={"collection": "different-index"})
    with pytest.raises(EvaluationError, match="active retrieval artifact"):
        calibrate_thresholds._require_active_retrieval_binding(records, mismatched)
    with pytest.raises(EvaluationError, match="requires existing"):
        calibrate_thresholds._require_active_retrieval_binding(records, None)


def test_development_score_export_requires_explicit_split_and_both_labels() -> None:
    rows = [
        {
            "query_id": "answerable",
            "query": "Where is Goa?",
            "split": "development",
            "is_answerable": True,
        },
        {
            "query_id": "unanswerable",
            "query": "What is Goa's live price?",
            "split": "development",
            "is_answerable": False,
        },
    ]
    prepared = score_development._prepare(rows, query_field="auto")
    assert {row["is_answerable"] for row in prepared} == {False, True}

    wrong_split = [dict(row) for row in rows]
    wrong_split[0]["split"] = "validation"
    with pytest.raises(EvaluationError, match="development split"):
        score_development._prepare(wrong_split, query_field="auto")

    with pytest.raises(EvaluationError, match="both answerable"):
        score_development._prepare(rows[:1], query_field="auto")


def test_bundled_unanswerable_fixture_completes_partitioned_development_input(
    tmp_path: Path,
) -> None:
    answerable_fixture = tmp_path / "development-fixtures.jsonl"
    answerable_fixture.write_text(
        json.dumps(
            {
                "query_id": "answerable-from-partition",
                "query": "Where is Goa?",
                "split": "development",
                "is_answerable": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    records = score_development._load_scoring_records(
        answerable_fixture,
        score_development.DEFAULT_UNANSWERABLE_FIXTURE,
    )
    prepared = score_development._prepare(records, query_field="auto")

    assert {row["is_answerable"] for row in prepared} == {False, True}
    assert sum(row["is_answerable"] is False for row in prepared) == 12


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("top_raw_dense_similarity", float("nan")),
        ("top_raw_dense_similarity", float("inf")),
        ("top_raw_dense_similarity", 1.01),
        ("top_raw_dense_similarity", -1.01),
        ("raw_dense_similarity_margin", float("nan")),
        ("raw_dense_similarity_margin", float("inf")),
        ("raw_dense_similarity_margin", -0.01),
        ("evidence_agreement", float("nan")),
        ("evidence_agreement", float("inf")),
        ("evidence_agreement", 1.01),
    ],
)
def test_calibration_rejects_nonfinite_and_out_of_range_scores(field: str, value: float) -> None:
    rows = [
        {
            "query_id": f"q{index}",
            "query": f"query {index}",
            "split": "development",
            "is_answerable": bool(index),
            "top_raw_dense_similarity": 0.8 if index else 0.1,
            "raw_dense_similarity_margin": 0.2,
            "evidence_agreement": 0.5,
            "score_kind": "raw_dense_similarity",
            "score_contract_version": "raw-dense-similarity-v1",
            "retrieval_artifacts": _calibration_binding(),
        }
        for index in range(2)
    ]
    rows[0][field] = value
    with pytest.raises(EvaluationError):
        calibrate_thresholds._prepare(rows)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 1.01, -1.01])
def test_calibration_validates_second_raw_dense_similarity(value: float) -> None:
    rows = [
        {
            "query_id": f"q{index}",
            "query": f"query {index}",
            "split": "development",
            "is_answerable": bool(index),
            "top_raw_dense_similarity": 0.8 if index else 0.1,
            "second_raw_dense_similarity": 0.0,
            "evidence_agreement": 0.5,
            "score_kind": "raw_dense_similarity",
            "score_contract_version": "raw-dense-similarity-v1",
            "retrieval_artifacts": _calibration_binding(),
        }
        for index in range(2)
    ]
    rows[0]["second_raw_dense_similarity"] = value
    with pytest.raises(EvaluationError):
        calibrate_thresholds._prepare(rows)


def test_raw_dense_export_does_not_relabel_fused_scores() -> None:
    hits = [
        SimpleNamespace(score=1.0, dense_score=0.3),
        SimpleNamespace(score=0.9, dense_score=0.2),
    ]
    evidence = raw_dense_score_evidence(hits)
    assert evidence["top_raw_dense_similarity"] == pytest.approx(0.3)
    assert evidence["raw_dense_similarity_margin"] == pytest.approx(0.1)
    assert evidence["score_kind"] == "raw_dense_similarity"


def test_ablation_shared_footprint_is_not_labeled_as_qdrant_size() -> None:
    configuration = next(
        item for item in run_ablation.CONFIGURATIONS if item.name == "atomic_dense_hindi"
    )
    manifest = {
        "strategies": {strategy.value: {"enabled": True} for strategy in ChunkStrategy},
        "artifacts": {"sparse_encoder": {"bytes": 19}},
    }
    footprint = {
        (ChunkStrategy.ATOMIC.value, Language.ENGLISH.value): {
            "count": 3,
            "jsonl_bytes": 30,
        },
        (ChunkStrategy.ATOMIC.value, Language.HINDI.value): {
            "count": 2,
            "jsonl_bytes": 24,
        },
    }
    artifacts = run_ablation._configuration_artifacts(configuration, manifest, footprint, None)
    assert artifacts["selected_chunk_count"] == 2
    assert artifacts["selected_chunk_jsonl_bytes"] == 24
    assert artifacts["separate_qdrant_build"]["qdrant_index_bytes"] is None
    assert "shared_index_disk_bytes" not in artifacts
    assert "strategy_build_time_seconds" not in artifacts


def test_guardrail_qualification_rejects_synthetic_only_live_evidence() -> None:
    records = [
        {"case_id": f"case-{index}", "expected": label}
        for index, label in enumerate(sorted(run_guardrail_eval.REQUIRED_EXPECTED_LABELS))
    ]
    records.append(
        {
            "case_id": "contradiction",
            "kind": "contradictory_pipeline",
            "expected": "RETRIEVAL_DISAGREEMENT",
        }
    )
    rows = [
        {
            "case_id": record["case_id"],
            "correct": True,
            "evidence": (
                {"evidence_mode": "harness_evidence_conflict_gate"}
                if record.get("kind") == "contradictory_pipeline"
                else {}
            ),
        }
        for record in records
    ]
    readiness = {
        "index": {"ready": True},
        "qdrant": {"ready": True},
        "thresholds": {"ready": True, "retrieval_artifacts_bound": True},
    }

    live = run_guardrail_eval._qualification_evidence(
        records, rows, offline=False, readiness_checks=readiness
    )
    offline = run_guardrail_eval._qualification_evidence(
        records, rows, offline=True, readiness_checks=readiness
    )
    failed = run_guardrail_eval._qualification_evidence(
        records,
        [{**row, "correct": False} if index == 0 else row for index, row in enumerate(rows)],
        offline=False,
        readiness_checks=readiness,
    )

    assert live["qualifying"] is False
    assert live["checks"]["synthetic_conflict_gate_regression"] is True
    assert live["checks"]["active_pipeline_supported_case"] is False
    assert live["checks"]["active_pipeline_unsupported_case"] is False
    assert live["checks"]["active_pipeline_contradictory_case"] is False
    assert offline["qualifying"] is False
    assert failed["qualifying"] is False
    assert failed["checks"]["all_cases_correct"] is False
