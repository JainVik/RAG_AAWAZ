from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from qdrant_client import models

from app.core.config import Settings
from app.core.errors import DependencyUnavailable
from app.domain.enums import ChunkStrategy, ErrorCode, Language, PipelineState
from app.domain.models import Chunk, SparseVector
from app.harness.circuit_breaker import CircuitBreaker, CircuitState
from app.retrieval.qdrant_store import QdrantStore, QdrantStoreError


class FakeDenseEncoder:
    dimension = 3

    def __init__(self) -> None:
        self.query_calls: list[list[str]] = []
        self.passage_calls: list[list[str]] = []

    async def encode_queries(self, texts: list[str]) -> list[list[float]]:
        self.query_calls.append(list(texts))
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def encode_passages(self, texts: list[str]) -> list[list[float]]:
        self.passage_calls.append(list(texts))
        return [
            [float(index + 1), float(len(text)), float(index + len(text))]
            for index, text in enumerate(texts)
        ]


class FakeSparseEncoder:
    dimensions = 128
    min_n = 3
    max_n = 5
    document_count = 3

    def encode(self, text: str) -> SparseVector:
        return SparseVector(indices=[1, 7], values=[0.75, float(len(text)) / 10.0])


def _settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "qdrant_collection": "test_chunks",
        "rag_dense_model": "test/dense-model",
        "dense_vector_size": 3,
        "rag_target_unique_passages": 10,
        "rag_development_passages": 10,
    }
    values.update(updates)
    return Settings(
        **values,  # type: ignore[arg-type]
    )


def _client() -> SimpleNamespace:
    return SimpleNamespace(
        collection_exists=AsyncMock(),
        create_collection=AsyncMock(return_value=True),
        get_collection=AsyncMock(),
        create_payload_index=AsyncMock(),
        upsert=AsyncMock(),
        query_points=AsyncMock(),
        search=AsyncMock(),
        info=AsyncMock(return_value=SimpleNamespace(title="qdrant", version="1.19.0")),
        count=AsyncMock(return_value=SimpleNamespace(count=0)),
        close=AsyncMock(),
        recreate_collection=AsyncMock(),
        delete_collection=AsyncMock(),
    )


def _store(
    client: SimpleNamespace,
    *,
    breaker: CircuitBreaker | None = None,
    sparse_enabled: bool = True,
) -> QdrantStore:
    return QdrantStore(
        _settings(rag_enable_sparse=sparse_enabled),
        FakeDenseEncoder(),
        FakeSparseEncoder() if sparse_enabled else None,
        client=client,
        circuit_breaker=breaker,
    )


def _collection_info(
    store: QdrantStore,
    *,
    dense_size: int = 3,
    metadata: dict[str, object] | None = None,
    payload_schema: dict[str, object] | None = None,
    status: models.CollectionStatus = models.CollectionStatus.GREEN,
) -> SimpleNamespace:
    if metadata is None:
        metadata = store.expected_collection_metadata
    if payload_schema is None:
        payload_schema = {
            "strategy": SimpleNamespace(data_type=models.PayloadSchemaType.KEYWORD),
            "language": SimpleNamespace(data_type=models.PayloadSchemaType.KEYWORD),
        }
    return SimpleNamespace(
        status=status,
        optimizer_status=models.OptimizersStatusOneOf.OK,
        points_count=2,
        indexed_vectors_count=2,
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors={
                    store.dense_vector_name: models.VectorParams(
                        size=dense_size,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors=(
                    {store.sparse_vector_name: models.SparseVectorParams()}
                    if store.sparse_enabled
                    else {}
                ),
            ),
            metadata=metadata,
        ),
        payload_schema=payload_schema,
    )


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        canonical_doc_id=f"doc-{chunk_id}",
        parent_id="parent-1",
        chunk_id=chunk_id,
        language=Language.ENGLISH,
        strategy=ChunkStrategy.ATOMIC,
        text=text,
        span_start=0,
        span_end=len(text),
        english_text=text,
        metadata={"source": "fixture"},
    )


