from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.enums import ChunkStrategy
from app.services import DefaultServices


def _settings(root: Path, *, sparse: bool) -> Settings:
    return Settings(
        environment="test",
        rag_data_dir=root,
        rag_thresholds_path=root / "missing-thresholds.json",
        qdrant_collection="fixture-collection",
        rag_dense_model="fixture-model",
        rag_dense_model_revision="fixture-revision",
        dense_vector_size=3,
        rag_enable_sparse=sparse,
        rag_enable_sentence_window_chunks=False,
        rag_enable_semantic_chunks=False,
        rag_enable_parent_child_chunks=False,
        rag_enable_bilingual_paired_chunks=False,
        rag_target_unique_passages=10,
        rag_development_passages=10,
    )


def _write_manifest(root: Path, **updates: object) -> dict[str, object]:
    index_dir = root / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "collection": "fixture-collection",
        "dense_model": "fixture-model",
        "model_revision": "fixture-revision",
        "chunk_build_id": "fixture-build",
        "corpus_manifest_sha256": "a" * 64,
        "point_count": 1,
        "sparse_vectors_built": False,
        "enabled_dense_strategies": [ChunkStrategy.ATOMIC.value],
        "checksums": {},
    }
    manifest.update(updates)
    (index_dir / "index-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return manifest


@pytest.mark.asyncio
async def test_sparse_encoder_checksum_tamper_fails_before_deserialization(
    tmp_path: Path,
) -> None:
    sparse_path = tmp_path / "index" / "sparse-encoder.json"
    sparse_path.parent.mkdir(parents=True)
    sparse_path.write_text('{"tampered":true}', encoding="utf-8")
    _write_manifest(
        tmp_path,
        sparse_vectors_built=True,
        checksums={"sparse_encoder": "f" * 64},
    )

    services = DefaultServices(_settings(tmp_path, sparse=True))
    await services.initialize()

    check = services._checks["index"]
    assert check["ready"] is False
    assert check["reason"] == "sparse_encoder_checksum_mismatch"
    assert check["observed_sha256"] == hashlib.sha256(
        sparse_path.read_bytes()
    ).hexdigest()
    assert services.orchestrator is None


@pytest.mark.asyncio
async def test_runtime_dense_strategy_must_have_been_built(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        enabled_dense_strategies=[ChunkStrategy.SENTENCE_WINDOW.value],
    )

    services = DefaultServices(_settings(tmp_path, sparse=False))
    await services.initialize()

    check = services._checks["index"]
    assert check["ready"] is False
    assert check["reason"] == "dense_strategy_not_built"
    assert check["missing_strategies"] == [ChunkStrategy.ATOMIC.value]
    assert services.orchestrator is None
