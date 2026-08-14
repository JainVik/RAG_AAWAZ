from __future__ import annotations

import asyncio
import time

import pytest

from app.core.config import Settings
from app.core.deadlines import Deadline
from app.core.errors import DependencyUnavailable
from app.domain.enums import ChunkStrategy, GuardrailReason, Language, PipelineState
from app.domain.models import CorpusDocument, SearchHit, Transcript
from app.embeddings.dense import HashingDenseEncoder
from app.embeddings.sparse_char_ngram import SparseCharNgramEncoder
from app.generation.grounded_generator import (
    ExtractiveGroundedGenerator,
    GeneratedAnswer,
)
from app.harness.orchestrator import PipelineOrchestrator
from app.ingestion.chunk_factory import ChunkFactory
from app.retrieval.hybrid import HybridRetriever, RetrievalResult
from app.retrieval.in_memory import InMemoryHybridIndex


def settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "rag_target_unique_passages": 10,
        "rag_development_passages": 1,
        "rag_deadline_ms": 1_000,
        "rag_fallback_at_ms": 900,
        "min_answer_score": 0.0,
        "min_score_margin": 0.0,
        "min_evidence_agreement": 0.0,
    }
    values.update(updates)
    return Settings(**values)


async def working_orchestrator() -> PipelineOrchestrator:
    document = CorpusDocument(
        canonical_doc_id="doc",
        parent_id="doc",
        english_text="Goa became a state in 1987. It is on India's west coast.",
        translated_text="गोवा 1987 में राज्य बना। यह भारत के पश्चिमी तट पर है।",
        translation_language="hin_Deva",
    )
    chunks = ChunkFactory().all_enabled(document, enable_semantic=False)
    index = InMemoryHybridIndex(
        chunks, HashingDenseEncoder(), SparseCharNgramEncoder(dimensions=10_007)
    )
    await index.initialize()
    retriever = HybridRetriever(index, index, final_limit=3)
    return PipelineOrchestrator(
        settings=settings(),
        retriever=retriever,
        generator=ExtractiveGroundedGenerator(),
    )


@pytest.mark.asyncio
async def test_final_text_path_returns_only_grounded_cited_answer() -> None:
    orchestrator = await working_orchestrator()
    response = await orchestrator.process_text("Explain Goa statehood", language=Language.ENGLISH)

    assert response.state == PipelineState.COMPLETED
    assert response.answer
    assert response.citations
    assert response.answer in " ".join(citation.text for citation in response.citations)


@pytest.mark.asyncio
async def test_final_answer_never_uses_partial_transcript_alone() -> None:
    orchestrator = await working_orchestrator()
    deadline = Deadline.after_ms(500, 400)
    partial = Transcript(
        text="Goa state",
        language=Language.ENGLISH,
        confidence=None,
        is_final=False,
        received_ns=time.perf_counter_ns(),
    )
    response = await orchestrator.process_transcript(partial, deadline=deadline)

    assert response.answer is None
    assert response.state == PipelineState.NEEDS_REPEAT


@pytest.mark.asyncio
async def test_genuine_provider_confidence_is_gated_when_available() -> None:
    orchestrator = await working_orchestrator()
    deadline = Deadline.after_ms(500, 400)
    low_confidence_final = Transcript(
        text="Goa statehood",
        language=Language.ENGLISH,
        confidence=0.1,
        is_final=True,
        received_ns=time.perf_counter_ns(),
    )
    response = await orchestrator.process_transcript(low_confidence_final, deadline=deadline)

    assert response.answer is None
    assert response.guardrail.reason == GuardrailReason.LOW_STT_CONFIDENCE


@pytest.mark.asyncio
async def test_stale_query_abstains_before_retrieval() -> None:
    orchestrator = await working_orchestrator()
    response = await orchestrator.process_text("Who is the current president?")

    assert response.answer is None
    assert response.guardrail.reason == GuardrailReason.STALE_CORPUS


class SlowDenseSearch:
    async def search_dense(
        self,
        query: str,
        *,
        strategies: object,
        limit: int,
        languages: object = None,
    ) -> list[object]:
        del query, strategies, limit, languages
        await asyncio.sleep(0.1)
        return []


@pytest.mark.asyncio
async def test_deadline_controller_stops_retrieval_and_returns_valid_schema() -> None:
    retriever = HybridRetriever(SlowDenseSearch(), None)  # type: ignore[arg-type]
    orchestrator = PipelineOrchestrator(
        settings=settings(rag_deadline_ms=30, rag_fallback_at_ms=20),
        retriever=retriever,
        generator=ExtractiveGroundedGenerator(),
    )
    response = await orchestrator.process_text("A question")

    assert response.state == PipelineState.DEADLINE_FALLBACK
    assert response.guardrail.reason == GuardrailReason.DEADLINE_EXCEEDED
    assert response.model_dump(mode="json")


class FailingRetriever:
    async def retrieve(self, query: str, plan: object, deadline: Deadline) -> object:
        del query, plan, deadline
        raise DependencyUnavailable("qdrant")


@pytest.mark.asyncio
async def test_dependency_failure_becomes_structured_terminal_state() -> None:
    orchestrator = PipelineOrchestrator(
        settings=settings(),
        retriever=FailingRetriever(),  # type: ignore[arg-type]
        generator=ExtractiveGroundedGenerator(),
    )
    response = await orchestrator.process_text("A question")

    assert response.state == PipelineState.DEPENDENCY_UNAVAILABLE
    assert response.guardrail.reason == GuardrailReason.DEPENDENCY_UNAVAILABLE