@pytest.mark.asyncio
async def test_initialize_creates_named_vectors_and_filter_payload_indexes() -> None:
    client = _client()
    store = _store(client)
    client.collection_exists.return_value = False
    client.get_collection.return_value = _collection_info(
        store, payload_schema={}
    )

    await store.initialize()

    create_kwargs = client.create_collection.await_args.kwargs
    assert set(create_kwargs["vectors_config"]) == {store.dense_vector_name}
    dense = create_kwargs["vectors_config"][store.dense_vector_name]
    assert dense.size == 3
    assert dense.distance is models.Distance.COSINE
    assert set(create_kwargs["sparse_vectors_config"]) == {
        store.sparse_vector_name
    }
    assert (
        create_kwargs["sparse_vectors_config"][store.sparse_vector_name].modifier
        is None
    )
    assert create_kwargs["metadata"] == store.expected_collection_metadata
    assert [call.kwargs["field_name"] for call in client.create_payload_index.await_args_list] == [
        "strategy",
        "language",
    ]
    assert all(
        call.kwargs["field_schema"] is models.PayloadSchemaType.KEYWORD
        and call.kwargs["collection_name"] == "test_chunks"
        and call.kwargs["wait"] is True
        for call in client.create_payload_index.await_args_list
    )
    client.recreate_collection.assert_not_awaited()
    client.delete_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_sparse_disabled_uses_dense_only_schema_upsert_and_search() -> None:
    client = _client()
    store = _store(client, sparse_enabled=False)
    client.collection_exists.return_value = False
    client.get_collection.return_value = _collection_info(store, payload_schema={})

    await store.initialize()

    create_kwargs = client.create_collection.await_args.kwargs
    assert create_kwargs["sparse_vectors_config"] is None
    assert store.expected_collection_metadata["sparse_enabled"] is False
    assert "sparse_vector_name" not in store.expected_collection_metadata

    await store.upsert_chunks([_chunk("dense-only", "dense evidence")])
    point = client.upsert.await_args.kwargs["points"][0]
    assert set(point.vector) == {store.dense_vector_name}

    payload = _chunk("dense-only", "dense evidence").model_dump(mode="json")
    client.query_points.return_value = SimpleNamespace(
        points=[SimpleNamespace(score=0.8, payload=payload)]
    )
    dense_hits = await store.search_dense(
        "query",
        strategies=[ChunkStrategy.ATOMIC],
        languages=[Language.ENGLISH],
        limit=1,
    )
    query_count = client.query_points.await_count
    sparse_hits = await store.search_sparse(
        "query",
        strategies=[ChunkStrategy.ATOMIC],
        languages=[Language.ENGLISH],
        limit=1,
    )
    assert dense_hits[0].dense_score == pytest.approx(0.8)
    assert sparse_hits == []
    assert client.query_points.await_count == query_count


@pytest.mark.asyncio
async def test_existing_incompatible_collection_is_never_recreated() -> None:
    client = _client()
    store = _store(client)
    client.collection_exists.return_value = True
    client.get_collection.return_value = _collection_info(store, dense_size=99)

    with pytest.raises(QdrantStoreError) as caught:
        await store.initialize()

    assert caught.value.code is ErrorCode.QDRANT_ERROR
    assert caught.value.state is PipelineState.FAILED
    assert not caught.value.retryable
    assert "dense vector size differs" in " ".join(
        caught.value.details["schema_errors"]
    )
    client.create_collection.assert_not_awaited()
    client.create_payload_index.assert_not_awaited()
    client.recreate_collection.assert_not_awaited()
    client.delete_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_batches_are_complete_sorted_and_deterministic() -> None:
    client = _client()
    store = _store(client)
    client.collection_exists.return_value = True
    client.get_collection.return_value = _collection_info(store)
    chunks = [_chunk("chunk-b", "beta"), _chunk("chunk-a", "alpha"), _chunk("chunk-c", "gamma")]

    assert await store.upsert_chunks(chunks, batch_size=2) == 3
    assert await store.upsert_chunks(chunks, batch_size=2) == 3

    assert client.upsert.await_count == 4
    first_run = client.upsert.await_args_list[:2]
    second_run = client.upsert.await_args_list[2:]
    first_points = [point for call in first_run for point in call.kwargs["points"]]
    second_points = [point for call in second_run for point in call.kwargs["points"]]
    assert [point.payload["chunk_id"] for point in first_points] == [
        "chunk-a",
        "chunk-b",
        "chunk-c",
    ]
    assert [point.id for point in first_points] == [point.id for point in second_points]

    expected = {chunk.chunk_id: chunk.model_dump(mode="json") for chunk in chunks}
    for point in first_points:
        assert point.payload == expected[point.payload["chunk_id"]]
        assert set(point.vector) == {
            store.dense_vector_name,
            store.sparse_vector_name,
        }
        assert isinstance(point.vector[store.sparse_vector_name], models.SparseVector)
    assert all(call.kwargs["wait"] is True for call in client.upsert.await_args_list)


