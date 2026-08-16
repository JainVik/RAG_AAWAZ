from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from functools import partial
from typing import Any, Literal, TypeVar
from uuid import UUID, uuid5

from pydantic import ValidationError
from qdrant_client import AsyncQdrantClient, models

from app.core.config import Settings
from app.core.errors import DependencyUnavailable, PipelineError
from app.domain.enums import ChunkStrategy, ErrorCode, Language, PipelineState
from app.domain.models import Chunk, SearchHit, SparseVector
from app.embeddings.dense import DenseEncoder
from app.embeddings.sparse_char_ngram import SparseCharNgramEncoder
from app.harness.circuit_breaker import CircuitBreaker
from app.retrieval.dense_search import DenseSearcher
from app.retrieval.sparse_search import SparseSearcher

T = TypeVar("T")
SearchBranch = Literal["dense", "sparse"]

COLLECTION_SCHEMA_VERSION = "awaaz-tiderag-qdrant-v3"
_POINT_ID_NAMESPACE = UUID("91ffdc40-870f-40df-bf2b-1844226d7ee9")
_UINT32_LIMIT = 1 << 32


class QdrantStoreError(PipelineError):
    """Structured failure raised by the Qdrant storage boundary."""

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        collection: str,
        retryable: bool,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        error_details: dict[str, Any] = {
            "operation": operation,
            "collection": collection,
        }
        if details:
            error_details.update(details)
        super().__init__(
            code=ErrorCode.QDRANT_ERROR,
            message=message,
            state=(
                PipelineState.DEPENDENCY_UNAVAILABLE
                if retryable
                else PipelineState.FAILED
            ),
            retryable=retryable,
            details=error_details,
        )


