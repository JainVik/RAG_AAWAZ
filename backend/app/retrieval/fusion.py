from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from app.domain.models import SearchHit


def reciprocal_rank_fusion(
    ranked_results: Mapping[str, Sequence[SearchHit]],
    *,
    weights: Mapping[str, float] | None = None,
    k: int = 60,
) -> list[SearchHit]:
    if k <= 0:
        raise ValueError("RRF k must be positive")
    weights = weights or {}
    fused_scores: defaultdict[str, float] = defaultdict(float)
    hits: dict[str, SearchHit] = {}
    source_ranks: defaultdict[str, dict[str, int]] = defaultdict(dict)
    source_scores: defaultdict[str, dict[str, float]] = defaultdict(dict)

    for source in sorted(ranked_results):
        weight = weights.get(source, 1.0)
        for rank, hit in enumerate(ranked_results[source], start=1):
            fused_scores[hit.chunk_id] += weight / (k + rank)
            hits.setdefault(hit.chunk_id, hit)
            source_ranks[hit.chunk_id][source] = rank
            source_scores[hit.chunk_id][source] = hit.score

    total_weight = sum(weights.get(source, 1.0) for source in ranked_results)
    maximum_rrf = total_weight / (k + 1) if total_weight else 1.0
    fused: list[SearchHit] = []
    for chunk_id, score in fused_scores.items():
        original = hits[chunk_id]
        scores = source_scores[chunk_id]
        fused.append(
            original.model_copy(
                update={
                    "score": score / maximum_rrf,
                    "dense_score": scores.get("dense", original.dense_score),
                    "sparse_score": scores.get("sparse", original.sparse_score),
                    "rank_sources": source_ranks[chunk_id],
                }
            )
        )
    return sorted(fused, key=lambda item: (-item.score, item.parent_id, item.chunk_id))


def evidence_agreement(
    dense_hits: Sequence[SearchHit], sparse_hits: Sequence[SearchHit], *, top_k: int = 10
) -> float:
    """Parent overlap weighted by reciprocal rank consistency, bounded to [0, 1]."""

    def best_parent_ranks(hits: Sequence[SearchHit]) -> dict[str, int]:
        ranks: dict[str, int] = {}
        for rank, hit in enumerate(hits[:top_k], start=1):
            ranks[hit.parent_id] = min(rank, ranks.get(hit.parent_id, rank))
        return ranks

    dense_ranks = best_parent_ranks(dense_hits)
    sparse_ranks = best_parent_ranks(sparse_hits)
    shared = dense_ranks.keys() & sparse_ranks.keys()
    if not shared:
        return 0.0
    overlap = len(shared) / max(1, len(dense_ranks.keys() | sparse_ranks.keys()))
    consistency = sum(
        1.0 - abs(dense_ranks[parent] - sparse_ranks[parent]) / max(1, top_k - 1)
        for parent in shared
    ) / len(shared)
    return max(0.0, min(1.0, 0.5 * overlap + 0.5 * consistency))