class RetryOnceRetriever:
    def __init__(self, delegate: HybridRetriever) -> None:
        self.delegate = delegate
        self.attempts = 0

    async def retrieve(self, query: str, plan: object, deadline: Deadline) -> object:
        self.attempts += 1
        if self.attempts == 1:
            raise DependencyUnavailable("qdrant")
        return await self.delegate.retrieve(query, plan, deadline)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_retryable_retrieval_failure_is_bounded_and_recovers() -> None:
    baseline = await working_orchestrator()
    flaky = RetryOnceRetriever(baseline.retriever)
    orchestrator = PipelineOrchestrator(
        settings=settings(),
        retriever=flaky,  # type: ignore[arg-type]
        generator=ExtractiveGroundedGenerator(),
    )

    response = await orchestrator.process_text("Explain Goa statehood")

    assert response.state == PipelineState.COMPLETED
    assert flaky.attempts == 2


class SlowGenerator:
    async def generate(self, query: str, evidence: object) -> GeneratedAnswer:
        del query, evidence
        await asyncio.sleep(1)
        raise AssertionError("the optional generator should have been cancelled")


@pytest.mark.asyncio
async def test_generation_is_cancelled_at_fallback_threshold() -> None:
    baseline = await working_orchestrator()
    orchestrator = PipelineOrchestrator(
        settings=settings(rag_deadline_ms=150, rag_fallback_at_ms=80),
        retriever=baseline.retriever,
        generator=SlowGenerator(),  # type: ignore[arg-type]
    )
    started = time.perf_counter()

    response = await orchestrator.process_text("Explain Goa statehood")

    assert response.state == PipelineState.DEADLINE_FALLBACK
    assert response.guardrail.reason == GuardrailReason.DEADLINE_EXCEEDED
    assert response.answer
    assert len(response.citations) == 1
    assert response.answer == response.citations[0].text
    assert response.citations[0].span_end - response.citations[0].span_start == len(
        response.answer
    )
    assert time.perf_counter() - started < 0.3


@pytest.mark.asyncio
async def test_late_chunking_flag_skips_optional_window_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = await working_orchestrator()
    orchestrator = PipelineOrchestrator(
        settings=settings(
            rag_enable_sentence_window_chunks=False,
            rag_enable_semantic_chunks=False,
            rag_enable_parent_child_chunks=False,
            rag_enable_bilingual_paired_chunks=False,
            rag_enable_sparse=False,
            rag_enable_late_chunking=False,
        ),
        retriever=baseline.retriever,
        generator=ExtractiveGroundedGenerator(),
    )
    assert orchestrator.router.enabled_strategies == (ChunkStrategy.ATOMIC,)
    assert orchestrator.router.enable_sparse is False

    def fail_if_called(*args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        raise AssertionError("late chunk selection is disabled")

    monkeypatch.setattr("app.harness.orchestrator.select_evidence_windows", fail_if_called)

    response = await orchestrator.process_text("Explain Goa statehood")

    assert response.state == PipelineState.COMPLETED


def _retrieval_hit(*, dense_score: float, fused_score: float = 1.0) -> SearchHit:
    return SearchHit(
        canonical_doc_id="irrelevant",
        parent_id="irrelevant",
        chunk_id="irrelevant",
        text="Unrelated evidence that happens to rank first.",
        language=Language.ENGLISH,
        strategy=ChunkStrategy.ATOMIC,
        span_start=0,
        span_end=46,
        score=fused_score,
        dense_score=dense_score,
        rank_sources={"dense": 1},
    )


class FixedResultRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result

    async def retrieve(self, query: str, plan: object, deadline: Deadline) -> RetrievalResult:
        del query, plan, deadline
        return self.result


@pytest.mark.asyncio
async def test_rrf_rank_score_cannot_make_low_dense_similarity_answerable() -> None:
    hit = _retrieval_hit(dense_score=0.05, fused_score=1.0)
    retriever = FixedResultRetriever(
        RetrievalResult(
            dense_hits=(hit,),
            sparse_hits=(),
            fused_hits=(hit,),
            agreement=0.0,
        )
    )
    orchestrator = PipelineOrchestrator(
        settings=settings(min_answer_score=0.24, min_score_margin=0.0),
        retriever=retriever,  # type: ignore[arg-type]
        generator=ExtractiveGroundedGenerator(),
    )

    response = await orchestrator.process_text("Completely unrelated question")

    assert response.guardrail.reason == GuardrailReason.NO_RELEVANT_EVIDENCE


@pytest.mark.asyncio
async def test_required_empty_sparse_branch_does_not_bypass_agreement_gate() -> None:
    hit = _retrieval_hit(dense_score=0.9)
    retriever = FixedResultRetriever(
        RetrievalResult(
            dense_hits=(hit,),
            sparse_hits=(),
            fused_hits=(hit,),
            agreement=0.0,
            sparse_failed=True,
        )
    )
    orchestrator = PipelineOrchestrator(
        settings=settings(min_answer_score=0.24, min_score_margin=0.0),
        retriever=retriever,  # type: ignore[arg-type]
        generator=ExtractiveGroundedGenerator(),
    )

    response = await orchestrator.process_text("Where is Goa located?")

    assert response.guardrail.reason == GuardrailReason.RETRIEVAL_DISAGREEMENT
    assert response.guardrail.evidence["sparse_failed"] is True
