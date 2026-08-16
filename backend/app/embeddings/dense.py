from __future__ import annotations

import asyncio
import contextlib
import hashlib
import math
from collections.abc import Sequence
from typing import Literal, Protocol

import numpy as np


class DenseEncoder(Protocol):
    dimension: int

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def encode_passages(self, texts: Sequence[str]) -> list[list[float]]: ...


class SentenceTransformerDenseEncoder:
    """Frozen multilingual E5 encoder; model parameters are never trained."""

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        *,
        revision: str | None = None,
        backend: Literal["torch", "onnx", "openvino"] = "torch",
        device: str = "cpu",
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Install the embeddings extra to load the dense model") from exc
        self._model = SentenceTransformer(
            model_name,
            revision=revision,
            backend=backend,
            device=device,
        )
        self.model_name = model_name
        self.model_revision = revision
        self.dimension = int(self._model.get_sentence_embedding_dimension() or 384)
        self._inference_lock = asyncio.Lock()
        self._query_cache: dict[str, list[float]] = {}
        self._max_cache_size = 2048

    def _encode(self, texts: Sequence[str], prefix: str) -> list[list[float]]:
        if prefix == "query":
            results: list[list[float] | None] = [self._query_cache.get(text) for text in texts]
            missing_indices = [i for i, v in enumerate(results) if v is None]
            if not missing_indices:
                return [res for res in results if res is not None]
            missing_texts = [texts[i] for i in missing_indices]
            prepared = [f"query: {text}" for text in missing_texts]
            vectors = self._model.encode(
                prepared,
                batch_size=min(32, max(1, len(prepared))),
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            array = np.asarray(vectors, dtype=np.float32)
            for idx, row in zip(missing_indices, array, strict=True):
                vec = [float(val) for val in row]
                results[idx] = vec
                if len(self._query_cache) < self._max_cache_size:
                    self._query_cache[texts[idx]] = vec
            return [res for res in results if res is not None]

        prepared = [f"{prefix}: {text}" for text in texts]
        vectors = self._model.encode(
            prepared,
            batch_size=min(32, max(1, len(prepared))),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        array = np.asarray(vectors, dtype=np.float32)
        return [[float(value) for value in row] for row in array]

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._encode_serialized(texts, "query")

    async def encode_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._encode_serialized(texts, "passage")

    async def _encode_serialized(
        self, texts: Sequence[str], prefix: str
    ) -> list[list[float]]:
        """Keep cancelled speculative E5 work from running concurrently.

        A running ``to_thread`` call cannot be stopped. Shielding and draining it
        keeps this lock held until the CPU worker exits, so replacement partials
        and the final query queue behind at most one stale inference.
        """

        async with self._inference_lock:
            work = asyncio.create_task(asyncio.to_thread(self._encode, texts, prefix))
            try:
                return await asyncio.shield(work)
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    await work
                raise


class HashingDenseEncoder:
    """Deterministic test fake. It is never presented as a production embedding model."""

    def __init__(self, dimension: int = 64) -> None:
        self.dimension = dimension

    def _vector(self, text: str, prefix: str) -> list[float]:
        values = [0.0] * self.dimension
        for token in f"{prefix}: {text}".casefold().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            values[index] += sign
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text, "query") for text in texts]

    async def encode_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text, "passage") for text in texts]
