from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.enums import ChunkStrategy, Language
from app.domain.languages import analyze_language, language_from_tag
from app.ingestion.normalize import normalize_text
from app.retrieval.query_variants import (
    ROMAN_HINDI_DESCRIPTIVE,
    ROMAN_HINDI_SHORT_FACTUAL,
    is_romanized_hindi,
    unicode_word_tokens,
)

_SHORT_FACTUAL = {
    "what",
    "when",
    "where",
    "who",
    "which",
    "क्या",
    "कब",
    "कहाँ",
    "कौन",
}
_DESCRIPTIVE = {"why", "how", "explain", "describe", "क्यों", "कैसे", "समझाइए", "बताइए"}

TIDE_ROUTER_CONTRACT_VERSION = "tide-router-heuristics-v6"


@dataclass(frozen=True, slots=True)
class RoutePlan:
    language: Language
    category: str
    strategies: tuple[ChunkStrategy, ...]
    dense_weight: float
    sparse_weight: float
    dense_limit: int
    sparse_limit: int
    low_stt_confidence: bool
    representation_languages: tuple[Language, ...] | None = None
    scripts: tuple[str, ...] = ()
    code_mixed: bool = False
    language_confidence: float | None = None
    language_fallback: bool = False
    romanized_hindi: bool = False


class TideRouter:
    """A deterministic, inspectable routing policy; it never calls an LLM."""

    def __init__(
        self,
        dense_limit: int = 24,
        sparse_limit: int = 24,
        *,
        enabled_strategies: Sequence[ChunkStrategy] | None = None,
        enable_sparse: bool = True,
    ) -> None:
        self.dense_limit = dense_limit
        self.sparse_limit = sparse_limit
        requested = tuple(ChunkStrategy) if enabled_strategies is None else enabled_strategies
        configured = tuple(dict.fromkeys(requested))
        if not configured:
            raise ValueError("TideRouter requires at least one dense chunk strategy")
        self.enabled_strategies = configured
        self.enable_sparse = enable_sparse

    @staticmethod
    def detect_language(query: str) -> Language:
        return analyze_language(query).language

    def route(
        self,
        query: str,
        *,
        stt_confidence: float | None = None,
        partial_stability: float | None = None,
        language_hint: Language | str | None = None,
        language_confidence: float | None = None,
    ) -> RoutePlan:
        normalized = normalize_text(query).casefold()
        token_list = unicode_word_tokens(normalized)
        tokens = set(token_list)
        normalized_hint = (
            language_hint
            if isinstance(language_hint, Language)
            else language_from_tag(language_hint)
        )
        language_analysis = analyze_language(
            normalized,
            hint=normalized_hint,
            language_confidence=language_confidence,
        )
        language = language_analysis.language
        romanized_hindi = is_romanized_hindi(
            normalized,
            language_hint=normalized_hint,
        )
        has_number = any(any(character.isdigit() for character in token) for token in token_list)
        is_short = len(token_list) <= 8
        factual = (
            bool(tokens.intersection(_SHORT_FACTUAL))
            or (romanized_hindi and not ROMAN_HINDI_SHORT_FACTUAL.isdisjoint(token_list))
            or has_number
        )
        descriptive = bool(tokens.intersection(_DESCRIPTIVE)) or (
            romanized_hindi and not ROMAN_HINDI_DESCRIPTIVE.isdisjoint(token_list)
        )
        low_confidence = stt_confidence is not None and stt_confidence < 0.65
        unstable = partial_stability is not None and partial_stability < 0.75
        strategies: tuple[ChunkStrategy, ...]

        if language == Language.CODE_MIXED:
            category = "code_mixed"
            strategies = (
                ChunkStrategy.BILINGUAL_PAIRED,
                ChunkStrategy.SENTENCE_WINDOW,
                ChunkStrategy.PARENT_CHILD,
            )
            dense_weight, sparse_weight = 0.55, 0.45
        elif is_short and factual:
            category = "short_factual"
            if language == Language.HINDI and not romanized_hindi:
                # Development A/B testing showed that the formerly validated
                # general plan is materially stronger for native-script Hindi
                # short questions. Keep the intent label for telemetry while
                # preserving that retrieval contract.
                strategies = (ChunkStrategy.ATOMIC, ChunkStrategy.SENTENCE_WINDOW)
                dense_weight, sparse_weight = 0.65, 0.35
            else:
                strategies = (ChunkStrategy.SENTENCE_WINDOW, ChunkStrategy.PARENT_CHILD)
                dense_weight, sparse_weight = 0.45, 0.55
        elif descriptive:
            category = "descriptive"
            strategies = (
                ChunkStrategy.ATOMIC,
                ChunkStrategy.SEMANTIC_SECTION,
                ChunkStrategy.PARENT_CHILD,
            )
            dense_weight, sparse_weight = 0.75, 0.25
        else:
            category = "general"
            strategies = (ChunkStrategy.ATOMIC, ChunkStrategy.SENTENCE_WINDOW)
            dense_weight, sparse_weight = 0.65, 0.35

        if romanized_hindi:
            category = f"roman_hindi_{category}"
            strategies = tuple(
                dict.fromkeys((ChunkStrategy.BILINGUAL_PAIRED, *strategies))
            )

        multiplier = 2 if low_confidence or unstable else 1
        if low_confidence:
            dense_weight, sparse_weight = 0.55, 0.45
        strategies = tuple(
            strategy for strategy in strategies if strategy in self.enabled_strategies
        )
        if not strategies:
            strategies = self.enabled_strategies
            category = f"{category}_enabled_fallback"
        if not self.enable_sparse:
            dense_weight, sparse_weight = 1.0, 0.0
        representation_languages: tuple[Language, ...] | None
        if language == Language.UNKNOWN:
            representation_languages = None
        elif language == Language.CODE_MIXED:
            representation_languages = tuple(
                dict.fromkeys((Language.CODE_MIXED, *language_analysis.component_languages))
            )
        else:
            representation_languages = (language,)
        if (
            ChunkStrategy.BILINGUAL_PAIRED in strategies
            and representation_languages is not None
            and Language.CODE_MIXED not in representation_languages
        ):
            representation_languages = (*representation_languages, Language.CODE_MIXED)
        if romanized_hindi:
            representation_languages = (Language.HINDI, Language.CODE_MIXED)
        return RoutePlan(
            language=language,
            category=category,
            strategies=strategies,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
            dense_limit=self.dense_limit * multiplier,
            sparse_limit=(self.sparse_limit * multiplier if self.enable_sparse else 0),
            low_stt_confidence=low_confidence,
            representation_languages=representation_languages,
            scripts=language_analysis.scripts,
            code_mixed=language_analysis.code_mixed,
            language_confidence=language_analysis.confidence,
            language_fallback=language_analysis.fallback_used,
            romanized_hindi=romanized_hindi,
        )
