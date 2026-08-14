from __future__ import annotations

import pytest

from app.core.deadlines import Deadline
from app.core.errors import DependencyUnavailable, PipelineError
from app.domain.enums import ChunkStrategy, ErrorCode, Language
from app.domain.models import SearchHit
from app.retrieval.fusion import evidence_agreement, reciprocal_rank_fusion
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.late_chunking import select_evidence_windows
from app.retrieval.parent_dedup import deduplicate_by_parent
from app.retrieval.router import TideRouter


def hit(chunk: str, parent: str, score: float) -> SearchHit:
    return SearchHit(
        canonical_doc_id=parent,
        parent_id=parent,
        chunk_id=chunk,
        text=f"evidence {chunk}",
        language=Language.ENGLISH,
        strategy=ChunkStrategy.ATOMIC,
        span_start=0,
        span_end=10,
        score=score,
    )


def test_fusion_is_deterministic_and_retains_branch_scores() -> None:
    dense = [hit("a", "p1", 0.9), hit("b", "p2", 0.8)]
    sparse = [hit("b", "p2", 4.0), hit("a", "p1", 3.0)]
    first = reciprocal_rank_fusion(
        {"dense": dense, "sparse": sparse}, weights={"dense": 0.6, "sparse": 0.4}
    )
    second = reciprocal_rank_fusion(
        {"sparse": sparse, "dense": dense}, weights={"dense": 0.6, "sparse": 0.4}
    )

    assert first == second
    assert first[0].dense_score is not None
    assert first[0].sparse_score is not None
    assert 0.0 <= first[0].score <= 1.0


def test_parent_dedup_prevents_duplicate_evidence() -> None:
    hits = [hit("a", "same", 1.0), hit("b", "same", 0.9), hit("c", "other", 0.8)]
    result = deduplicate_by_parent(hits, limit=3)
    assert [item.parent_id for item in result] == ["same", "other"]


def test_evidence_agreement_is_bounded_and_uses_parent_overlap() -> None:
    assert evidence_agreement([hit("a", "p1", 1)], [hit("b", "p1", 1)]) == 1.0
    assert evidence_agreement([hit("a", "p1", 1)], [hit("b", "p2", 1)]) == 0.0


def test_evidence_agreement_uses_best_rank_for_duplicate_parent_chunks() -> None:
    dense = [hit("first", "p1", 1.0), hit("second", "p1", 0.9)]
    sparse = [hit("sparse", "p1", 1.0)]

    assert evidence_agreement(dense, sparse) == 1.0


def test_router_selects_code_mixed_and_short_factual_paths() -> None:
    router = TideRouter()
    mixed = router.route("Goa राज्य कब बना 1987?")
    factual = router.route("When was Goa formed?")

    assert mixed.language == Language.CODE_MIXED
    assert ChunkStrategy.BILINGUAL_PAIRED in mixed.strategies
    assert factual.category == "short_factual"
    assert factual.sparse_weight > factual.dense_weight


@pytest.mark.parametrize(("partial", "final"), [("When", "When?"), ("How", "How?")])
def test_punctuation_equivalent_transcripts_have_identical_route_plans(
    partial: str, final: str
) -> None:
    router = TideRouter()

    assert router.route(partial) == router.route(final)


def test_router_excludes_disabled_dense_and_sparse_strategies() -> None:
    router = TideRouter(
        enabled_strategies=(ChunkStrategy.ATOMIC,),
        enable_sparse=False,
    )

    plan = router.route("Goa rajya mixed query")

    assert plan.strategies == (ChunkStrategy.ATOMIC,)
    assert plan.dense_weight == 1.0
    assert plan.sparse_weight == 0.0
    assert plan.sparse_limit == 0

    bilingual_only = TideRouter(enabled_strategies=(ChunkStrategy.BILINGUAL_PAIRED,)).route(
        "English query"
    )
    assert bilingual_only.strategies == (ChunkStrategy.BILINGUAL_PAIRED,)
    assert bilingual_only.representation_languages == (
        Language.ENGLISH,
        Language.CODE_MIXED,
    )

    with pytest.raises(ValueError, match="at least one dense chunk strategy"):
        TideRouter(enabled_strategies=())


class _DenseSearch:
    async def search_dense(
        self,
        query: str,
        *,
        strategies: object,
        limit: int,
        languages: object = None,
    ) -> list[SearchHit]:
        del query, strategies, limit, languages
        return [hit("dense", "parent", 0.8)]


class _CountingSparseSearch:
    def __init__(self) -> None:
        self.calls = 0

    async def search_sparse(
        self,
        query: str,
        *,
        strategies: object,
        limit: int,
        languages: object = None,
    ) -> list[SearchHit]:
        del query, strategies, limit, languages
        self.calls += 1
        return [hit("sparse", "parent", 0.8)]


class _FailingSparseSearch:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def search_sparse(
        self,
        query: str,
        *,
        strategies: object,
        limit: int,
        languages: object = None,
    ) -> list[SearchHit]:
        del query, strategies, limit, languages
        raise self.error


@pytest.mark.asyncio
async def test_hybrid_retriever_does_not_schedule_disabled_sparse_branch() -> None:
    sparse = _CountingSparseSearch()
    retriever = HybridRetriever(_DenseSearch(), sparse)
    plan = TideRouter(enable_sparse=False).route("general question")

    result = await retriever.retrieve("general question", plan, Deadline.after_ms(500, 450))

    assert sparse.calls == 0
    assert result.sparse_hits == ()
    assert result.sparse_failed is False


@pytest.mark.asyncio
async def test_hybrid_retriever_degrades_only_retryable_sparse_dependency_failures() -> None:
    plan = TideRouter().route("When was Goa formed?")
    retryable = HybridRetriever(
        _DenseSearch(), _FailingSparseSearch(DependencyUnavailable("qdrant"))
    )
    result = await retryable.retrieve(
        "When was Goa formed?", plan, Deadline.after_ms(500, 450)
    )
    assert result.sparse_failed is True

    corrupt = PipelineError(
        code=ErrorCode.QDRANT_ERROR,
        message="corrupt sparse payload",
        retryable=False,
    )
    nonretryable = HybridRetriever(_DenseSearch(), _FailingSparseSearch(corrupt))
    with pytest.raises(PipelineError, match="corrupt sparse payload"):
        await nonretryable.retrieve(
            "When was Goa formed?", plan, Deadline.after_ms(500, 450)
        )


def test_late_chunking_segments_full_parent_after_child_hit() -> None:
    child = hit("child", "parent", 0.9).model_copy(
        update={
            "text": "First unrelated sentence.",
            "parent_text": "First unrelated sentence. Goa became a state in 1987.",
            "span_start": 0,
            "span_end": 25,
        }
    )
    selected = select_evidence_windows(
        "When did Goa become a state?", [child], limit=1, sentences_per_window=1
    )

    assert selected[0].text == "Goa became a state in 1987."
    assert selected[0].span_start == len("First unrelated sentence. ")
