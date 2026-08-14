from __future__ import annotations

from collections.abc import Sequence

from app.domain.models import SearchHit


def deduplicate_by_parent(hits: Sequence[SearchHit], limit: int) -> list[SearchHit]:
    selected: list[SearchHit] = []
    seen: set[str] = set()
    for hit in hits:
        if hit.parent_id in seen:
            continue
        seen.add(hit.parent_id)
        selected.append(hit)
        if len(selected) >= limit:
            break
    return selected

