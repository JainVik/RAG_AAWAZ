from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


EvidenceStatus = Literal[
    "qualifying", "non_qualifying", "not_measured", "invalid", "partial", "smoke_audit"
]


class RetrievalEvidence(EvidenceModel):
    status: EvidenceStatus
    qualifying: bool
    sample_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    completion_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    recall_at_1: float | None = Field(default=None, ge=0.0, le=1.0)
    recall_at_5: float | None = Field(default=None, ge=0.0, le=1.0)
    recall_at_10: float | None = Field(default=None, ge=0.0, le=1.0)
    mrr_at_10: float | None = Field(default=None, ge=0.0, le=1.0)
    ndcg_at_10: float | None = Field(default=None, ge=0.0, le=1.0)
    retrieval_hit_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    split_verified: bool
    direct_latency_sample_count: int | None = Field(default=None, ge=0)
    direct_mean_ms: float | None = Field(default=None, ge=0.0)
    direct_p50_ms: float | None = Field(default=None, ge=0.0)
    direct_p70_ms: float | None = Field(default=None, ge=0.0)
    direct_p95_ms: float | None = Field(default=None, ge=0.0)
    direct_max_ms: float | None = Field(default=None, ge=0.0)
    source_artifact_sha256: str | None = None
    failed_checks: list[str] = Field(default_factory=list)


class CorpusEvidence(EvidenceModel):
    status: EvidenceStatus
    verified: bool
    dataset_id: str | None = None
    source_split: str | None = None
    language: str | None = None
    revision: str | None = None
    document_count: int | None = Field(default=None, ge=0)
    evaluation_fixture_count: int | None = Field(default=None, ge=0)
    indexed_chunks_count: int | None = Field(default=None, ge=0)
    dense_model: str | None = None
    dense_model_revision: str | None = None
    dense_dim: int | None = Field(default=None, ge=1)
    dense_distance: str | None = None
    sparse_model: str | None = None
    qdrant_collection: str | None = None
    index_build_id: str | None = None
    source_artifact_sha256: str | None = None
    index_manifest_sha256: str | None = None
    failed_checks: list[str] = Field(default_factory=list)


class ChunkRepresentationEvidence(EvidenceModel):
    strategy: str
    name: str
    description: str
    enabled: bool
    chunk_count: int = Field(ge=0)
    avg_text_length: float = Field(ge=0.0)
    artifact_bytes: int = Field(ge=0)
    build_duration_seconds: float = Field(ge=0.0)


class DatasetAuditEvidence(EvidenceModel):
    status: EvidenceStatus
    qualifying: bool
    dataset_id: str | None = None
    revision: str | None = None
    source_split: str | None = None
    target_language: str | None = None
    audited_row_count: int = Field(default=0, ge=0)
    candidate_passage_count: int = Field(default=0, ge=0)
    schema_match: bool | None = None
    malformed_row_count: int = Field(default=0, ge=0)
    duplicate_query_count: int = Field(default=0, ge=0)
    selected_passage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    query_type_distribution: dict[str, int] = Field(default_factory=dict)
    source_artifact_sha256: str | None = None
    failed_checks: list[str] = Field(default_factory=list)


class CorpusScalingEvidence(EvidenceModel):
    status: EvidenceStatus
    qualifying: bool
    baseline_document_count: int | None = Field(default=None, ge=0)
    baseline_chunk_count: int | None = Field(default=None, ge=0)
    scaling_comparison_status: str
    notes: str | None = None
    source_artifact_sha256: str | None = None
    failed_checks: list[str] = Field(default_factory=list)


class GuardrailEvidence(EvidenceModel):
    status: EvidenceStatus
    qualifying: bool
    sample_count: int = Field(ge=0)
    observed_correct_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    passed_categories: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    source_artifact_sha256: str | None = None


class VoiceLatencyEvidence(EvidenceModel):
    status: EvidenceStatus
    qualifying: bool
    sample_count: int = Field(ge=0)
    cold_p50_ms: float | None = Field(default=None, ge=0.0)
    cold_p70_ms: float | None = Field(default=None, ge=0.0)
    cold_p95_ms: float | None = Field(default=None, ge=0.0)
    cold_p100_ms: float | None = Field(default=None, ge=0.0)
    warm_p50_ms: float | None = Field(default=None, ge=0.0)
    warm_p70_ms: float | None = Field(default=None, ge=0.0)
    warm_p95_ms: float | None = Field(default=None, ge=0.0)
    warm_p100_ms: float | None = Field(default=None, ge=0.0)
    pending_criteria: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    source_artifact_sha256: str | None = None


