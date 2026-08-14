from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.domain.enums import ChunkStrategy
from app.domain.models import Chunk
from app.embeddings.sparse_char_ngram import SparseCharNgramEncoder
from app.retrieval.qdrant_store import QdrantStoreError
from scripts.build_index import (
    CHECKPOINT_FILENAME,
    CHUNKS_FILENAME,
    INDEX_MANIFEST_FILENAME,
    SPARSE_STATE_FILENAME,
    IndexArtifactError,
    IndexBuildConfig,
    IndexPrerequisiteError,
    build_index,
)


class FakeDenseEncoder:
    dimension = 3
    model_revision = "fixture-revision"

    def __init__(self) -> None:
        self.sentence_calls: list[list[str]] = []

    def encode_sentences(self, texts: list[str]) -> list[list[float]]:
        self.sentence_calls.append(list(texts))
        return [
            [1.0, 0.0, 0.0] if index < 2 else [0.0, 1.0, 0.0] for index, _text in enumerate(texts)
        ]

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def encode_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.3, 0.2, 0.1] for _ in texts]


class FakeStore:
    def __init__(
        self,
        persisted: set[str],
        *,
        fail_on_call: int | None = None,
        initialize_error: Exception | None = None,
    ) -> None:
        self.persisted = persisted
        self.fail_on_call = fail_on_call
        self.initialize_error = initialize_error
        self.upsert_calls: list[list[Chunk]] = []
        self.upsert_attempts = 0
        self.initialize_calls = 0
        self.closed = False

    async def initialize(self) -> None:
        self.initialize_calls += 1
        if self.initialize_error is not None:
            raise self.initialize_error

    async def upsert_chunks(self, chunks: Sequence[Chunk], *, batch_size: int = 64) -> int:
        assert batch_size == len(chunks)
        self.upsert_attempts += 1
        if self.upsert_attempts == self.fail_on_call:
            raise RuntimeError("simulated interrupted Qdrant upsert")
        copied = list(chunks)
        self.upsert_calls.append(copied)
        self.persisted.update(chunk.chunk_id for chunk in copied)
        return len(copied)

    async def readiness_details(
        self,
        *,
        expected_points: int | None = None,
        require_green: bool = True,
    ) -> dict[str, Any]:
        del require_green
        count = len(self.persisted)
        return {
            "ready": expected_points == count,
            "exact_points_count": count,
            "schema_valid": True,
        }

    async def close(self) -> None:
        self.closed = True


