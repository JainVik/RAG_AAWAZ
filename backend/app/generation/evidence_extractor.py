from __future__ import annotations

from collections.abc import Sequence

from app.domain.models import SearchHit


def choose_supporting_hits(hits: Sequence[SearchHit], limit: int = 2) -> list[SearchHit]:
    return sorted(hits, key=lambda hit: (-hit.score, hit.parent_id, hit.span_start))[:limit]