class ProvenanceEvidence(EvidenceModel):
    evaluation_split: str | None = None
    manifest_verified: bool
    audit_trail_valid: bool
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class EvidenceSummary(EvidenceModel):
    schema_version: Literal["2.0.0"] = "2.0.0"
    generated_at: datetime
    retrieval: RetrievalEvidence
    corpus: CorpusEvidence
    chunk_representations: list[ChunkRepresentationEvidence]
    dataset_audit: DatasetAuditEvidence
    corpus_scaling: CorpusScalingEvidence
    guardrails: GuardrailEvidence
    voice_latency: VoiceLatencyEvidence
    provenance: ProvenanceEvidence


router = APIRouter(prefix="/v1/evidence", tags=["evidence"])

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = BACKEND_DIR / "evaluation" / "reports"
DATA_DIR = BACKEND_DIR / "data"


def _load_json(path: Path) -> tuple[dict[str, Any] | None, bool]:
    if not path.is_file():
        return None, False
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, True
    return (parsed, False) if isinstance(parsed, dict) else (None, True)


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as artifact:
            for block in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _integer(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value)
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        result = float(value)
        return result if math.isfinite(result) else None
    return None


def _boolean(value: Any) -> bool:
    return value is True


def _retrieval_evidence(path: Path) -> RetrievalEvidence:
    raw, invalid = _load_json(path)
    if raw is None:
        return RetrievalEvidence(
            status="invalid" if invalid else "not_measured",
            qualifying=False,
            sample_count=0,
            failure_count=0,
            split_verified=False,
            failed_checks=["retrieval_artifact_invalid" if invalid else "retrieval_not_measured"],
        )
    metadata = _mapping(raw.get("metadata"))
    qualification = _mapping(metadata.get("qualification_checks"))
    checks = _mapping(qualification.get("checks"))
    metrics = _mapping(_mapping(raw.get("metrics")).get("overall"))
    latency = _mapping(raw.get("latency"))
    qualifying = _boolean(qualification.get("qualifying")) and _boolean(metadata.get("qualifying"))
    failed_checks = [str(item) for item in _list(qualification.get("failed_checks"))]
    return RetrievalEvidence(
        status="qualifying" if qualifying else "non_qualifying",
        qualifying=qualifying,
        sample_count=_integer(qualification.get("successful_requests"))
        or _integer(metrics.get("query_count"))
        or 0,
        failure_count=_integer(raw.get("failure_count")) or 0,
        completion_coverage=_number(raw.get("retrieval_completion_coverage")),
        recall_at_1=_number(metrics.get("recall_at_1")),
        recall_at_5=_number(metrics.get("recall_at_5")),
        recall_at_10=_number(metrics.get("recall_at_10")),
        mrr_at_10=_number(metrics.get("mrr_at_10")),
        ndcg_at_10=_number(metrics.get("ndcg_at_10")),
        retrieval_hit_coverage=_number(raw.get("retrieval_hit_coverage")),
        split_verified=_boolean(checks.get("verified_held_out_provenance")),
        direct_latency_sample_count=_integer(latency.get("sample_count")),
        direct_mean_ms=_number(latency.get("mean_ms")),
        direct_p50_ms=_number(latency.get("p50_ms")),
        direct_p70_ms=_number(latency.get("p70_ms")),
        direct_p95_ms=_number(latency.get("p95_ms")),
        direct_max_ms=_number(latency.get("p100_ms")),
        source_artifact_sha256=_sha256(path),
        failed_checks=failed_checks,
    )


def _corpus_evidence(corpus_path: Path, index_path: Path) -> CorpusEvidence:
    corpus, corpus_invalid = _load_json(corpus_path)
    index, index_invalid = _load_json(index_path)
    if corpus is None or index is None:
        invalid = corpus_invalid or index_invalid
        return CorpusEvidence(
            status="invalid" if invalid else "not_measured",
            verified=False,
            failed_checks=[
                "corpus_or_index_manifest_invalid" if invalid else "corpus_or_index_missing"
            ],
        )
    dataset = _mapping(corpus.get("dataset"))
    artifacts = _mapping(corpus.get("artifacts"))
    fixtures = _mapping(artifacts.get("evaluation_fixtures"))
    vectors = _mapping(index.get("vectors"))
    dense = _mapping(vectors.get("dense"))
    sparse = _mapping(vectors.get("sparse"))
    corpus_sha = _sha256(corpus_path)
    expected_corpus_sha = _string(index.get("corpus_manifest_sha256"))
    verified = corpus_sha is not None and corpus_sha == expected_corpus_sha
    return CorpusEvidence(
        status="qualifying" if verified else "invalid",
        verified=verified,
        dataset_id=_string(dataset.get("id")),
        source_split=_string(dataset.get("split")),
        language=_string(dataset.get("language")),
        revision=_string(dataset.get("revision")),
        document_count=_integer(index.get("document_count")),
        evaluation_fixture_count=_integer(fixtures.get("records")),
        indexed_chunks_count=_integer(index.get("point_count")),
        dense_model=_string(index.get("dense_model")),
        dense_model_revision=_string(index.get("model_revision")),
        dense_dim=_integer(dense.get("size")) or _integer(index.get("dense_vector_size")),
        dense_distance=_string(dense.get("distance")),
        sparse_model=_string(sparse.get("algorithm")),
        qdrant_collection=_string(index.get("collection")),
        index_build_id=_string(index.get("chunk_build_id")),
        source_artifact_sha256=corpus_sha,
        index_manifest_sha256=_sha256(index_path),
        failed_checks=[] if verified else ["index_corpus_manifest_hash_mismatch"],
    )


