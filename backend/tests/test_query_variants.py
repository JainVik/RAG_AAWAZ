from __future__ import annotations

import pytest

from app.core.deadlines import Deadline
from app.domain.enums import ChunkStrategy, Language
from app.domain.models import SearchHit
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.query_variants import (
    build_retrieval_query,
    is_romanized_hindi,
    unicode_word_tokens,
)
from app.retrieval.router import TideRouter


@pytest.mark.parametrize(
    ("query", "expected_category"),
    [
        ("भारत की राजधानी क्या है?", "short_factual"),
        ("गोवा कब बना?", "short_factual"),
        ("यह क्यों महत्वपूर्ण है?", "descriptive"),
        ("यह कैसे काम करता है?", "descriptive"),
    ],
)
def test_devanagari_intent_words_survive_unicode_tokenization(
    query: str,
    expected_category: str,
) -> None:
    plan = TideRouter().route(query)

    assert plan.category == expected_category
    assert plan.language == Language.HINDI


def test_unicode_tokenizer_keeps_devanagari_marks_attached() -> None:
    assert unicode_word_tokens("क्या कब क्यों कैसे") == (
        "क्या",
        "कब",
        "क्यों",
        "कैसे",
    )


def test_native_hindi_short_factual_keeps_development_selected_plan() -> None:
    plan = TideRouter().route("भारत की राजधानी क्या है?")

    assert plan.category == "short_factual"
    assert plan.strategies == (
        ChunkStrategy.ATOMIC,
        ChunkStrategy.SENTENCE_WINDOW,
    )
    assert (plan.dense_weight, plan.sparse_weight) == (0.65, 0.35)


@pytest.mark.parametrize("hint", [Language.HINDI, Language.CODE_MIXED])
def test_roman_hindi_fallback_requires_and_honors_explicit_hint(hint: Language) -> None:
    query = "bharat me allocation ka kya matlab hai"
    plan = TideRouter().route(query, language_hint=hint)

    assert plan.romanized_hindi is True
    assert plan.category == (
        "roman_hindi_code_mixed"
        if hint == Language.CODE_MIXED
        else "roman_hindi_short_factual"
    )
    assert plan.representation_languages == (Language.HINDI, Language.CODE_MIXED)
    assert ChunkStrategy.BILINGUAL_PAIRED in plan.strategies
    if hint == Language.HINDI:
        assert ChunkStrategy.PARENT_CHILD in plan.strategies
        assert (plan.dense_weight, plan.sparse_weight) == (0.45, 0.55)
    assert build_retrieval_query(query, romanized_hindi=plan.romanized_hindi) == (
        "bharat me allocation का क्या मतलब है"
    )


def test_marker_variant_preserves_unknown_english_and_content_tokens() -> None:
    query = "COVID-19 allocation ka kya matlab hai?"

    assert build_retrieval_query(query, romanized_hindi=True) == (
        "COVID-19 allocation का क्या मतलब है?"
    )
    assert build_retrieval_query(
        "Explain the allocation ka matlab",
        romanized_hindi=True,
    ) == "Explain the allocation का मतलब"


def test_plain_english_or_unhinted_latin_text_is_not_transliterated() -> None:
    roman_hindi = "bharat me allocation ka kya matlab hai"
    english = "Tell me the allocation process."

    assert is_romanized_hindi(roman_hindi, language_hint=None) is False
    assert TideRouter().route(roman_hindi).romanized_hindi is False
    assert is_romanized_hindi(english, language_hint=Language.HINDI) is False
    assert build_retrieval_query(english, romanized_hindi=False) == english


def _hit(chunk_id: str) -> SearchHit:
    return SearchHit(
        canonical_doc_id="doc",
        parent_id="parent",
        chunk_id=chunk_id,
        text="भारत में allocation का अर्थ आवंटन है।",
        language=Language.HINDI,
        strategy=ChunkStrategy.SENTENCE_WINDOW,
        span_start=0,
        span_end=35,
        score=0.8,
    )


class _CapturingDenseSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search_dense(
        self,
        query: str,
        *,
        strategies: object,
        limit: int,
        languages: object = None,
    ) -> list[SearchHit]:
        del strategies, limit, languages
        self.queries.append(query)
        return [_hit("dense")]


class _CapturingSparseSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search_sparse(
        self,
        query: str,
        *,
        strategies: object,
        limit: int,
        languages: object = None,
    ) -> list[SearchHit]:
        del strategies, limit, languages
        self.queries.append(query)
        return [_hit("sparse")]


@pytest.mark.asyncio
async def test_hybrid_searches_one_bounded_mixed_script_query_per_branch() -> None:
    query = "bharat me allocation ka kya matlab hai"
    plan = TideRouter().route(query, language_hint=Language.HINDI)
    dense = _CapturingDenseSearch()
    sparse = _CapturingSparseSearch()
    retriever = HybridRetriever(dense, sparse)

    await retriever.retrieve(query, plan, Deadline.after_ms(500, 450))

    expected = build_retrieval_query(query, romanized_hindi=True)
    assert dense.queries == [expected]
    assert sparse.queries == [expected]
    assert "allocation" in expected
    assert "क्या" in expected
