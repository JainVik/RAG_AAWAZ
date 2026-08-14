from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings, get_settings  # noqa: E402
from app.domain.enums import ChunkStrategy  # noqa: E402
from app.domain.models import Chunk, CorpusDocument  # noqa: E402
from app.embeddings.sparse_char_ngram import SparseCharNgramEncoder  # noqa: E402
from app.ingestion.chunk_factory import ChunkFactory  # noqa: E402
from app.ingestion.corpus_writer import CORPUS_PAYLOAD_FIELDS  # noqa: E402
from app.ingestion.loader import PROHIBITED_INDEX_KEYS  # noqa: E402
from app.retrieval.qdrant_store import QdrantStore  # noqa: E402

INDEX_ARTIFACT_VERSION = 2
CHUNKS_FILENAME = "chunks.jsonl"
SPARSE_STATE_FILENAME = "sparse-encoder.json"
INDEX_MANIFEST_FILENAME = "index-manifest.json"
CHECKPOINT_FILENAME = ".index-build.checkpoint.json"
CHUNK_ALGORITHM_VERSION = "chunk-factory-v2"
SPARSE_ALGORITHM_VERSION = "char-ngram-tfidf-v1"
CHUNK_PARAMETERS: dict[str, int | float] = {
    "sentence_window_size": 3,
    "sentence_overlap": 1,
    "semantic_min_sentences": 4,
    "semantic_break_quantile": 0.35,
    "semantic_max_words": 180,
    "bilingual_max_characters": 800,
}
SPARSE_DIMENSIONS = 1 << 20
SPARSE_MIN_N = 3
SPARSE_MAX_N = 5

_PROHIBITED_ARTIFACT_KEYS = PROHIBITED_INDEX_KEYS | {
    "labels",
    "query_id",
    "ground_truth",
}
_PACKAGE_NAMES = (
    "awaaz-tiderag",
    "numpy",
    "pydantic",
    "qdrant-client",
    "sentence-transformers",
)


class IndexBuildError(RuntimeError):
    """An index could not be built without violating its safety contract."""


class IndexPrerequisiteError(IndexBuildError):
    """A required local artifact, package, model, or service is unavailable."""


class IndexArtifactError(IndexBuildError):
    """An input or resumable artifact is malformed or incompatible."""


class BuildDenseEncoder(Protocol):
    dimension: int

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def encode_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def encode_sentences(self, texts: list[str]) -> Sequence[Sequence[float]]: ...


class IndexStore(Protocol):
    async def initialize(self) -> None: ...

    async def upsert_chunks(self, chunks: Sequence[Chunk], *, batch_size: int = 64) -> int: ...

    async def readiness_details(
        self,
        *,
        expected_points: int | None = None,
        require_green: bool = True,
    ) -> dict[str, Any]: ...

    async def close(self) -> None: ...


StoreFactory = Callable[
    [Settings, BuildDenseEncoder, SparseCharNgramEncoder | None, Mapping[str, Any]],
    IndexStore,
]


@dataclass(frozen=True, slots=True)
class IndexBuildConfig:
    settings: Settings
    corpus_path: Path
    output_dir: Path
    corpus_manifest_path: Path | None = None
    batch_size: int = 64
    enable_semantic: bool = True
    resume: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= 4096:
            raise ValueError("batch_size must be between 1 and 4096")
        if not self.enabled_strategies:
            raise ValueError(
                "IndexBuildConfig must leave at least one dense chunk strategy enabled"
            )

    @property
    def enabled_strategies(self) -> tuple[ChunkStrategy, ...]:
        return tuple(
            strategy
            for strategy in self.settings.enabled_chunk_strategies
            if strategy is not ChunkStrategy.SEMANTIC_SECTION or self.enable_semantic
        )

    @property
    def dense_strategy_flags(self) -> dict[str, bool]:
        enabled = set(self.enabled_strategies)
        return {strategy.value: strategy in enabled for strategy in ChunkStrategy}

    @property
    def feature_flags(self) -> dict[str, bool]:
        return self.dense_strategy_flags | {
            "sparse": self.settings.rag_enable_sparse,
            "late_chunking": self.settings.rag_enable_late_chunking,
        }

    @property
    def chunks_path(self) -> Path:
        return self.output_dir / CHUNKS_FILENAME

    @property
    def sparse_state_path(self) -> Path:
        return self.output_dir / SPARSE_STATE_FILENAME

    @property
    def manifest_path(self) -> Path:
        return self.output_dir / INDEX_MANIFEST_FILENAME

    @property
    def checkpoint_path(self) -> Path:
        return self.output_dir / CHECKPOINT_FILENAME