class QdrantStore(DenseSearcher, SparseSearcher):
    """Long-lived async Qdrant adapter for the named dense and sparse vectors."""

    def __init__(
        self,
        settings: Settings,
        dense_encoder: DenseEncoder,
        sparse_encoder: SparseCharNgramEncoder | None,
        *,
        client: AsyncQdrantClient | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        request_timeout_s: int = 5,
        close_client: bool = True,
        collection_metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if dense_encoder.dimension != settings.dense_vector_size:
            raise ValueError(
                "Dense encoder dimension does not match settings.dense_vector_size: "
                f"{dense_encoder.dimension} != {settings.dense_vector_size}"
            )
        if not settings.dense_vector_name.strip() or not settings.sparse_vector_name.strip():
            raise ValueError("Qdrant vector names must be non-empty")
        if settings.dense_vector_name == settings.sparse_vector_name:
            raise ValueError("Dense and sparse Qdrant vector names must be different")
        if settings.rag_enable_sparse and sparse_encoder is None:
            raise ValueError("Sparse retrieval is enabled but no sparse encoder was provided")
        if not settings.rag_enable_sparse and sparse_encoder is not None:
            raise ValueError("Sparse encoder must be omitted when sparse retrieval is disabled")
        if request_timeout_s <= 0:
            raise ValueError("request_timeout_s must be positive")

        self.settings = settings
        self.dense_encoder = dense_encoder
        self.sparse_encoder = sparse_encoder
        self.collection_name = settings.qdrant_collection
        self.dense_vector_name = settings.dense_vector_name
        self.sparse_vector_name = settings.sparse_vector_name
        self.sparse_enabled = settings.rag_enable_sparse

        metadata = dict(collection_metadata or {})
        metadata.update(
            {
                "schema_version": COLLECTION_SCHEMA_VERSION,
                "dense_model": settings.rag_dense_model,
                "dense_model_revision": settings.rag_dense_model_revision,
                "dense_dimension": dense_encoder.dimension,
                "dense_vector_name": self.dense_vector_name,
                "sparse_enabled": self.sparse_enabled,
            }
        )
        if sparse_encoder is not None:
            metadata.update(
                {
                    "sparse_vector_name": self.sparse_vector_name,
                    "sparse_encoder": "char-ngram-tfidf-v1",
                    "sparse_dimensions": sparse_encoder.dimensions,
                    "sparse_min_n": sparse_encoder.min_n,
                    "sparse_max_n": sparse_encoder.max_n,
                }
            )
        self._expected_metadata = metadata

        self._client = client or AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key_value,
            timeout=request_timeout_s,
            check_compatibility=True,
        )
        self._close_client = close_client
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            "qdrant", failure_threshold=3, recovery_timeout_s=10.0
        )
        self._initialize_lock = asyncio.Lock()
        self._initialized = False
        self._closed = False

    @property
    def expected_collection_metadata(self) -> dict[str, Any]:
        return dict(self._expected_metadata)

    async def __aenter__(self) -> QdrantStore:
        await self.initialize()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the shared async client once, normally during application shutdown."""

        if self._closed:
            return
        self._closed = True
        if self._close_client:
            await self._client.close()

    async def initialize(self) -> None:
        """Create a missing collection or validate an existing one without replacing it."""

        self._ensure_open()
        if self._initialized:
            return

        async with self._initialize_lock:
            if self._initialized:
                return

            exists = await self._qdrant_call(
                "collection_exists",
                lambda: self._client.collection_exists(self.collection_name),
            )
            if not exists:
                await self._qdrant_call(
                    "create_collection",
                    lambda: self._client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config={
                            self.dense_vector_name: models.VectorParams(
                                size=self.dense_encoder.dimension,
                                distance=models.Distance.COSINE,
                                on_disk=True,
                            )
                        },
                        sparse_vectors_config=(
                            {
                                self.sparse_vector_name: models.SparseVectorParams(
                                    index=models.SparseIndexParams(
                                        on_disk=True,
                                    )
                                )
                            }
                            if self.sparse_enabled
                            else None
                        ),
                        on_disk_payload=True,
                        metadata=self._expected_metadata,
                    ),
                )

            info = await self._qdrant_call(
                "get_collection",
                lambda: self._client.get_collection(self.collection_name),
            )
            schema_errors = self._collection_schema_errors(
                info, require_payload_indexes=False
            )
            if schema_errors:
                raise self._schema_error(schema_errors)

            payload_schema = _as_mapping(_read(info, "payload_schema"))
            for field_name in ("strategy", "language"):
                if field_name in payload_schema:
                    continue
                await self._qdrant_call(
                    f"create_{field_name}_payload_index",
                    partial(
                        self._client.create_payload_index,
                        collection_name=self.collection_name,
                        field_name=field_name,
                        field_schema=models.PayloadSchemaType.KEYWORD,
                        wait=True,
                    ),
                )

            self._initialized = True

    async def upsert_chunks(
        self, chunks: Sequence[Chunk], *, batch_size: int = 64
    ) -> int:
        """Upsert complete, deterministic point batches and return the point count."""

        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if not chunks:
            return 0
        await self.initialize()

        ordered = sorted(chunks, key=lambda chunk: chunk.chunk_id)
        chunk_ids = [chunk.chunk_id for chunk in ordered]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("chunk_id values must be unique within an upsert")

        for offset in range(0, len(ordered), batch_size):
            batch = ordered[offset : offset + batch_size]
            dense_vectors = await self.dense_encoder.encode_passages(
                [chunk.text for chunk in batch]
            )
            normalized_dense = self._validate_dense_vectors(
                dense_vectors,
                expected_count=len(batch),
                operation="encode_passages",
            )

            points: list[models.PointStruct] = []
            for chunk, dense_vector in zip(batch, normalized_dense, strict=True):
                point_vectors: dict[str, Any] = {
                    self.dense_vector_name: dense_vector
                }
                if self.sparse_encoder is not None:
                    sparse_vector = self._validate_sparse_vector(
                        self.sparse_encoder.encode(chunk.text),
                        operation="encode_passages",
                    )
                    point_vectors[self.sparse_vector_name] = models.SparseVector(
                        indices=sparse_vector.indices,
                        values=sparse_vector.values,
                    )
                points.append(
                    models.PointStruct(
                        id=self._point_id(chunk.chunk_id),
                        vector=point_vectors,
                        payload=chunk.model_dump(mode="json"),
                    )
                )

            await self._qdrant_call(
                "upsert",
                partial(
                    self._client.upsert,
                    collection_name=self.collection_name,
                    points=points,
                    wait=True,
                ),
            )
        return len(ordered)

    async def search_dense(
        self,
        query: str,
        *,
        strategies: Sequence[ChunkStrategy],
        limit: int,
        languages: Sequence[Language] | None = None,
    ) -> list[SearchHit]:
        prepared_query = _validate_search_input(query, limit)
        query_filter = _payload_filter(strategies, languages=languages)
        if query_filter is None:
            return []
        await self.initialize()

        dense_vectors = await self.dense_encoder.encode_queries([prepared_query])
        dense_vector = self._validate_dense_vectors(
            dense_vectors, expected_count=1, operation="encode_query"
        )[0]
        response = await self._qdrant_call(
            "query_dense",
            lambda: self._client.query_points(
                collection_name=self.collection_name,
                query=dense_vector,
                using=self.dense_vector_name,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            ),
        )
        return self._decode_query_response(response, branch="dense")

    async def search_sparse(
        self,
        query: str,
        *,
        strategies: Sequence[ChunkStrategy],
        limit: int,
        languages: Sequence[Language] | None = None,
    ) -> list[SearchHit]:
        prepared_query = _validate_search_input(query, limit)
        if not self.sparse_enabled:
            return []
        query_filter = _payload_filter(strategies, languages=languages)
        if query_filter is None:
            return []
        await self.initialize()

        assert self.sparse_encoder is not None
        sparse_vector = self._validate_sparse_vector(
            self.sparse_encoder.encode(prepared_query), operation="encode_query"
        )
        if not sparse_vector.indices:
            return []
        response = await self._qdrant_call(
            "query_sparse",
            lambda: self._client.query_points(
                collection_name=self.collection_name,
                query=models.SparseVector(
                    indices=sparse_vector.indices,
                    values=sparse_vector.values,
                ),
                using=self.sparse_vector_name,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            ),
        )
        return self._decode_query_response(response, branch="sparse")

    async def readiness_details(
        self,
        *,
        expected_points: int | None = None,
        require_green: bool = True,
    ) -> dict[str, Any]:
        """Return non-mutating service, collection, schema, and count readiness."""

        if expected_points is not None and expected_points < 0:
            raise ValueError("expected_points must not be negative")

        details: dict[str, Any] = {
            "ready": False,
            "service": "qdrant",
            "collection": self.collection_name,
            "exists": False,
            "schema_valid": False,
            "schema_errors": [],
            "expected_points": expected_points,
            "circuit_state": _enum_value(self._circuit_breaker.state),
        }
        if self._closed:
            details["error"] = {
                "code": ErrorCode.QDRANT_ERROR.value,
                "message": "Qdrant store is closed",
                "retryable": False,
            }
            return details

        try:
            service_info = await self._qdrant_call("info", self._client.info)
            details["version"] = _read(service_info, "version")
            details["title"] = _read(service_info, "title")

            exists = await self._qdrant_call(
                "collection_exists",
                lambda: self._client.collection_exists(self.collection_name),
            )
            details["exists"] = bool(exists)
            if not exists:
                details["schema_errors"] = ["collection does not exist"]
                return details

            info = await self._qdrant_call(
                "get_collection",
                lambda: self._client.get_collection(self.collection_name),
            )
            status = _enum_value(_read(info, "status"))
            optimizer_status = _optimizer_status(_read(info, "optimizer_status"))
            details.update(
                {
                    "status": status,
                    "optimizer_status": optimizer_status,
                    "points_count": _read(info, "points_count"),
                    "indexed_vectors_count": _read(info, "indexed_vectors_count"),
                }
            )

            schema_errors = self._collection_schema_errors(
                info, require_payload_indexes=True
            )
            details["schema_errors"] = schema_errors
            details["schema_valid"] = not schema_errors

            count_matches = True
            if expected_points is not None:
                count_result = await self._qdrant_call(
                    "count",
                    lambda: self._client.count(
                        collection_name=self.collection_name, exact=True
                    ),
                )
                exact_count = _read(count_result, "count")
                details["exact_points_count"] = exact_count
                count_matches = exact_count == expected_points
                details["point_count_matches"] = count_matches

            status_ready = not require_green or status == models.CollectionStatus.GREEN.value
            details["ready"] = bool(
                not schema_errors
                and status_ready
                and optimizer_status == models.OptimizersStatusOneOf.OK.value
                and count_matches
            )
            return details
        except PipelineError as exc:
            details["circuit_state"] = _enum_value(self._circuit_breaker.state)
            details["error"] = {
                "code": exc.code.value,
                "message": exc.message,
                "retryable": exc.retryable,
                "details": exc.details or {},
            }
            return details

    async def _qdrant_call(
        self, operation: str, call: Callable[[], Awaitable[T]]
    ) -> T:
        self._ensure_open()
        try:
            return await self._circuit_breaker.call(call)
        except DependencyUnavailable:
            raise
        except QdrantStoreError:
            raise
        except Exception as exc:
            raise QdrantStoreError(
                f"Qdrant operation failed: {operation}",
                operation=operation,
                collection=self.collection_name,
                retryable=True,
                details={"cause_type": type(exc).__name__},
            ) from exc

    def _ensure_open(self) -> None:
        if self._closed:
            raise QdrantStoreError(
                "Qdrant store is closed",
                operation="client_lifecycle",
                collection=self.collection_name,
                retryable=False,
            )

    def _point_id(self, chunk_id: str) -> UUID:
        return uuid5(_POINT_ID_NAMESPACE, f"{self.collection_name}:{chunk_id}")

    def _validate_dense_vectors(
        self,
        vectors: Sequence[Sequence[float]],
        *,
        expected_count: int,
        operation: str,
    ) -> list[list[float]]:
        if len(vectors) != expected_count:
            raise self._encoding_error(
                operation,
                f"dense encoder returned {len(vectors)} vectors; expected {expected_count}",
            )

        normalized: list[list[float]] = []
        for index, vector in enumerate(vectors):
            if len(vector) != self.dense_encoder.dimension:
                raise self._encoding_error(
                    operation,
                    "dense vector dimension mismatch at position "
                    f"{index}: {len(vector)} != {self.dense_encoder.dimension}",
                )
            try:
                values = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise self._encoding_error(
                    operation, f"dense vector {index} contains a non-numeric value"
                ) from exc
            if not all(math.isfinite(value) for value in values):
                raise self._encoding_error(
                    operation, f"dense vector {index} contains a non-finite value"
                )
            normalized.append(values)
        return normalized

    def _validate_sparse_vector(
        self, vector: SparseVector, *, operation: str
    ) -> SparseVector:
        assert self.sparse_encoder is not None
        indices = list(vector.indices)
        try:
            values = [float(value) for value in vector.values]
        except (TypeError, ValueError) as exc:
            raise self._encoding_error(
                operation, "sparse vector contains a non-numeric value"
            ) from exc
        valid_indices = (
            len(indices) == len(values)
            and indices == sorted(indices)
            and len(indices) == len(set(indices))
            and all(
                isinstance(index, int)
                and not isinstance(index, bool)
                and 0 <= index < min(self.sparse_encoder.dimensions, _UINT32_LIMIT)
                for index in indices
            )
        )
        if not valid_indices:
            raise self._encoding_error(
                operation,
                "sparse vector indices must be unique, sorted, in-range uint32 values",
            )
        if not all(math.isfinite(value) for value in values):
            raise self._encoding_error(
                operation, "sparse vector contains a non-finite value"
            )
        return SparseVector(indices=indices, values=values)

    def _encoding_error(self, operation: str, reason: str) -> QdrantStoreError:
        return QdrantStoreError(
            f"Invalid vector produced for Qdrant: {reason}",
            operation=operation,
            collection=self.collection_name,
            retryable=False,
        )

    def _decode_query_response(
        self, response: object, *, branch: SearchBranch
    ) -> list[SearchHit]:
        points = _read(response, "points")
        if not isinstance(points, Sequence) or isinstance(points, str | bytes):
            raise QdrantStoreError(
                "Qdrant query response did not contain a point sequence",
                operation=f"decode_{branch}_results",
                collection=self.collection_name,
                retryable=False,
            )
        return [self._payload_to_hit(point, branch=branch) for point in points]

    def _payload_to_hit(self, point: object, *, branch: SearchBranch) -> SearchHit:
        payload = _read(point, "payload")
        score = _read(point, "score")
        operation = f"decode_{branch}_result"
        if not isinstance(payload, Mapping):
            raise QdrantStoreError(
                "Qdrant result is missing its payload",
                operation=operation,
                collection=self.collection_name,
                retryable=False,
            )
        if isinstance(score, bool) or not isinstance(score, int | float):
            raise QdrantStoreError(
                "Qdrant result has a non-numeric score",
                operation=operation,
                collection=self.collection_name,
                retryable=False,
            )
        numeric_score = float(score)
        if not math.isfinite(numeric_score):
            raise QdrantStoreError(
                "Qdrant result has a non-finite score",
                operation=operation,
                collection=self.collection_name,
                retryable=False,
            )

        required = (
            "canonical_doc_id",
            "parent_id",
            "chunk_id",
            "text",
            "language",
            "strategy",
            "span_start",
            "span_end",
        )
        missing = [field for field in required if field not in payload]
        metadata = payload.get("metadata", {})
        if missing or not isinstance(metadata, Mapping):
            reason = (
                f"missing required payload fields: {', '.join(missing)}"
                if missing
                else "payload metadata must be an object"
            )
            raise QdrantStoreError(
                f"Qdrant result payload is invalid: {reason}",
                operation=operation,
                collection=self.collection_name,
                retryable=False,
            )

        hit_data: dict[str, Any] = {
            field: payload[field] for field in required
        }
        hit_data.update(
            {
                "score": numeric_score,
                "dense_score": numeric_score if branch == "dense" else None,
                "sparse_score": numeric_score if branch == "sparse" else None,
                "metadata": dict(metadata),
            }
        )
        language = str(payload["language"])
        if language in {"hi", "mr"} and isinstance(payload.get("translated_text"), str):
            hit_data["parent_text"] = payload["translated_text"]
        elif language == "hi-en":
            hit_data["parent_text"] = payload["text"]
        elif isinstance(payload.get("english_text"), str):
            hit_data["parent_text"] = payload["english_text"]
        try:
            return SearchHit.model_validate(hit_data)
        except (ValidationError, TypeError, ValueError) as exc:
            raise QdrantStoreError(
                "Qdrant result payload failed SearchHit validation",
                operation=operation,
                collection=self.collection_name,
                retryable=False,
                details={"cause_type": type(exc).__name__},
            ) from exc

    def _collection_schema_errors(
        self, info: object, *, require_payload_indexes: bool
    ) -> list[str]:
        errors: list[str] = []
        config = _read(info, "config")
        params = _read(config, "params")

        dense_configs = _as_mapping(_read(params, "vectors"))
        if set(dense_configs) != {self.dense_vector_name}:
            errors.append(
                "dense vector names differ: "
                f"expected [{self.dense_vector_name}], got {sorted(dense_configs)}"
            )
        else:
            dense_config = dense_configs[self.dense_vector_name]
            if _read(dense_config, "size") != self.dense_encoder.dimension:
                errors.append(
                    "dense vector size differs: "
                    f"expected {self.dense_encoder.dimension}, "
                    f"got {_read(dense_config, 'size')}"
                )
            if _enum_value(_read(dense_config, "distance")) != models.Distance.COSINE.value:
                errors.append("dense vector distance must be Cosine")

        sparse_configs = _as_mapping(_read(params, "sparse_vectors"))
        expected_sparse_names = (
            {self.sparse_vector_name} if self.sparse_enabled else set()
        )
        if set(sparse_configs) != expected_sparse_names:
            errors.append(
                "sparse vector names differ: "
                f"expected {sorted(expected_sparse_names)}, got {sorted(sparse_configs)}"
            )
        elif self.sparse_enabled:
            sparse_config = sparse_configs[self.sparse_vector_name]
            modifier = _read(sparse_config, "modifier")
            if modifier is not None:
                errors.append(
                    "sparse vector modifier must be unset because the encoder applies TF-IDF"
                )

        metadata = _as_mapping(_read(config, "metadata"))
        for key, expected in self._expected_metadata.items():
            if key not in metadata:
                errors.append(f"collection metadata is missing {key}")
            elif metadata[key] != expected:
                errors.append(
                    f"collection metadata {key} differs: expected {expected!r}, "
                    f"got {metadata[key]!r}"
                )

        payload_schema = _as_mapping(_read(info, "payload_schema"))
        for field_name in ("strategy", "language"):
            if field_name not in payload_schema:
                if require_payload_indexes:
                    errors.append(f"{field_name} payload index is missing")
            elif (
                _enum_value(_read(payload_schema[field_name], "data_type"))
                != models.PayloadSchemaType.KEYWORD.value
            ):
                errors.append(f"{field_name} payload index must have keyword type")
        return errors

    def _schema_error(self, errors: Sequence[str]) -> QdrantStoreError:
        return QdrantStoreError(
            "Existing Qdrant collection is incompatible; refusing destructive recreation",
            operation="validate_collection_schema",
            collection=self.collection_name,
            retryable=False,
            details={"schema_errors": list(errors)},
        )


def _read(value: object, field: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _enum_value(value: object) -> Any:
    return getattr(value, "value", value)


def _optimizer_status(value: object) -> str | None:
    enum_value = _enum_value(value)
    if isinstance(enum_value, str):
        return enum_value
    error = _read(value, "error")
    return f"error: {error}" if error else None


def _validate_search_input(query: str, limit: int) -> str:
    if limit <= 0:
        raise ValueError("limit must be positive")
    prepared = query.strip()
    if not prepared:
        raise ValueError("query must be non-empty")
    return prepared


def _payload_filter(
    strategies: Sequence[ChunkStrategy],
    *,
    languages: Sequence[Language] | None,
) -> models.Filter | None:
    values = sorted({strategy.value for strategy in strategies})
    if not values:
        return None
    language_values = (
        sorted({language.value for language in languages})
        if languages is not None
        else None
    )
    if language_values == []:
        return None
    must: list[models.Condition] = [
        models.FieldCondition(
            key="strategy",
            match=models.MatchAny(any=values),
        )
    ]
    if language_values is not None:
        must.append(
            models.FieldCondition(
                key="language",
                match=models.MatchAny(any=language_values),
            )
        )
    return models.Filter(must=must)
