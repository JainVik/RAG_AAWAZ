from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.domain.enums import ChunkStrategy, Language
from app.domain.models import SearchHit


class DenseSearcher(Protocol):
    async def search_dense(
        self,
        query: str,
        *,
        strategies: Sequence[ChunkStrategy],
        limit: int,
        languages: Sequence[Language] | None = None,
    ) -> list[SearchHit]: ...