@dataclass(frozen=True, slots=True)
class IndexBuildResult:
    chunks_path: Path
    sparse_state_path: Path | None
    manifest_path: Path
    manifest: dict[str, Any]
    reused_existing: bool = False


class OfflineE5DenseEncoder:
    """One locally cached E5 instance shared by semantic chunking and indexing."""

    def __init__(self, model_name: str, revision: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on optional package
            raise IndexPrerequisiteError(
                "Dense embedding support is missing. Install the backend embeddings extra "
                "before building the index."
            ) from exc

        try:
            self._model = SentenceTransformer(
                model_name,
                revision=revision,
                backend="torch",
                device="cpu",
                local_files_only=True,
            )
        except Exception as exc:  # pragma: no cover - depends on local model cache
            raise IndexPrerequisiteError(
                f"Dense model {model_name!r} is not available in the local cache. "
                "Download the frozen model before running build_index; this command "
                "does not fetch models from the network."
            ) from exc

        self.model_name = model_name
        self.model_revision = revision
        self.dimension = int(self._model.get_sentence_embedding_dimension() or 0)
        if self.dimension <= 0:
            raise IndexPrerequisiteError(
                f"Dense model {model_name!r} did not report an embedding dimension"
            )

    def _encode(self, texts: Sequence[str], prefix: str) -> list[list[float]]:
        if not texts:
            return []
        prepared = [f"{prefix}: {text}" for text in texts]
        vectors = self._model.encode(
            prepared,
            batch_size=min(32, len(prepared)),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32).tolist()

    def encode_sentences(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts, "passage")

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode, texts, "query")

    async def encode_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode, texts, "passage")