_STRATEGY_DESCRIPTIONS = {
    "atomic": "Complete source passages indexed as the smallest canonical representation.",
    "sentence_window": "Bounded sentence windows retaining nearby context.",
    "semantic_section": "Meaningful sentence groups split at measured semantic transitions.",
    "parent_child": "Fine-grained child retrieval with canonical parent evidence returned.",
    "bilingual_paired": "Bounded aligned translated and English evidence windows.",
}


def _chunk_representations(index_path: Path) -> list[ChunkRepresentationEvidence]:
    index, _invalid = _load_json(index_path)
    if index is None:
        return []
    strategies = _mapping(index.get("strategies"))
    result: list[ChunkRepresentationEvidence] = []
    for strategy in _STRATEGY_DESCRIPTIONS:
        data = _mapping(strategies.get(strategy))
        if not data:
            continue
        result.append(
            ChunkRepresentationEvidence(
                strategy=strategy,
                name=strategy.replace("_", " ").title(),
                description=_STRATEGY_DESCRIPTIONS[strategy],
                enabled=_boolean(data.get("enabled")),
                chunk_count=_integer(data.get("count")) or 0,
                avg_text_length=_number(data.get("average_text_characters")) or 0.0,
                artifact_bytes=_integer(data.get("artifact_bytes")) or 0,
                build_duration_seconds=_number(data.get("build_duration_seconds")) or 0.0,
            )
        )
    return result


def _dataset_audit(path: Path) -> DatasetAuditEvidence:
    raw, invalid = _load_json(path)
    reports = _list(raw.get("reports")) if raw is not None else []
    report = _mapping(reports[0]) if reports else {}
    if not report:
        return DatasetAuditEvidence(
            status="invalid" if invalid else "not_measured",
            qualifying=False,
            failed_checks=["dataset_audit_invalid" if invalid else "dataset_audit_not_measured"],
        )
    dataset = _mapping(report.get("dataset"))
    sampling = _mapping(report.get("sampling"))
    schema = _mapping(report.get("schema"))
    passages = _mapping(report.get("passage_counts"))
    queries = _mapping(report.get("query_counts"))
    malformed = _mapping(report.get("malformed"))
    query_types = {
        str(key): int(value)
        for key, value in _mapping(queries.get("query_type_distribution")).items()
        if isinstance(value, int) and not isinstance(value, bool)
    }
    return DatasetAuditEvidence(
        status="smoke_audit",
        qualifying=False,
        dataset_id=_string(dataset.get("id")),
        revision=_string(dataset.get("revision")),
        source_split=_string(dataset.get("split")),
        target_language=_string(dataset.get("language")),
        audited_row_count=_integer(sampling.get("rows_sampled")) or 0,
        candidate_passage_count=_integer(passages.get("aligned_candidate_positions")) or 0,
        schema_match=schema.get("matches") if isinstance(schema.get("matches"), bool) else None,
        malformed_row_count=_integer(malformed.get("examples_recorded")) or 0,
        duplicate_query_count=_integer(queries.get("duplicate_query_id_rows")) or 0,
        selected_passage_ratio=_number(passages.get("selected_ratio")),
        query_type_distribution=query_types,
        source_artifact_sha256=_sha256(path),
        failed_checks=["bounded_sample_not_full_dataset_certification"],
    )


def _guardrail_evidence(path: Path) -> GuardrailEvidence:
    raw, invalid = _load_json(path)
    if raw is None:
        return GuardrailEvidence(
            status="invalid" if invalid else "not_measured",
            qualifying=False,
            sample_count=0,
            observed_correct_count=0,
            failure_count=0,
            failed_checks=["guardrail_artifact_invalid" if invalid else "guardrail_not_measured"],
        )
    metrics = _mapping(raw.get("metrics"))
    qualification = _mapping(raw.get("qualification"))
    confusion = _mapping(metrics.get("confusion"))
    qualifying = _boolean(qualification.get("qualifying"))
    count = _integer(metrics.get("case_count")) or 0
    correct = _integer(metrics.get("correct")) or 0
    return GuardrailEvidence(
        status="qualifying" if qualifying else "non_qualifying",
        qualifying=qualifying,
        sample_count=count,
        observed_correct_count=correct,
        failure_count=max(0, count - correct),
        passed_categories=sorted(str(key) for key in confusion),
        failed_checks=[str(item) for item in _list(qualification.get("failed_checks"))],
        source_artifact_sha256=_sha256(path),
    )


