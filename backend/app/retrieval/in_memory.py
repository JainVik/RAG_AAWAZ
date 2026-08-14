from __future__ import annotations

import math
from collections.abc import Sequence

from app.domain.enums import ChunkStrategy, Language
from app.domain.models import Chunk, SearchHit, SparseVector
from app.embeddings.dense import DenseEncoder
from app.embeddings.sparse_char_ngram import SparseCharNgramEncoder


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _sparse_dot(left: SparseVector, right: SparseVector) -> float:
    left_values = dict(zip(left.indices, left.values, strict=True))
    return sum(
        left_values.get(index, 0.0) * value
        for index, value in zip(right.indices, right.values, strict=True)
    )


class InMemoryHybridIndex:
    """Deterministic evaluation fake; production uses QdrantStore."""

    def __init__(
        self,
        chunks: Sequence[Chunk],
        dense_encoder: DenseEncoder,
        sparse_encoder: SparseCharNgramEncoder,
    ) -> None:
        self.chunks = list(chunks)
        self.dense_encoder = dense_encoder
        self.sparse_encoder = sparse_encoder.fit(chunk.text for chunk in chunks)
        self._dense_vectors: list[list[float]] = []
        self._sparse_vectors = [self.sparse_encoder.encode(chunk.text) for chunk in chunks]

    async def initialize(self) -> None:
        self._dense_vectors = await self.dense_encoder.encode_passages(
            [chunk.text for chunk in self.chunks]
        )

    @staticmethod
    def _hit(chunk: Chunk, score: float) -> SearchHit:
        if chunk.language.value in {"hi", "mr"}:
            parent_text = chunk.translated_text
        elif chunk.language.value == "hi-en":
            parent_text = chunk.text
        else:
            parent_text = chunk.english_text
        return SearchHit(
            canonical_doc_id=chunk.canonical_doc_id,
            parent_id=chunk.parent_id,
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            parent_text=parent_text,
            language=chunk.language,
            strategy=chunk.strategy,
            span_start=chunk.span_start,
            span_end=chunk.span_end,
            score=score,
            metadata=chunk.metadata,
        )

    async def search_dense(
        self,
        query: str,
        *,
        strategies: Sequence[ChunkStrategy],
        limit: int,
        languages: Sequence[Language] | None = None,
    ) -> list[SearchHit]:
        if not self._dense_vectors:
            await self.initialize()
        query_vector = (await self.dense_encoder.encode_queries([query]))[0]
        allowed = set(strategies)
        allowed_languages = set(languages) if languages is not None else None
        hits = []
        for chunk, vector in zip(self.chunks, self._dense_vectors, strict=True):
            if chunk.strategy not in allowed:
                continue
            if allowed_languages is not None and chunk.language not in allowed_languages:
                continue
            score = _dot(query_vector, vector)
            hits.append(self._hit(chunk, score).model_copy(update={"dense_score": score}))
        return sorted(hits, key=lambda item: (-item.score, item.chunk_id))[:limit]

    async def search_sparse(
        self,
        query: str,
        *,
        strategies: Sequence[ChunkStrategy],
        limit: int,
        languages: Sequence[Language] | None = None,
    ) -> list[SearchHit]:
        query_vector = self.sparse_encoder.encode(query)
        allowed = set(strategies)
        allowed_languages = set(languages) if languages is not None else None
        hits = []
        for chunk, vector in zip(self.chunks, self._sparse_vectors, strict=True):
            if chunk.strategy not in allowed:
                continue
            if allowed_languages is not None and chunk.language not in allowed_languages:
                continue
            score = _sparse_dot(query_vector, vector)
            if not math.isclose(score, 0.0):
                hits.append(self._hit(chunk, score).model_copy(update={"sparse_score": score}))
        return sorted(hits, key=lambda item: (-item.score, item.chunk_id))[:limit]