def _canonical_json_bytes(value: Mapping[str, Any], *, newline: bool = False) -> bytes:
    suffix = b"\n" if newline else b""
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + suffix
    )


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            )
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json_object(path: Path, *, purpose: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise IndexArtifactError(f"Invalid {purpose} JSON: {path}") from exc
    if not isinstance(value, dict):
        raise IndexArtifactError(f"{purpose} must be a JSON object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {"python": sys.version.split()[0]}
    for package in _PACKAGE_NAMES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def _assert_no_evaluation_keys(value: Any, *, location: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if key_text.casefold() in _PROHIBITED_ARTIFACT_KEYS:
                raise IndexArtifactError(f"Evaluation-only field {key_text!r} found in {location}")
            _assert_no_evaluation_keys(child, location=f"{location}.{key_text}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_evaluation_keys(child, location=f"{location}[{index}]")


def _iter_documents(path: Path) -> Iterator[CorpusDocument]:
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            location = f"{path}:{line_number}"
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise IndexArtifactError(f"Invalid corpus JSONL at {location}") from exc
            if not isinstance(value, dict):
                raise IndexArtifactError(f"Corpus row must be an object at {location}")
            _assert_no_evaluation_keys(value, location=location)
            unexpected = set(value) - CORPUS_PAYLOAD_FIELDS
            if unexpected:
                raise IndexArtifactError(
                    f"Non-whitelisted corpus fields at {location}: {sorted(unexpected)}"
                )
            try:
                document = CorpusDocument.model_validate(value)
            except ValidationError as exc:
                raise IndexArtifactError(
                    f"Corpus row is not CorpusDocument-compatible at {location}"
                ) from exc
            if document.canonical_doc_id in seen_ids:
                raise IndexArtifactError(
                    f"Duplicate canonical_doc_id at {location}: {document.canonical_doc_id}"
                )
            seen_ids.add(document.canonical_doc_id)
            yield document


def _empty_strategy_metrics(
    enabled_strategies: Sequence[ChunkStrategy],
) -> dict[str, dict[str, Any]]:
    enabled = set(enabled_strategies)
    return {
        strategy.value: {
            "enabled": strategy in enabled,
            "count": 0,
            "text_characters": 0,
            "text_words": 0,
            "artifact_bytes": 0,
            "duplicate_texts": 0,
            "build_duration_seconds": 0.0,
        }
        for strategy in ChunkStrategy
    }


def _document_chunks(
    factory: ChunkFactory,
    document: CorpusDocument,
    *,
    enabled_strategies: Sequence[ChunkStrategy],
) -> tuple[list[Chunk], dict[str, float]]:
    chunks: list[Chunk] = []
    durations = {strategy.value: 0.0 for strategy in ChunkStrategy}
    enabled = set(enabled_strategies)

    def extend(
        strategy: ChunkStrategy,
        operation: Callable[[], list[Chunk]],
    ) -> None:
        started = time.perf_counter()
        generated = operation()
        durations[strategy.value] += time.perf_counter() - started
        chunks.extend(generated)

    for language in factory.document_languages(document):
        if ChunkStrategy.ATOMIC in enabled:
            extend(
                ChunkStrategy.ATOMIC,
                partial(factory.atomic, document, language),
            )
        if ChunkStrategy.SENTENCE_WINDOW in enabled:
            extend(
                ChunkStrategy.SENTENCE_WINDOW,
                partial(factory.sentence_windows, document, language),
            )
        if ChunkStrategy.SEMANTIC_SECTION in enabled:
            extend(
                ChunkStrategy.SEMANTIC_SECTION,
                partial(factory.semantic_sections, document, language),
            )
        if ChunkStrategy.PARENT_CHILD in enabled:
            extend(
                ChunkStrategy.PARENT_CHILD,
                partial(factory.parent_children, document, language),
            )
    if document.translated_text and ChunkStrategy.BILINGUAL_PAIRED in enabled:
        extend(ChunkStrategy.BILINGUAL_PAIRED, lambda: factory.bilingual_paired(document))
    return chunks, durations


def _build_chunk_artifact(
    corpus_path: Path,
    chunks_path: Path,
    factory: ChunkFactory,
    *,
    enabled_strategies: Sequence[ChunkStrategy],
    expected_documents: int | None,
) -> dict[str, Any]:
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{chunks_path.name}.", suffix=".tmp", dir=chunks_path.parent
    )
    temporary = Path(temporary_name)
    metrics: dict[str, Any] = {
        "document_count": 0,
        "point_count": 0,
        "deduplicated_chunk_ids": 0,
        "strategies": _empty_strategy_metrics(enabled_strategies),
    }
    seen_chunk_ids: set[str] = set()
    seen_texts: dict[str, set[bytes]] = {strategy.value: set() for strategy in ChunkStrategy}
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for document in _iter_documents(corpus_path):
                metrics["document_count"] += 1
                generated, durations = _document_chunks(
                    factory, document, enabled_strategies=enabled_strategies
                )
                for strategy, duration in durations.items():
                    metrics["strategies"][strategy]["build_duration_seconds"] += duration

                for chunk in generated:
                    if chunk.chunk_id in seen_chunk_ids:
                        metrics["deduplicated_chunk_ids"] += 1
                        continue
                    seen_chunk_ids.add(chunk.chunk_id)
                    payload = chunk.model_dump(mode="json")
                    _assert_no_evaluation_keys(payload, location=f"chunk {chunk.chunk_id}")
                    encoded = _canonical_json_bytes(payload, newline=True)
                    handle.write(encoded)

                    strategy_metrics = metrics["strategies"][chunk.strategy.value]
                    strategy_metrics["count"] += 1
                    strategy_metrics["text_characters"] += len(chunk.text)
                    strategy_metrics["text_words"] += len(chunk.text.split())
                    strategy_metrics["artifact_bytes"] += len(encoded)
                    text_digest = hashlib.sha256(chunk.text.encode("utf-8")).digest()
                    if text_digest in seen_texts[chunk.strategy.value]:
                        strategy_metrics["duplicate_texts"] += 1
                    else:
                        seen_texts[chunk.strategy.value].add(text_digest)
                    metrics["point_count"] += 1
            handle.flush()
            os.fsync(handle.fileno())

        if metrics["document_count"] == 0:
            raise IndexArtifactError(f"Corpus contains no documents: {corpus_path}")
        if expected_documents is not None and metrics["document_count"] != expected_documents:
            raise IndexArtifactError(
                "Corpus record count does not match corpus manifest: "
                f"{metrics['document_count']} != {expected_documents}"
            )
        if metrics["point_count"] == 0:
            raise IndexArtifactError("ChunkFactory emitted no indexable chunks")
        os.replace(temporary, chunks_path)
        return metrics
    finally:
        temporary.unlink(missing_ok=True)


def _iter_chunks(path: Path) -> Iterator[Chunk]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            location = f"{path}:{line_number}"
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise IndexArtifactError(f"Invalid chunk JSONL at {location}") from exc
            if not isinstance(value, dict):
                raise IndexArtifactError(f"Chunk row must be an object at {location}")
            _assert_no_evaluation_keys(value, location=location)
            try:
                yield Chunk.model_validate(value)
            except ValidationError as exc:
                raise IndexArtifactError(f"Invalid chunk at {location}") from exc


def _chunk_batches(path: Path, *, skip: int, batch_size: int) -> Iterator[list[Chunk]]:
    batch: list[Chunk] = []
    total = 0
    for chunk in _iter_chunks(path):
        if total < skip:
            total += 1
            continue
        total += 1
        batch.append(chunk)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if skip > total:
        raise IndexArtifactError(
            f"Checkpoint point offset {skip} exceeds chunk artifact count {total}"
        )
    if batch:
        yield batch


def _fit_sparse_encoder(chunks_path: Path) -> SparseCharNgramEncoder:
    encoder = SparseCharNgramEncoder(
        dimensions=SPARSE_DIMENSIONS,
        min_n=SPARSE_MIN_N,
        max_n=SPARSE_MAX_N,
    )
    encoder.fit(chunk.text for chunk in _iter_chunks(chunks_path))
    return encoder


def _corpus_manifest_details(
    config: IndexBuildConfig, corpus_sha256: str
) -> tuple[str, int | None]:
    explicit = config.corpus_manifest_path
    candidate = explicit or config.corpus_path.parent / "corpus-manifest.json"
    if not candidate.exists():
        if explicit is not None:
            raise IndexPrerequisiteError(f"Corpus manifest does not exist: {candidate}")
        return "", None

    manifest = _read_json_object(candidate, purpose="corpus manifest")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise IndexArtifactError("Corpus manifest is missing its artifacts section")
    artifact = artifacts.get("corpus")
    if not isinstance(artifact, Mapping):
        raise IndexArtifactError("Corpus manifest is missing artifacts.corpus")
    expected_sha = artifact.get("sha256")
    if expected_sha != corpus_sha256:
        raise IndexArtifactError(
            "Corpus checksum does not match corpus-manifest.json: "
            f"expected {expected_sha!r}, got {corpus_sha256!r}"
        )
    records = artifact.get("records")
    expected_records = int(records) if records is not None else None
    return _sha256_file(candidate), expected_records


def _model_revision(encoder: BuildDenseEncoder) -> str | None:
    value = getattr(encoder, "model_revision", None)
    return str(value) if value else None


def _build_id(
    config: IndexBuildConfig,
    *,
    corpus_sha256: str,
    corpus_manifest_sha256: str,
    encoder: BuildDenseEncoder,
    package_versions: Mapping[str, str | None],
) -> str:
    sparse_configuration = (
        {
            "algorithm": SPARSE_ALGORITHM_VERSION,
            "dimensions": SPARSE_DIMENSIONS,
            "max_n": SPARSE_MAX_N,
            "min_n": SPARSE_MIN_N,
            "vector_name": config.settings.sparse_vector_name,
        }
        if config.settings.rag_enable_sparse
        else None
    )
    material = {
        "artifact_version": INDEX_ARTIFACT_VERSION,
        "chunk_algorithm": CHUNK_ALGORITHM_VERSION,
        "chunk_parameters": CHUNK_PARAMETERS,
        "collection": config.settings.qdrant_collection,
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "corpus_sha256": corpus_sha256,
        "dense_dimension": encoder.dimension,
        "dense_model": config.settings.rag_dense_model,
        "dense_vector_name": config.settings.dense_vector_name,
        "feature_flags": config.feature_flags,
        "enabled_dense_strategies": [strategy.value for strategy in config.enabled_strategies],
        "model_revision": _model_revision(encoder),
        "package_versions": dict(package_versions),
        "sparse_configuration": sparse_configuration,
    }
    return hashlib.sha256(_canonical_json_bytes(material)).hexdigest()


def _artifact_checksums(config: IndexBuildConfig) -> dict[str, str]:
    checksums = {"chunks": _sha256_file(config.chunks_path)}
    if config.settings.rag_enable_sparse:
        checksums["sparse_encoder"] = _sha256_file(config.sparse_state_path)
    return checksums


def _validate_artifact_file(path: Path, expected_sha256: object, *, name: str) -> None:
    if not path.exists():
        raise IndexArtifactError(f"{name} artifact is missing: {path}")
    actual = _sha256_file(path)
    if actual != expected_sha256:
        raise IndexArtifactError(
            f"{name} artifact checksum mismatch: expected {expected_sha256!r}, got {actual!r}"
        )


def _load_existing_manifest(config: IndexBuildConfig, *, build_id: str) -> dict[str, Any] | None:
    if not config.manifest_path.exists():
        return None
    manifest = _read_json_object(config.manifest_path, purpose="index manifest")
    if manifest.get("chunk_build_id") != build_id:
        raise IndexArtifactError(
            "Existing index manifest was built with incompatible corpus/model/chunk "
            "settings. Use a different output directory and Qdrant collection; this "
            "builder will not replace an incompatible collection."
        )
    if not config.resume:
        return None
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise IndexArtifactError("Index manifest is missing its artifacts section")
    chunks = artifacts.get("chunks")
    if not isinstance(chunks, Mapping):
        raise IndexArtifactError("Index manifest has an invalid chunks artifact entry")
    _validate_artifact_file(config.chunks_path, chunks.get("sha256"), name="chunks")
    sparse_built = manifest.get("sparse_vectors_built")
    if sparse_built is not config.settings.rag_enable_sparse:
        raise IndexArtifactError(
            "Index manifest sparse_vectors_built does not match RAG_ENABLE_SPARSE"
        )
    if config.settings.rag_enable_sparse:
        sparse = artifacts.get("sparse_encoder")
        if not isinstance(sparse, Mapping):
            raise IndexArtifactError("Index manifest has an invalid sparse encoder artifact entry")
        _validate_artifact_file(
            config.sparse_state_path,
            sparse.get("sha256"),
            name="sparse encoder",
        )
    return manifest


def _checkpoint_payload(
    *,
    build_id: str,
    corpus_sha256: str,
    artifact_checksums: Mapping[str, str],
    point_count: int,
    next_chunk_index: int,
    metrics: Mapping[str, Any] | None,
    active_build_duration_seconds: float,
) -> dict[str, Any]:
    return {
        "checkpoint_version": 1,
        "chunk_build_id": build_id,
        "corpus_sha256": corpus_sha256,
        "artifact_checksums": dict(artifact_checksums),
        "point_count": point_count,
        "next_chunk_index": next_chunk_index,
        "active_build_duration_seconds": active_build_duration_seconds,
        "artifact_metrics": dict(metrics) if metrics is not None else None,
    }


def _load_checkpoint(
    config: IndexBuildConfig,
    *,
    build_id: str,
    corpus_sha256: str,
) -> dict[str, Any] | None:
    if not config.resume or not config.checkpoint_path.exists():
        return None
    checkpoint = _read_json_object(config.checkpoint_path, purpose="index checkpoint")
    if checkpoint.get("checkpoint_version") != 1:
        raise IndexArtifactError("Unsupported index checkpoint version")
    if (
        checkpoint.get("chunk_build_id") != build_id
        or checkpoint.get("corpus_sha256") != corpus_sha256
    ):
        raise IndexArtifactError(
            "Index checkpoint is incompatible with this corpus/model configuration; "
            "use a different output directory or rerun with --no-resume."
        )
    checksums = checkpoint.get("artifact_checksums")
    if not isinstance(checksums, Mapping):
        raise IndexArtifactError("Index checkpoint has no artifact checksums")
    _validate_artifact_file(config.chunks_path, checksums.get("chunks"), name="chunks")
    if config.settings.rag_enable_sparse:
        _validate_artifact_file(
            config.sparse_state_path,
            checksums.get("sparse_encoder"),
            name="sparse encoder",
        )
    point_count = int(checkpoint.get("point_count", -1))
    next_index = int(checkpoint.get("next_chunk_index", -1))
    if point_count < 1 or not 0 <= next_index <= point_count:
        raise IndexArtifactError("Index checkpoint has invalid point offsets")
    return checkpoint


def _strategy_manifest(metrics: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    strategies = metrics.get("strategies", {})
    if not isinstance(strategies, Mapping):
        raise IndexArtifactError("Chunk metrics are missing strategy statistics")
    for strategy in ChunkStrategy:
        raw = strategies.get(strategy.value, {})
        if not isinstance(raw, Mapping):
            raise IndexArtifactError(f"Invalid metrics for strategy {strategy.value}")
        count = int(raw.get("count", 0))
        characters = int(raw.get("text_characters", 0))
        words = int(raw.get("text_words", 0))
        result[strategy.value] = {
            "enabled": bool(raw.get("enabled", True)),
            "count": count,
            "average_text_characters": round(characters / count, 3) if count else 0.0,
            "average_text_words": round(words / count, 3) if count else 0.0,
            "duplicate_texts": int(raw.get("duplicate_texts", 0)),
            "artifact_bytes": int(raw.get("artifact_bytes", 0)),
            "build_duration_seconds": round(float(raw.get("build_duration_seconds", 0.0)), 6),
        }
    return result


def _new_manifest(
    config: IndexBuildConfig,
    *,
    build_id: str,
    corpus_sha256: str,
    corpus_manifest_sha256: str,
    encoder: BuildDenseEncoder,
    sparse_encoder: SparseCharNgramEncoder | None,
    metrics: Mapping[str, Any],
    package_versions: Mapping[str, str | None],
    active_build_duration_seconds: float,
    exact_point_count: int,
) -> dict[str, Any]:
    sparse_enabled = config.settings.rag_enable_sparse
    if sparse_enabled != (sparse_encoder is not None):
        raise IndexBuildError("Sparse encoder availability does not match RAG_ENABLE_SPARSE")
    checksums = _artifact_checksums(config)
    strategies = _strategy_manifest(metrics)
    strategy_counts = {strategy: int(values["count"]) for strategy, values in strategies.items()}
    average_lengths = {
        strategy: float(values["average_text_characters"])
        for strategy, values in strategies.items()
    }
    chunks_bytes = config.chunks_path.stat().st_size
    sparse_bytes = config.sparse_state_path.stat().st_size if sparse_enabled else 0
    point_count = int(metrics["point_count"])
    if exact_point_count != point_count:
        raise IndexBuildError(
            f"Qdrant point count differs from chunk artifact: {exact_point_count} != {point_count}"
        )
    artifacts: dict[str, Any] = {
        "corpus": {
            "filename": config.corpus_path.name,
            "sha256": corpus_sha256,
            "bytes": config.corpus_path.stat().st_size,
        },
        "chunks": {
            "filename": CHUNKS_FILENAME,
            "sha256": checksums["chunks"],
            "bytes": chunks_bytes,
            "records": point_count,
        },
    }
    vectors: dict[str, Any] = {
        "dense": {
            "name": config.settings.dense_vector_name,
            "size": encoder.dimension,
            "distance": "Cosine",
        }
    }
    if sparse_encoder is not None:
        artifacts["sparse_encoder"] = {
            "filename": SPARSE_STATE_FILENAME,
            "sha256": checksums["sparse_encoder"],
            "bytes": sparse_bytes,
            "document_count": sparse_encoder.document_count,
        }
        vectors["sparse"] = {
            "name": config.settings.sparse_vector_name,
            "algorithm": SPARSE_ALGORITHM_VERSION,
            "dimensions": sparse_encoder.dimensions,
            "min_n": sparse_encoder.min_n,
            "max_n": sparse_encoder.max_n,
        }

    manifest: dict[str, Any] = {
        "artifact_version": INDEX_ARTIFACT_VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        "chunk_build_id": build_id,
        "collection": config.settings.qdrant_collection,
        "point_count": point_count,
        "chunk_count": point_count,
        "document_count": int(metrics["document_count"]),
        "dense_model": config.settings.rag_dense_model,
        "model_revision": _model_revision(encoder),
        "dense_vector_name": config.settings.dense_vector_name,
        "dense_vector_size": encoder.dimension,
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "strategy_counts": strategy_counts,
        "strategy_average_lengths": average_lengths,
        "strategies": strategies,
        "feature_flags": config.feature_flags,
        "enabled_dense_strategies": [strategy.value for strategy in config.enabled_strategies],
        "sparse_vectors_built": sparse_enabled,
        "build_time_seconds": round(active_build_duration_seconds, 6),
        "disk_bytes": chunks_bytes + sparse_bytes,
        "checksums": {
            "corpus": corpus_sha256,
            "corpus_manifest": corpus_manifest_sha256 or None,
            **checksums,
        },
        "artifacts": artifacts,
        "vectors": vectors,
        "build": {
            "semantic_enabled": (ChunkStrategy.SEMANTIC_SECTION in config.enabled_strategies),
            "enabled_dense_strategies": [strategy.value for strategy in config.enabled_strategies],
            "feature_flags": config.feature_flags,
            "chunk_parameters": CHUNK_PARAMETERS,
            "batch_size": config.batch_size,
            "active_duration_seconds": round(active_build_duration_seconds, 6),
            "deduplicated_chunk_ids": int(metrics["deduplicated_chunk_ids"]),
            "resume_supported": True,
            "network_model_downloads": False,
        },
        "package_versions": dict(package_versions),
        "source_payload_whitelist": sorted(CORPUS_PAYLOAD_FIELDS),
    }
    if sparse_enabled:
        manifest["sparse_vector_name"] = config.settings.sparse_vector_name
    return manifest


def _default_store_factory(
    settings: Settings,
    dense_encoder: BuildDenseEncoder,
    sparse_encoder: SparseCharNgramEncoder | None,
    metadata: Mapping[str, Any],
) -> IndexStore:
    return QdrantStore(
        settings,
        dense_encoder,
        sparse_encoder,
        collection_metadata=metadata,
    )


def _load_default_encoder(settings: Settings) -> BuildDenseEncoder:
    return OfflineE5DenseEncoder(settings.rag_dense_model, settings.rag_dense_model_revision)


def _sentence_embedder(
    encoder: BuildDenseEncoder, *, enabled: bool
) -> Callable[[list[str]], Sequence[Sequence[float]]] | None:
    if not enabled:
        return None
    method = getattr(encoder, "encode_sentences", None)
    if not callable(method):
        raise IndexPrerequisiteError(
            "The loaded dense encoder cannot synchronously embed sentences required "
            "for semantic chunking. Use --no-semantic or an offline E5 encoder."
        )
    return method


async def build_index(
    config: IndexBuildConfig,
    *,
    dense_encoder: BuildDenseEncoder | None = None,
    store_factory: StoreFactory | None = None,
) -> IndexBuildResult:
    """Build deterministic chunks/sparse state and safely resume Qdrant ingestion."""

    run_started = time.perf_counter()
    if not config.corpus_path.exists():
        raise IndexPrerequisiteError(
            f"Corpus does not exist: {config.corpus_path}. Run build_corpus first."
        )
    if not config.corpus_path.is_file() or config.corpus_path.stat().st_size == 0:
        raise IndexPrerequisiteError(f"Corpus is not a non-empty file: {config.corpus_path}")
    config.output_dir.mkdir(parents=True, exist_ok=True)

    corpus_sha256 = await asyncio.to_thread(_sha256_file, config.corpus_path)
    corpus_manifest_sha256, expected_documents = await asyncio.to_thread(
        _corpus_manifest_details, config, corpus_sha256
    )
    packages = _package_versions()
    if dense_encoder is None:
        encoder = await asyncio.to_thread(_load_default_encoder, config.settings)
    else:
        encoder = dense_encoder
    if encoder.dimension != config.settings.dense_vector_size:
        raise IndexPrerequisiteError(
            "Loaded dense model dimension does not match configuration: "
            f"{encoder.dimension} != {config.settings.dense_vector_size}"
        )

    build_id = _build_id(
        config,
        corpus_sha256=corpus_sha256,
        corpus_manifest_sha256=corpus_manifest_sha256,
        encoder=encoder,
        package_versions=packages,
    )
    existing_manifest = _load_existing_manifest(config, build_id=build_id)
    checkpoint = _load_checkpoint(
        config,
        build_id=build_id,
        corpus_sha256=corpus_sha256,
    )
    metrics: Mapping[str, Any] | None = None
    carried_duration = 0.0

    if existing_manifest is not None:
        sparse_encoder = (
            await asyncio.to_thread(SparseCharNgramEncoder.load, config.sparse_state_path)
            if config.settings.rag_enable_sparse
            else None
        )
        point_count = int(existing_manifest.get("point_count", -1))
        if point_count < 1:
            raise IndexArtifactError("Existing index manifest has an invalid point_count")
        if checkpoint is not None:
            if int(checkpoint["point_count"]) != point_count:
                raise IndexArtifactError(
                    "Index checkpoint point count differs from the completed manifest"
                )
            carried_duration = float(checkpoint.get("active_build_duration_seconds", 0.0))
    elif checkpoint is not None:
        sparse_encoder = (
            await asyncio.to_thread(SparseCharNgramEncoder.load, config.sparse_state_path)
            if config.settings.rag_enable_sparse
            else None
        )
        point_count = int(checkpoint["point_count"])
        raw_metrics = checkpoint.get("artifact_metrics")
        metrics = raw_metrics if isinstance(raw_metrics, Mapping) else None
        carried_duration = float(checkpoint.get("active_build_duration_seconds", 0.0))
    else:
        factory = ChunkFactory(
            sentence_window_size=int(CHUNK_PARAMETERS["sentence_window_size"]),
            sentence_overlap=int(CHUNK_PARAMETERS["sentence_overlap"]),
            semantic_min_sentences=int(CHUNK_PARAMETERS["semantic_min_sentences"]),
            semantic_break_quantile=float(CHUNK_PARAMETERS["semantic_break_quantile"]),
            semantic_max_words=int(CHUNK_PARAMETERS["semantic_max_words"]),
            bilingual_max_characters=int(CHUNK_PARAMETERS["bilingual_max_characters"]),
            sentence_embedder=_sentence_embedder(
                encoder,
                enabled=(ChunkStrategy.SEMANTIC_SECTION in config.enabled_strategies),
            ),
        )
        metrics = await asyncio.to_thread(
            _build_chunk_artifact,
            config.corpus_path,
            config.chunks_path,
            factory,
            enabled_strategies=config.enabled_strategies,
            expected_documents=expected_documents,
        )
        sparse_encoder = None
        if config.settings.rag_enable_sparse:
            sparse_encoder = await asyncio.to_thread(_fit_sparse_encoder, config.chunks_path)
            await asyncio.to_thread(sparse_encoder.save, config.sparse_state_path)
        point_count = int(metrics["point_count"])
        checksums = await asyncio.to_thread(_artifact_checksums, config)
        _atomic_write_json(
            config.checkpoint_path,
            _checkpoint_payload(
                build_id=build_id,
                corpus_sha256=corpus_sha256,
                artifact_checksums=checksums,
                point_count=point_count,
                next_chunk_index=0,
                metrics=metrics,
                active_build_duration_seconds=time.perf_counter() - run_started,
            ),
        )
        checkpoint = _read_json_object(config.checkpoint_path, purpose="index checkpoint")

    if sparse_encoder is not None and sparse_encoder.document_count != point_count:
        raise IndexArtifactError(
            "Sparse encoder document count differs from chunk point count: "
            f"{sparse_encoder.document_count} != {point_count}"
        )

    metadata = {
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "chunk_build_id": build_id,
    }
    factory_function = store_factory or _default_store_factory
    store = factory_function(config.settings, encoder, sparse_encoder, metadata)
    try:
        await store.initialize()
        current = await store.readiness_details(expected_points=point_count, require_green=False)
        if existing_manifest is not None and current.get("ready") is True:
            config.checkpoint_path.unlink(missing_ok=True)
            return IndexBuildResult(
                chunks_path=config.chunks_path,
                sparse_state_path=(
                    config.sparse_state_path if config.settings.rag_enable_sparse else None
                ),
                manifest_path=config.manifest_path,
                manifest=existing_manifest,
                reused_existing=True,
            )

        next_index = int(checkpoint.get("next_chunk_index", 0)) if checkpoint else 0
        current_count = current.get("exact_points_count")
        if isinstance(current_count, int) and current_count < next_index:
            next_index = 0

        checksums = await asyncio.to_thread(_artifact_checksums, config)
        for batch in _chunk_batches(
            config.chunks_path,
            skip=next_index,
            batch_size=config.batch_size,
        ):
            written = await store.upsert_chunks(batch, batch_size=len(batch))
            if written != len(batch):
                raise IndexBuildError(
                    f"Qdrant upsert acknowledged {written} points for a {len(batch)} point batch"
                )
            next_index += len(batch)
            _atomic_write_json(
                config.checkpoint_path,
                _checkpoint_payload(
                    build_id=build_id,
                    corpus_sha256=corpus_sha256,
                    artifact_checksums=checksums,
                    point_count=point_count,
                    next_chunk_index=next_index,
                    metrics=metrics,
                    active_build_duration_seconds=(
                        carried_duration + time.perf_counter() - run_started
                    ),
                ),
            )

        final_readiness = await store.readiness_details(
            expected_points=point_count, require_green=False
        )
        if final_readiness.get("ready") is not True:
            raise IndexBuildError(
                "Qdrant is not ready after deterministic upsert: "
                + json.dumps(final_readiness, ensure_ascii=False, sort_keys=True)
            )
        exact_count = final_readiness.get("exact_points_count")
        if not isinstance(exact_count, int):
            raise IndexBuildError("Qdrant readiness did not return an exact point count")

        if existing_manifest is not None:
            config.checkpoint_path.unlink(missing_ok=True)
            return IndexBuildResult(
                chunks_path=config.chunks_path,
                sparse_state_path=(
                    config.sparse_state_path if config.settings.rag_enable_sparse else None
                ),
                manifest_path=config.manifest_path,
                manifest=existing_manifest,
                reused_existing=False,
            )
        if metrics is None:
            raise IndexArtifactError("Index checkpoint is missing chunk strategy metrics")

        active_duration = carried_duration + time.perf_counter() - run_started
        manifest = _new_manifest(
            config,
            build_id=build_id,
            corpus_sha256=corpus_sha256,
            corpus_manifest_sha256=corpus_manifest_sha256,
            encoder=encoder,
            sparse_encoder=sparse_encoder,
            metrics=metrics,
            package_versions=packages,
            active_build_duration_seconds=active_duration,
            exact_point_count=exact_count,
        )
        _atomic_write_json(config.manifest_path, manifest)
        config.checkpoint_path.unlink(missing_ok=True)
        return IndexBuildResult(
            chunks_path=config.chunks_path,
            sparse_state_path=(
                config.sparse_state_path if config.settings.rag_enable_sparse else None
            ),
            manifest_path=config.manifest_path,
            manifest=manifest,
        )
    finally:
        await store.close()


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Build deterministic configured Qdrant index artifacts."
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=settings.rag_data_dir / "corpus" / "corpus.jsonl",
    )
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        help="Optional corpus manifest; otherwise auto-detected beside corpus.jsonl.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=settings.rag_data_dir / "index",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--no-semantic", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 4096:
        parser.error("--batch-size must be between 1 and 4096")
    settings = get_settings()
    config = IndexBuildConfig(
        settings=settings,
        corpus_path=args.corpus,
        corpus_manifest_path=args.corpus_manifest,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
        enable_semantic=not args.no_semantic,
        resume=not args.no_resume,
    )
    try:
        result = asyncio.run(build_index(config))
    except (IndexBuildError, OSError, ValueError) as exc:
        print(f"build-index failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.manifest, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Chunks: {result.chunks_path}")
    print(
        f"Sparse encoder: {result.sparse_state_path}"
        if result.sparse_state_path is not None
        else "Sparse encoder: disabled"
    )
    print(f"Manifest: {result.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