def _voice_latency(path: Path) -> VoiceLatencyEvidence:
    raw, invalid = _load_json(path)
    pending = [
        "At least 100 distinct measured voice cases with the required language and "
        "condition slices",
        "Credentialed Sarvam evidence with transcript-match and verified-response coverage",
        "Separate compatible cold and warm runs with canonical timing coverage",
        "Zero request failures in the qualifying measured denominator",
    ]
    if raw is None:
        return VoiceLatencyEvidence(
            status="invalid" if invalid else "not_measured",
            qualifying=False,
            sample_count=0,
            pending_criteria=pending,
            failed_checks=["voice_latency_invalid" if invalid else "voice_latency_not_measured"],
        )
    qualification = _mapping(raw.get("qualification"))
    summary = _mapping(raw.get("summary"))
    qualifying = _boolean(qualification.get("qualifying"))
    return VoiceLatencyEvidence(
        status="qualifying" if qualifying else "non_qualifying",
        qualifying=qualifying,
        sample_count=_integer(summary.get("sample_count")) or 0,
        pending_criteria=[] if qualifying else pending,
        failed_checks=[str(item) for item in _list(qualification.get("failed_checks"))],
        source_artifact_sha256=_sha256(path),
    )


def build_evidence_summary() -> EvidenceSummary:
    retrieval_path = REPORTS_DIR / "final" / "retrieval-eval.json"
    corpus_manifest_path = DATA_DIR / "corpus" / "corpus-manifest.json"
    index_manifest_path = DATA_DIR / "index" / "index-manifest.json"
    audit_path = REPORTS_DIR / "dataset-audit.json"
    guardrail_path = REPORTS_DIR / "final" / "guardrail-eval.json"
    voice_path = REPORTS_DIR / "final" / "voice-latency.json"
    retrieval = _retrieval_evidence(retrieval_path)
    corpus = _corpus_evidence(corpus_manifest_path, index_manifest_path)
    dataset_audit = _dataset_audit(audit_path)
    guardrails = _guardrail_evidence(guardrail_path)
    voice_latency = _voice_latency(voice_path)
    retrieval_raw, _retrieval_invalid = _load_json(retrieval_path)
    held_out = (
        _mapping(_mapping(retrieval_raw.get("metadata")).get("held_out_provenance"))
        if retrieval_raw
        else {}
    )
    evaluation_split = _string(_mapping(held_out.get("fixture_artifact")).get("split"))
    artifact_paths = {
        "retrieval-eval.json": retrieval_path,
        "corpus-manifest.json": corpus_manifest_path,
        "index-manifest.json": index_manifest_path,
        "dataset-audit.json": audit_path,
        "guardrail-eval.json": guardrail_path,
        "voice-latency.json": voice_path,
    }
    artifact_hashes = {
        name: digest
        for name, path in artifact_paths.items()
        if (digest := _sha256(path)) is not None
    }
    return EvidenceSummary(
        generated_at=datetime.now(UTC),
        retrieval=retrieval,
        corpus=corpus,
        chunk_representations=_chunk_representations(index_manifest_path),
        dataset_audit=dataset_audit,
        corpus_scaling=CorpusScalingEvidence(
            status="not_measured",
            qualifying=False,
            baseline_document_count=corpus.document_count,
            baseline_chunk_count=corpus.indexed_chunks_count,
            scaling_comparison_status="Corpus-size recommendation pending",
            notes=(
                "Only the current independently built baseline is available; no multi-collection "
                "qualifying comparison artifact exists."
            ),
            failed_checks=["multiple_qualifying_corpus_sizes_not_available"],
        ),
        guardrails=guardrails,
        voice_latency=voice_latency,
        provenance=ProvenanceEvidence(
            evaluation_split=evaluation_split,
            manifest_verified=corpus.verified,
            audit_trail_valid=corpus.verified
            and retrieval.status == "qualifying"
            and dataset_audit.status == "smoke_audit"
            and guardrails.status != "invalid"
            and all(
                artifact_hashes.get(name) is not None
                for name in (
                    "retrieval-eval.json",
                    "corpus-manifest.json",
                    "index-manifest.json",
                    "dataset-audit.json",
                    "guardrail-eval.json",
                )
            ),
            artifact_hashes=artifact_hashes,
            limitations=[],
        ),
    )


@router.get("/summary", response_model=EvidenceSummary)
async def evidence_summary() -> EvidenceSummary:
    return build_evidence_summary()