@pytest.mark.asyncio
async def test_dense_and_sparse_search_use_query_points_and_validate_hits() -> None:
    client = _client()
    store = _store(client)
    client.collection_exists.return_value = True
    client.get_collection.return_value = _collection_info(store)
    payload = _chunk("chunk-a", "evidence").model_dump(mode="json")
    client.query_points.side_effect = [
        SimpleNamespace(points=[SimpleNamespace(score=0.91, payload=payload)]),
        SimpleNamespace(points=[SimpleNamespace(score=0.72, payload=payload)]),
    ]
    strategies = [ChunkStrategy.SEMANTIC_SECTION, ChunkStrategy.ATOMIC]

    dense_hits = await store.search_dense(
        " query ", strategies=strategies, limit=4, languages=[Language.HINDI]
    )
    sparse_hits = await store.search_sparse(
        "query", strategies=strategies, limit=5, languages=[Language.HINDI]
    )

    dense_call, sparse_call = client.query_points.await_args_list
    assert dense_call.kwargs["using"] == store.dense_vector_name
    assert dense_call.kwargs["query"] == [0.1, 0.2, 0.3]
    assert dense_call.kwargs["with_payload"] is True
    assert dense_call.kwargs["with_vectors"] is False
    dense_match = dense_call.kwargs["query_filter"].must[0].match
    assert dense_match.any == ["atomic", "semantic_section"]
    dense_language_match = dense_call.kwargs["query_filter"].must[1].match
    assert dense_language_match.any == ["hi"]
    assert sparse_call.kwargs["using"] == store.sparse_vector_name
    assert isinstance(sparse_call.kwargs["query"], models.SparseVector)
    assert sparse_call.kwargs["limit"] == 5
    client.search.assert_not_awaited()

    assert dense_hits[0].score == pytest.approx(0.91)
    assert dense_hits[0].dense_score == pytest.approx(0.91)
    assert dense_hits[0].sparse_score is None
    assert sparse_hits[0].score == pytest.approx(0.72)
    assert sparse_hits[0].sparse_score == pytest.approx(0.72)
    assert sparse_hits[0].dense_score is None


@pytest.mark.asyncio
async def test_invalid_qdrant_payload_fails_closed() -> None:
    client = _client()
    store = _store(client)
    client.collection_exists.return_value = True
    client.get_collection.return_value = _collection_info(store)
    payload = _chunk("chunk-a", "evidence").model_dump(mode="json")
    del payload["text"]
    client.query_points.return_value = SimpleNamespace(
        points=[SimpleNamespace(score=0.8, payload=payload)]
    )

    with pytest.raises(QdrantStoreError) as caught:
        await store.search_dense(
            "query", strategies=[ChunkStrategy.ATOMIC], limit=3
        )

    assert not caught.value.retryable
    assert caught.value.details["operation"] == "decode_dense_result"


@pytest.mark.asyncio
async def test_transport_errors_are_structured_and_open_the_circuit() -> None:
    client = _client()
    breaker = CircuitBreaker("qdrant", failure_threshold=1, recovery_timeout_s=60)
    store = _store(client, breaker=breaker)
    client.collection_exists.side_effect = OSError("connection refused")

    with pytest.raises(QdrantStoreError) as first:
        await store.initialize()

    assert first.value.retryable
    assert first.value.state is PipelineState.DEPENDENCY_UNAVAILABLE
    assert first.value.details == {
        "operation": "collection_exists",
        "collection": "test_chunks",
        "cause_type": "OSError",
    }
    assert breaker.state is CircuitState.OPEN
    with pytest.raises(DependencyUnavailable):
        await store.initialize()


@pytest.mark.asyncio
async def test_readiness_is_detailed_and_never_provisions() -> None:
    client = _client()
    store = _store(client)
    client.collection_exists.return_value = True
    client.get_collection.return_value = _collection_info(store)
    client.count.return_value = SimpleNamespace(count=2)

    ready = await store.readiness_details(expected_points=2)

    assert ready["ready"] is True
    assert ready["version"] == "1.19.0"
    assert ready["status"] == "green"
    assert ready["optimizer_status"] == "ok"
    assert ready["exact_points_count"] == 2
    assert ready["point_count_matches"] is True
    client.count.assert_awaited_once_with(collection_name="test_chunks", exact=True)
    client.create_collection.assert_not_awaited()
    client.create_payload_index.assert_not_awaited()

    client.get_collection.return_value = _collection_info(
        store,
        metadata={"schema_version": "wrong"},
        status=models.CollectionStatus.RED,
    )
    not_ready = await store.readiness_details()
    assert not_ready["ready"] is False
    assert not_ready["schema_valid"] is False
    assert not_ready["status"] == "red"


@pytest.mark.asyncio
async def test_close_is_async_and_idempotent() -> None:
    client = _client()
    store = _store(client)

    await store.close()
    await store.close()

    client.close.assert_awaited_once_with()
    with pytest.raises(QdrantStoreError) as caught:
        await store.initialize()
    assert caught.value.details["operation"] == "client_lifecycle"
