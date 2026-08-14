from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.enums import ChunkStrategy, Language
from app.ingestion.normalize import normalize_text

_DEVANAGARI = re.compile(r"[\u0900-\u097f]")
_LATIN = re.compile(r"[A-Za-z]")
_NUMBER_OR_DATE = re.compile(r"\b\d+(?:[./:-]\d+)*\b")
_TOKEN = re.compile(r"\w+", re.UNICODE)
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

TIDE_ROUTER_CONTRACT_VERSION = "tide-router-heuristics-v3"


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
        devanagari = len(_DEVANAGARI.findall(query))
        latin = len(_LATIN.findall(query))
        if devanagari and latin:
            return Language.CODE_MIXED
        if devanagari:
            return Language.HINDI
        if latin:
            return Language.ENGLISH
        return Language.UNKNOWN

    def route(
        self,
        query: str,
        *,
        stt_confidence: float | None = None,
        partial_stability: float | None = None,
    ) -> RoutePlan:
        normalized = normalize_text(query).casefold()
        token_list = _TOKEN.findall(normalized)
        tokens = set(token_list)
        language = self.detect_language(normalized)
        has_number = bool(_NUMBER_OR_DATE.search(normalized))
        is_short = len(token_list) <= 8
        factual = bool(tokens.intersection(_SHORT_FACTUAL)) or has_number
        descriptive = bool(tokens.intersection(_DESCRIPTIVE))
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
        representation_languages: tuple[Language, ...] | None = (
            (Language.ENGLISH,)
            if language == Language.ENGLISH
            else (Language.HINDI,)
            if language == Language.HINDI
            else (Language.MARATHI,)
            if language == Language.MARATHI
            else (Language.CODE_MIXED, Language.HINDI, Language.ENGLISH)
            if language == Language.CODE_MIXED
            else None
        )
        if (
            ChunkStrategy.BILINGUAL_PAIRED in strategies
            and representation_languages is not None
            and Language.CODE_MIXED not in representation_languages
        ):
            representation_languages = (*representation_languages, Language.CODE_MIXED)
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
        )
