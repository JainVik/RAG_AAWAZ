from __future__ import annotations

import pytest
from qdrant_client import AsyncQdrantClient

from app.core.config import Settings
from app.domain.enums import ChunkStrategy
from app.domain.models import CorpusDocument
from app.embeddings.dense import HashingDenseEncoder
from app.embeddings.sparse_char_ngram import SparseCharNgramEncoder
from app.ingestion.chunk_factory import ChunkFactory
from app.retrieval.qdrant_store import QdrantStore


@pytest.mark.asyncio
async def test_real_qdrant_client_local_dense_and_sparse_round_trip() -> None:
    """Exercise qdrant-client's local engine; this is not a server readiness claim."""

    settings = Settings(
        rag_target_unique_passages=10,
        rag_development_passages=1,
        dense_vector_size=64,
        qdrant_collection="local_client_integration",
    )
    document = CorpusDocument(
        canonical_doc_id="goa",
        parent_id="goa",
        english_text="Goa became an Indian state in 1987. Panaji is its capital.",
        translated_text="गोवा 1987 में भारत का राज्य बना। पणजी इसकी राजधानी है।",
        translation_language="hin_Deva",
    )
    chunks = ChunkFactory().all_enabled(document, enable_semantic=False)
    sparse = SparseCharNgramEncoder(dimensions=10_007).fit(
        chunk.text for chunk in chunks
    )
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantStore(
        settings,
        HashingDenseEncoder(dimension=64),
        sparse,
        client=client,
    )

    try:
        assert await store.upsert_chunks(chunks, batch_size=3) == len(chunks)
        dense_hits = await store.search_dense(
            "When did Goa become a state?",
            strategies=(ChunkStrategy.ATOMIC, ChunkStrategy.SENTENCE_WINDOW),
            limit=5,
        )
        sparse_hits = await store.search_sparse(
            "Goa 1987",
            strategies=(ChunkStrategy.ATOMIC, ChunkStrategy.SENTENCE_WINDOW),
            limit=5,
        )
    finally:
        await store.close()

    assert dense_hits and dense_hits[0].parent_id == "goa"
    assert sparse_hits and sparse_hits[0].parent_id == "goa"
    assert dense_hits[0].dense_score is not None
    assert sparse_hits[0].sparse_score is not None