def _settings(data_dir: Path, **updates: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "rag_data_dir": data_dir,
        "qdrant_collection": "fixture_chunks",
        "rag_dense_model": "intfloat/multilingual-e5-small",
        "dense_vector_size": 3,
        "rag_target_unique_passages": 10,
        "rag_development_passages": 10,
    }
    values.update(updates)
    return Settings(**values)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_corpus(root: Path, *, extra: Mapping[str, object] | None = None) -> Path:
    corpus_dir = root / "corpus"
    corpus_dir.mkdir(parents=True)
    rows: list[dict[str, object]] = [
        {
            "canonical_doc_id": "short-doc",
            "parent_id": "short-doc",
            "english_text": "Brief factual passage.",
        },
        {
            "canonical_doc_id": "long-doc",
            "parent_id": "long-doc",
            "english_text": (
                "First useful sentence covers Goa. "
                "Second related sentence adds historical context. "
                "Third different sentence discusses coastal geography. "
                "Fourth final sentence explains regional tourism."
            ),
            "translated_text": (
                "Pahala upayogi vakya Goa batata hai. "
                "Dusara sambandhit vakya itihas jodata hai. "
                "Tisara alag vakya bhugol batata hai. "
                "Chautha antim vakya paryatan samjhata hai."
            ),
            "translation_language": "hin_Deva",
            "translation_model": "fixture-translator",
        },
    ]
    if extra:
        rows[0].update(extra)
    corpus_path = corpus_dir / "corpus.jsonl"
    corpus_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "artifacts": {
            "corpus": {
                "filename": "corpus.jsonl",
                "sha256": _sha256(corpus_path),
                "bytes": corpus_path.stat().st_size,
                "records": len(rows),
            }
        }
    }
    (corpus_dir / "corpus-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )
    return corpus_path


def _factory_for(store: FakeStore, captured: dict[str, Any]):
    def factory(
        settings: Settings,
        dense_encoder: FakeDenseEncoder,
        sparse_encoder: SparseCharNgramEncoder | None,
        metadata: Mapping[str, Any],
    ) -> FakeStore:
        captured.update(
            {
                "settings": settings,
                "dense_encoder": dense_encoder,
                "sparse_encoder": sparse_encoder,
                "metadata": dict(metadata),
            }
        )
        return store

    return factory


def _read_chunks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _contains_prohibited_key(value: Any) -> bool:
    prohibited = {"query", "query_id", "answer", "answers", "label", "labels"}
    if isinstance(value, dict):
        return any(
            str(key).casefold() in prohibited or _contains_prohibited_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_prohibited_key(child) for child in value)
    return False


@pytest.mark.asyncio
async def test_builds_deterministic_complete_artifacts_and_manifest(tmp_path) -> None:
    corpus = _write_corpus(tmp_path)
    settings = _settings(tmp_path)
    first_encoder = FakeDenseEncoder()
    first_store = FakeStore(set())
    captured: dict[str, Any] = {}
    first_config = IndexBuildConfig(
        settings=settings,
        corpus_path=corpus,
        output_dir=tmp_path / "index-first",
        batch_size=3,
    )

    first = await build_index(
        first_config,
        dense_encoder=first_encoder,
        store_factory=_factory_for(first_store, captured),
    )

    chunks = _read_chunks(first.chunks_path)
    strategies = {chunk["strategy"] for chunk in chunks}
    assert strategies == {strategy.value for strategy in ChunkStrategy}
    assert all(len(call) >= 4 for call in first_encoder.sentence_calls)
    assert len(first_encoder.sentence_calls) == 2
    assert not any(_contains_prohibited_key(chunk) for chunk in chunks)
    assert first.manifest["point_count"] == len(chunks)
    assert first.manifest["chunk_count"] == len(chunks)
    assert first.manifest["collection"] == "fixture_chunks"
    assert first.manifest["dense_model"] == "intfloat/multilingual-e5-small"
    assert first.manifest["dense_vector_name"] == "dense"
    assert first.manifest["sparse_vector_name"] == "char_ngrams"
    assert set(first.manifest["strategy_counts"]) == {strategy.value for strategy in ChunkStrategy}
    assert set(first.manifest["strategy_average_lengths"]) == {
        strategy.value for strategy in ChunkStrategy
    }
    assert first.manifest["build_time_seconds"] >= 0
    assert first.sparse_state_path is not None
    assert first.manifest["disk_bytes"] == (
        first.chunks_path.stat().st_size + first.sparse_state_path.stat().st_size
    )
    assert first.manifest["checksums"]["chunks"] == _sha256(first.chunks_path)
    assert first.manifest["checksums"]["sparse_encoder"] == _sha256(first.sparse_state_path)
    assert "qdrant-client" in first.manifest["package_versions"]
    assert "sentence-transformers" in first.manifest["package_versions"]
    sparse = SparseCharNgramEncoder.load(first.sparse_state_path)
    assert sparse.document_count == len(chunks)
    assert captured["metadata"] == {
        "corpus_manifest_sha256": first.manifest["corpus_manifest_sha256"],
        "chunk_build_id": first.manifest["chunk_build_id"],
    }
    assert first_store.closed
    assert not (first_config.output_dir / CHECKPOINT_FILENAME).exists()

    second_config = IndexBuildConfig(
        settings=settings,
        corpus_path=corpus,
        output_dir=tmp_path / "index-second",
        batch_size=5,
    )
    second = await build_index(
        second_config,
        dense_encoder=FakeDenseEncoder(),
        store_factory=_factory_for(FakeStore(set()), {}),
    )
    assert first.chunks_path.read_bytes() == second.chunks_path.read_bytes()


@pytest.mark.asyncio
async def test_no_semantic_skips_sentence_embeddings(tmp_path) -> None:
    corpus = _write_corpus(tmp_path)
    encoder = FakeDenseEncoder()
    store = FakeStore(set())
    config = IndexBuildConfig(
        settings=_settings(tmp_path),
        corpus_path=corpus,
        output_dir=tmp_path / "index",
        enable_semantic=False,
    )

    result = await build_index(
        config,
        dense_encoder=encoder,
        store_factory=_factory_for(store, {}),
    )

    assert encoder.sentence_calls == []
    assert all(
        chunk["strategy"] != ChunkStrategy.SEMANTIC_SECTION.value
        for chunk in _read_chunks(result.chunks_path)
    )
    semantic = result.manifest["strategies"][ChunkStrategy.SEMANTIC_SECTION.value]
    assert semantic["enabled"] is False
    assert semantic["count"] == 0


@pytest.mark.asyncio
async def test_independent_strategy_flags_change_artifact_and_manifest(tmp_path) -> None:
    corpus = _write_corpus(tmp_path)
    encoder = FakeDenseEncoder()
    settings = _settings(
        tmp_path,
        rag_enable_sentence_window_chunks=False,
        rag_enable_semantic_chunks=False,
        rag_enable_parent_child_chunks=False,
        rag_enable_bilingual_paired_chunks=False,
        rag_enable_sparse=False,
        rag_enable_late_chunking=False,
    )
    config = IndexBuildConfig(
        settings=settings,
        corpus_path=corpus,
        output_dir=tmp_path / "index",
    )
    captured: dict[str, Any] = {}

    result = await build_index(
        config,
        dense_encoder=encoder,
        store_factory=_factory_for(FakeStore(set()), captured),
    )

    chunks = _read_chunks(result.chunks_path)
    assert {chunk["strategy"] for chunk in chunks} == {ChunkStrategy.ATOMIC.value}
    assert encoder.sentence_calls == []
    assert result.manifest["enabled_dense_strategies"] == [ChunkStrategy.ATOMIC.value]
    assert result.manifest["feature_flags"] == {
        "atomic": True,
        "sentence_window": False,
        "semantic_section": False,
        "parent_child": False,
        "bilingual_paired": False,
        "sparse": False,
        "late_chunking": False,
    }
    assert result.sparse_state_path is None
    assert not config.sparse_state_path.exists()
    assert captured["sparse_encoder"] is None
    assert result.manifest["sparse_vectors_built"] is False
    assert "sparse_vector_name" not in result.manifest
    assert "sparse_encoder" not in result.manifest["artifacts"]
    assert "sparse_encoder" not in result.manifest["checksums"]
    assert "sparse" not in result.manifest["vectors"]
    assert result.manifest["disk_bytes"] == result.chunks_path.stat().st_size
    assert all(
        details["enabled"] == (name == ChunkStrategy.ATOMIC.value)
        for name, details in result.manifest["strategies"].items()
    )


def test_no_semantic_cli_compatibility_cannot_disable_last_dense_strategy(
    tmp_path,
) -> None:
    semantic_only = _settings(
        tmp_path,
        rag_enable_atomic_chunks=False,
        rag_enable_sentence_window_chunks=False,
        rag_enable_semantic_chunks=True,
        rag_enable_parent_child_chunks=False,
        rag_enable_bilingual_paired_chunks=False,
    )

    with pytest.raises(ValueError, match="at least one dense chunk strategy"):
        IndexBuildConfig(
            settings=semantic_only,
            corpus_path=tmp_path / "corpus.jsonl",
            output_dir=tmp_path / "index",
            enable_semantic=False,
        )


@pytest.mark.asyncio
async def test_interrupted_upsert_resumes_after_last_complete_batch(tmp_path) -> None:
    corpus = _write_corpus(tmp_path)
    config = IndexBuildConfig(
        settings=_settings(tmp_path),
        corpus_path=corpus,
        output_dir=tmp_path / "index",
        batch_size=2,
    )
    persisted: set[str] = set()
    interrupted = FakeStore(persisted, fail_on_call=2)

    with pytest.raises(RuntimeError, match="simulated interrupted"):
        await build_index(
            config,
            dense_encoder=FakeDenseEncoder(),
            store_factory=_factory_for(interrupted, {}),
        )

    checkpoint_path = config.output_dir / CHECKPOINT_FILENAME
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["next_chunk_index"] == 2
    assert len(persisted) == 2
    assert interrupted.closed
    all_chunk_ids = [chunk["chunk_id"] for chunk in _read_chunks(config.chunks_path)]

    resumed_store = FakeStore(persisted)
    resumed = await build_index(
        config,
        dense_encoder=FakeDenseEncoder(),
        store_factory=_factory_for(resumed_store, {}),
    )

    resumed_ids = [chunk.chunk_id for batch in resumed_store.upsert_calls for chunk in batch]
    assert resumed_ids == all_chunk_ids[2:]
    assert len(persisted) == len(all_chunk_ids)
    assert resumed.manifest["point_count"] == len(all_chunk_ids)
    assert not checkpoint_path.exists()


@pytest.mark.asyncio
async def test_existing_complete_build_is_idempotently_reused(tmp_path) -> None:
    corpus = _write_corpus(tmp_path)
    config = IndexBuildConfig(
        settings=_settings(tmp_path),
        corpus_path=corpus,
        output_dir=tmp_path / "index",
        batch_size=4,
    )
    persisted: set[str] = set()
    first_store = FakeStore(persisted)
    first = await build_index(
        config,
        dense_encoder=FakeDenseEncoder(),
        store_factory=_factory_for(first_store, {}),
    )
    chunk_bytes = first.chunks_path.read_bytes()

    second_store = FakeStore(persisted)
    second = await build_index(
        config,
        dense_encoder=FakeDenseEncoder(),
        store_factory=_factory_for(second_store, {}),
    )

    assert second.reused_existing is True
    assert second.manifest == first.manifest
    assert second_store.upsert_calls == []
    assert second.chunks_path.read_bytes() == chunk_bytes
    assert second_store.closed


@pytest.mark.asyncio
async def test_incompatible_collection_failure_is_not_recreated_or_hidden(tmp_path) -> None:
    corpus = _write_corpus(tmp_path)
    error = QdrantStoreError(
        "Existing Qdrant collection is incompatible; refusing destructive recreation",
        operation="validate_collection_schema",
        collection="fixture_chunks",
        retryable=False,
    )
    store = FakeStore(set(), initialize_error=error)
    config = IndexBuildConfig(
        settings=_settings(tmp_path),
        corpus_path=corpus,
        output_dir=tmp_path / "index",
    )

    with pytest.raises(QdrantStoreError, match="incompatible"):
        await build_index(
            config,
            dense_encoder=FakeDenseEncoder(),
            store_factory=_factory_for(store, {}),
        )

    assert store.upsert_calls == []
    assert store.closed
    assert not (config.output_dir / INDEX_MANIFEST_FILENAME).exists()
    assert (config.output_dir / CHECKPOINT_FILENAME).exists()


@pytest.mark.asyncio
async def test_rejects_missing_or_evaluation_contaminated_corpus(tmp_path) -> None:
    missing_config = IndexBuildConfig(
        settings=_settings(tmp_path),
        corpus_path=tmp_path / "missing" / "corpus.jsonl",
        output_dir=tmp_path / "index-missing",
    )
    with pytest.raises(IndexPrerequisiteError, match="Run build_corpus first"):
        await build_index(missing_config, dense_encoder=FakeDenseEncoder())

    corpus = _write_corpus(tmp_path / "contaminated", extra={"query": "leaked query"})
    contaminated_config = IndexBuildConfig(
        settings=_settings(tmp_path),
        corpus_path=corpus,
        output_dir=tmp_path / "index-contaminated",
    )
    with pytest.raises(IndexArtifactError, match="Evaluation-only field 'query'"):
        await build_index(
            contaminated_config,
            dense_encoder=FakeDenseEncoder(),
            store_factory=_factory_for(FakeStore(set()), {}),
        )

    assert not (contaminated_config.output_dir / CHUNKS_FILENAME).exists()
    assert not (contaminated_config.output_dir / SPARSE_STATE_FILENAME).exists()
    assert not (contaminated_config.output_dir / INDEX_MANIFEST_FILENAME).exists()
