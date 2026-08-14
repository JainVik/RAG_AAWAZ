from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.deadlines import Deadline
from app.core.errors import DeadlineExceeded, PipelineError
from app.domain.models import SearchHit
from app.retrieval.dense_search import DenseSearcher
from app.retrieval.fusion import evidence_agreement, reciprocal_rank_fusion
from app.retrieval.parent_dedup import deduplicate_by_parent
from app.retrieval.router import RoutePlan
from app.retrieval.sparse_search import SparseSearcher


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    dense_hits: tuple[SearchHit, ...]
    sparse_hits: tuple[SearchHit, ...]
    fused_hits: tuple[SearchHit, ...]
    agreement: float
    sparse_failed: bool = False


class HybridRetriever:
    def __init__(
        self,
        dense_searcher: DenseSearcher,
        sparse_searcher: SparseSearcher | None,
        *,
        rrf_k: int = 60,
        final_limit: int = 5,
    ) -> None:
        self.dense_searcher = dense_searcher
        self.sparse_searcher = sparse_searcher
        self.rrf_k = rrf_k
        self.final_limit = final_limit

    async def retrieve(self, query: str, plan: RoutePlan, deadline: Deadline) -> RetrievalResult:
        dense_task = asyncio.create_task(
            self.dense_searcher.search_dense(
                query,
                strategies=plan.strategies,
                limit=plan.dense_limit,
                languages=plan.representation_languages,
            )
        )
        sparse_task = (
            asyncio.create_task(
                self.sparse_searcher.search_sparse(
                    query,
                    strategies=plan.strategies,
                    limit=plan.sparse_limit,
                    languages=plan.representation_languages,
                )
            )
            if (
                self.sparse_searcher is not None
                and plan.sparse_limit > 0
                and plan.sparse_weight > 0.0
            )
            else None
        )
        try:
            dense_hits = await asyncio.wait_for(
                dense_task, timeout=deadline.timeout_seconds(reserve_ms=15)
            )
            sparse_failed = False
            if sparse_task is None:
                sparse_hits: list[SearchHit] = []
            else:
                try:
                    sparse_hits = await asyncio.wait_for(
                        sparse_task, timeout=deadline.timeout_seconds(reserve_ms=10)
                    )
                except PipelineError as exc:
                    if not exc.retryable:
                        raise
                    sparse_failed = True
                    sparse_hits = []
                except TimeoutError:
                    sparse_failed = True
                    sparse_hits = []
            ranked = {"dense": dense_hits}
            weights = {"dense": plan.dense_weight}
            if sparse_hits:
                ranked["sparse"] = sparse_hits
                weights["sparse"] = plan.sparse_weight
            fused = reciprocal_rank_fusion(ranked, weights=weights, k=self.rrf_k)
            deduplicated = deduplicate_by_parent(fused, self.final_limit)
            agreement = evidence_agreement(dense_hits, sparse_hits) if sparse_hits else 0.0
            return RetrievalResult(
                dense_hits=tuple(dense_hits),
                sparse_hits=tuple(sparse_hits),
                fused_hits=tuple(deduplicated),
                agreement=agreement,
                sparse_failed=sparse_failed,
            )
        except TimeoutError as exc:
            raise DeadlineExceeded("Retrieval exceeded the remaining request budget") from exc
        finally:
            branch_tasks: list[asyncio.Task[list[SearchHit]]] = []
            for task in (dense_task, sparse_task):
                if task is None:
                    continue
                if not task.done():
                    task.cancel()
                branch_tasks.append(task)
            if branch_tasks:
                await asyncio.gather(*branch_tasks, return_exceptions=True)
