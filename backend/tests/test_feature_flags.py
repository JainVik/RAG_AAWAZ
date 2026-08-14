from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.domain.enums import ChunkStrategy
from app.domain.models import Chunk
from app.services import DefaultServices


def test_chunk_and_retrieval_flags_are_typed_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("RAG_ENABLE_ATOMIC_CHUNKS", "false")
    monkeypatch.setenv("RAG_ENABLE_SENTENCE_WINDOW_CHUNKS", "true")
    monkeypatch.setenv("RAG_ENABLE_SEMANTIC_CHUNKS", "false")
    monkeypatch.setenv("RAG_ENABLE_PARENT_CHILD_CHUNKS", "false")
    monkeypatch.setenv("RAG_ENABLE_BILINGUAL_PAIRED_CHUNKS", "false")
    monkeypatch.setenv("RAG_ENABLE_SPARSE", "false")
    monkeypatch.setenv("RAG_ENABLE_LATE_CHUNKING", "false")

    settings = Settings(_env_file=None)

    assert settings.enabled_chunk_strategies == (ChunkStrategy.SENTENCE_WINDOW,)
    assert settings.retrieval_feature_flags == {
        "atomic": False,
        "sentence_window": True,
        "semantic_section": False,
        "parent_child": False,
        "bilingual_paired": False,
        "sparse": False,
        "late_chunking": False,
    }


def test_at_least_one_dense_representation_must_be_enabled() -> None:
    with pytest.raises(ValidationError, match="At least one dense chunk representation"):
        Settings(
            _env_file=None,
            rag_enable_atomic_chunks=False,
            rag_enable_sentence_window_chunks=False,
            rag_enable_semantic_chunks=False,
            rag_enable_parent_child_chunks=False,
            rag_enable_bilingual_paired_chunks=False,
        )


def test_production_requires_shared_api_authentication() -> None:
    with pytest.raises(ValidationError, match="RAG_API_TOKEN"):
        Settings(_env_file=None, environment="production")

    settings = Settings(
        _env_file=None,
        environment="production",
        rag_api_token=SecretStr("secret"),
    )
    assert settings.api_token_value == "secret"
    assert settings.voice_api_token_value == "secret"


class _DenseFixture:
    dimension = 3

    def __init__(self, *_args: object, **_kwargs: object) -> None: ...

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def encode_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.3, 0.2, 0.1] for _ in texts]


class _DenseOnlyStoreFixture:
    observed_sparse_encoder: object = "not-constructed"

    def __init__(
        self,
        settings: Settings,
        dense_encoder: object,
        sparse_encoder: object,
        *,
        collection_metadata: Mapping[str, Any],
    ) -> None:
        del settings, dense_encoder, collection_metadata
        type(self).observed_sparse_encoder = sparse_encoder

    async def initialize(self) -> None: ...

    async def readiness_details(
        self,
        *,
        expected_points: int | None = None,
        require_green: bool = True,
    ) -> dict[str, Any]:
        del require_green
        return {
            "ready": True,
            "exact_points_count": expected_points,
            "schema_valid": True,
        }

    async def upsert_chunks(self, chunks: Sequence[Chunk], *, batch_size: int = 64) -> int:
        del batch_size
        return len(chunks)

    async def close(self) -> None: ...


@pytest.mark.asyncio
async def test_dense_only_services_do_not_require_sparse_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    (index_dir / "index-manifest.json").write_text(
        json.dumps(
            {
                "collection": "dense-only",
                "dense_model": "fixture-model",
                "model_revision": "fixture-revision",
                "chunk_build_id": "fixture-build",
                "corpus_manifest_sha256": "a" * 64,
                "point_count": 1,
                "sparse_vectors_built": False,
                "enabled_dense_strategies": [
                    strategy.value for strategy in ChunkStrategy
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.services.SentenceTransformerDenseEncoder", _DenseFixture)
    monkeypatch.setattr("app.services.QdrantStore", _DenseOnlyStoreFixture)
    settings = Settings(
        environment="test",
        rag_data_dir=tmp_path,
        rag_thresholds_path=tmp_path / "missing-thresholds.json",
        qdrant_collection="dense-only",
        rag_dense_model="fixture-model",
        rag_dense_model_revision="fixture-revision",
        dense_vector_size=3,
        rag_enable_sparse=False,
        rag_target_unique_passages=10,
        rag_development_passages=10,
    )

    services = DefaultServices(settings)
    await services.initialize()

    assert services.orchestrator is not None
    assert services._checks["index"]["ready"] is True
    assert _DenseOnlyStoreFixture.observed_sparse_encoder is None
    assert not services.sparse_state_path.exists()
