from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.domain.enums import ChunkStrategy, Language
from app.domain.models import Chunk, CorpusDocument
from app.ingestion.deduplicate import stable_id


@dataclass(frozen=True, slots=True)
class SentenceSpan:
    text: str
    start: int
    end: int


_TERMINATOR = re.compile(r"[.!?।॥]+(?:[\"'”’\)\]]*)")
_PERIOD_ABBREVIATIONS = {
    "dr.",
    "mr.",
    "mrs.",
    "ms.",
    "prof.",
    "sr.",
    "jr.",
    "st.",
    "vs.",
    "no.",
    "fig.",
    "dept.",
    "govt.",
    "e.g.",
    "i.e.",
}


def _is_internal_period(text: str, start: int, end: int) -> bool:
    punctuation = text[start:end].rstrip("\"'”’)]")
    if punctuation != ".":
        return False
    if (
        start > 0
        and start + 1 < len(text)
        and text[start - 1].isdigit()
        and text[start + 1].isdigit()
    ):
        return True
    if end < len(text) and not text[end].isspace():
        return True
    token_match = re.search(r"[A-Za-z.]+\.$", text[: start + 1])
    token = token_match.group(0).casefold() if token_match else ""
    if token in _PERIOD_ABBREVIATIONS:
        return True
    if re.fullmatch(r"(?:[a-z]\.)+", token):
        return True
    next_nonspace = end
    while next_nonspace < len(text) and text[next_nonspace].isspace():
        next_nonspace += 1
    return (
        "." in token[:-1]
        and next_nonspace < len(text)
        and text[next_nonspace].islower()
    )


def sentence_spans(text: str) -> list[SentenceSpan]:
    """Return exact, non-overlapping sentence spans for Latin and Indic punctuation."""

    spans: list[SentenceSpan] = []
    cursor = 0
    for match in _TERMINATOR.finditer(text):
        end = match.end()
        if _is_internal_period(text, match.start(), end):
            continue
        raw_start = cursor
        while raw_start < end and text[raw_start].isspace():
            raw_start += 1
        if raw_start < end:
            spans.append(SentenceSpan(text=text[raw_start:end], start=raw_start, end=end))
        cursor = end
    tail_start = cursor
    while tail_start < len(text) and text[tail_start].isspace():
        tail_start += 1
    if tail_start < len(text):
        spans.append(SentenceSpan(text=text[tail_start:], start=tail_start, end=len(text)))
    return spans


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class ChunkFactory:
    def __init__(
        self,
        *,
        sentence_window_size: int = 3,
        sentence_overlap: int = 1,
        semantic_min_sentences: int = 4,
        semantic_break_quantile: float = 0.35,
        semantic_max_words: int = 180,
        bilingual_max_characters: int = 800,
        sentence_embedder: Callable[[list[str]], Sequence[Sequence[float]]] | None = None,
    ) -> None:
        if sentence_window_size < 1:
            raise ValueError("sentence_window_size must be positive")
        if not 0 <= sentence_overlap < sentence_window_size:
            raise ValueError("sentence_overlap must be between zero and window size")
        if semantic_min_sentences < 2:
            raise ValueError("semantic_min_sentences must be at least 2")
        if semantic_max_words < 1:
            raise ValueError("semantic_max_words must be positive")
        if bilingual_max_characters < 32:
            raise ValueError("bilingual_max_characters must be at least 32")
        self.window_size = sentence_window_size
        self.overlap = sentence_overlap
        self.semantic_min_sentences = semantic_min_sentences
        self.semantic_break_quantile = semantic_break_quantile
        self.semantic_max_words = semantic_max_words
        self.bilingual_max_characters = bilingual_max_characters
        self.sentence_embedder = sentence_embedder

    def _chunk(
        self,
        document: CorpusDocument,
        *,
        strategy: ChunkStrategy,
        language: Language,
        text: str,
        start: int,
        end: int,
        metadata: dict[str, object] | None = None,
    ) -> Chunk:
        chunk_text = text[start:end]
        chunk_id = stable_id(
            document.parent_id,
            strategy.value,
            language.value,
            str(start),
            str(end),
            chunk_text,
        )
        return Chunk(
            canonical_doc_id=document.canonical_doc_id,
            parent_id=document.parent_id,
            chunk_id=chunk_id,
            language=language,
            strategy=strategy,
            text=chunk_text,
            span_start=start,
            span_end=end,
            english_text=document.english_text,
            translated_text=document.translated_text,
            translation_model=document.translation_model,
            metadata=dict(metadata or {}),
        )

    def atomic(
        self, document: CorpusDocument, language: Language = Language.ENGLISH
    ) -> list[Chunk]:
        text = self._text_for_language(document, language)
        if not text:
            return []
        return [
            self._chunk(
                document,
                strategy=ChunkStrategy.ATOMIC,
                language=language,
                text=text,
                start=0,
                end=len(text),
            )
        ]

    def sentence_windows(
        self, document: CorpusDocument, language: Language = Language.ENGLISH
    ) -> list[Chunk]:
        text = self._text_for_language(document, language)
        if not text:
            return []
        sentences = sentence_spans(text)
        if len(sentences) <= 1:
            return [
                self._chunk(
                    document,
                    strategy=ChunkStrategy.SENTENCE_WINDOW,
                    language=language,
                    text=text,
                    start=0,
                    end=len(text),
                    metadata={
                        "sentence_start": 0,
                        "sentence_count": len(sentences),
                        "single_sentence_geometry": "atomic_span",
                    },
                )
            ]
        step = self.window_size - self.overlap
        chunks: list[Chunk] = []
        for start_index in range(0, len(sentences), step):
            window = sentences[start_index : start_index + self.window_size]
            if not window:
                break
            if chunks and window[-1].end <= chunks[-1].span_end:
                break
            chunks.append(
                self._chunk(
                    document,
                    strategy=ChunkStrategy.SENTENCE_WINDOW,
                    language=language,
                    text=text,
                    start=window[0].start,
                    end=window[-1].end,
                    metadata={"sentence_start": start_index, "sentence_count": len(window)},
                )
            )
            if window[-1].end == len(text):
                break
        return chunks

    def semantic_sections(
        self, document: CorpusDocument, language: Language = Language.ENGLISH
    ) -> list[Chunk]:
        text = self._text_for_language(document, language)
        sentences = sentence_spans(text)
        meaningful = [item for item in sentences if len(item.text.split()) >= 3]
        if len(meaningful) < self.semantic_min_sentences or self.sentence_embedder is None:
            return []
        embeddings = list(self.sentence_embedder([item.text for item in meaningful]))
        if len(embeddings) != len(meaningful):
            raise ValueError("sentence embedder returned an unexpected number of vectors")
        similarities = [
            _cosine(embeddings[index], embeddings[index + 1])
            for index in range(len(embeddings) - 1)
        ]
        ordered = sorted(similarities)
        threshold_index = min(
            len(ordered) - 1,
            max(0, int((len(ordered) - 1) * self.semantic_break_quantile)),
        )
        threshold = ordered[threshold_index]
        semantic_break_starts = {
            meaningful[index].start
            for index in range(1, len(meaningful))
            if similarities[index - 1] <= threshold
        }
        groups: list[list[SentenceSpan]] = []
        current: list[SentenceSpan] = []
        current_words = 0
        for sentence in sentences:
            words = list(re.finditer(r"\S+", sentence.text))
            word_count = len(words)
            must_cap = bool(current) and (
                current_words + word_count > self.semantic_max_words
            )
            if current and (must_cap or sentence.start in semantic_break_starts):
                groups.append(current)
                current = []
                current_words = 0
            if word_count > self.semantic_max_words:
                for offset in range(0, word_count, self.semantic_max_words):
                    window = words[offset : offset + self.semantic_max_words]
                    start = sentence.start + window[0].start()
                    end = sentence.start + window[-1].end()
                    groups.append(
                        [SentenceSpan(text=text[start:end], start=start, end=end)]
                    )
                continue
            current.append(sentence)
            current_words += word_count
        if current:
            groups.append(current)
        return [
            self._chunk(
                document,
                strategy=ChunkStrategy.SEMANTIC_SECTION,
                language=language,
                text=text,
                start=group[0].start,
                end=group[-1].end,
                metadata={
                    "sentence_count": len(group),
                    "word_count": len(text[group[0].start : group[-1].end].split()),
                    "similarity_threshold": threshold,
                    "oversized_sentence_split": len(group) == 1
                    and group[0] not in sentences,
                },
            )
            for group in groups
        ]

    def parent_children(
        self, document: CorpusDocument, language: Language = Language.ENGLISH
    ) -> list[Chunk]:
        children = self.sentence_windows(document, language)
        return [
            child.model_copy(
                update={
                    "strategy": ChunkStrategy.PARENT_CHILD,
                    "chunk_id": stable_id(child.chunk_id, ChunkStrategy.PARENT_CHILD.value),
                    "metadata": {**child.metadata, "return_parent": True},
                }
            )
            for child in children
        ]

    def bilingual_paired(self, document: CorpusDocument) -> list[Chunk]:
        if not document.translated_text or not document.english_text:
            return []
        separator = "\n[EN] "
        component_cap = (self.bilingual_max_characters - len(separator)) // 2
        translated_spans = self._fixed_character_spans(document.translated_text, component_cap)
        english_spans = self._fixed_character_spans(document.english_text, component_cap)
        pair_count = max(len(translated_spans), len(english_spans))
        chunks: list[Chunk] = []
        for pair_index in range(pair_count):
            translated = translated_spans[min(pair_index, len(translated_spans) - 1)]
            english = english_spans[min(pair_index, len(english_spans) - 1)]
            translated_text = document.translated_text[translated.start : translated.end]
            english_text = document.english_text[english.start : english.end]
            paired = f"{translated_text}{separator}{english_text}"
            english_representation_start = len(translated_text) + len(separator)
            chunk_id = stable_id(
                document.parent_id,
                ChunkStrategy.BILINGUAL_PAIRED.value,
                str(translated.start),
                str(translated.end),
                str(english.start),
                str(english.end),
                paired,
            )
            chunks.append(
                Chunk(
                    canonical_doc_id=document.canonical_doc_id,
                    parent_id=document.parent_id,
                    chunk_id=chunk_id,
                    language=Language.CODE_MIXED,
                    strategy=ChunkStrategy.BILINGUAL_PAIRED,
                    text=paired,
                    span_start=0,
                    span_end=len(paired),
                    english_text=document.english_text,
                    translated_text=document.translated_text,
                    translation_model=document.translation_model,
                    metadata={
                        "paired": True,
                        "translated_language": document.translation_language,
                        "span_coordinate_system": "paired_representation",
                        "representation_span": [0, len(paired)],
                        "translated_source_span": [translated.start, translated.end],
                        "english_source_span": [english.start, english.end],
                        "translated_representation_span": [0, len(translated_text)],
                        "english_representation_span": [
                            english_representation_start,
                            len(paired),
                        ],
                        "pair_index": pair_index,
                        "pair_count": pair_count,
                        "translated_component_reused": pair_index >= len(translated_spans),
                        "english_component_reused": pair_index >= len(english_spans),
                        "maximum_representation_characters": self.bilingual_max_characters,
                    },
                )
            )
        return chunks

    def all_enabled(
        self,
        document: CorpusDocument,
        *,
        enable_atomic: bool = True,
        enable_sentence_window: bool = True,
        enable_semantic: bool = True,
        enable_parent_child: bool = True,
        enable_bilingual: bool = True,
    ) -> list[Chunk]:
        if not any(
            (
                enable_atomic,
                enable_sentence_window,
                enable_semantic,
                enable_parent_child,
                enable_bilingual,
            )
        ):
            raise ValueError("ChunkFactory requires at least one enabled strategy")
        result: list[Chunk] = []
        for language in self.document_languages(document):
            if enable_atomic:
                result.extend(self.atomic(document, language))
            if enable_sentence_window:
                result.extend(self.sentence_windows(document, language))
            if enable_semantic:
                result.extend(self.semantic_sections(document, language))
            if enable_parent_child:
                result.extend(self.parent_children(document, language))
        if document.translated_text and enable_bilingual:
            result.extend(self.bilingual_paired(document))
        chunk_ids = [chunk.chunk_id for chunk in result]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("ChunkFactory emitted duplicate chunk_id values")
        return result

    @staticmethod
    def _fixed_character_spans(text: str, maximum: int) -> list[SentenceSpan]:
        spans: list[SentenceSpan] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + maximum)
            while (
                end > start and end < len(text) and unicodedata.category(text[end]).startswith("M")
            ):
                end -= 1
            if end == start:
                end = min(len(text), start + maximum)
            spans.append(SentenceSpan(text=text[start:end], start=start, end=end))
            start = end
        return spans

    @staticmethod
    def document_languages(document: CorpusDocument) -> tuple[Language, ...]:
        if not document.translated_text:
            return (Language.ENGLISH,)
        translation_language = (document.translation_language or "").casefold()
        translated = (
            Language.MARATHI if translation_language.startswith(("mr", "mar")) else Language.HINDI
        )
        return Language.ENGLISH, translated

    @staticmethod
    def _text_for_language(document: CorpusDocument, language: Language) -> str:
        if language in {Language.HINDI, Language.MARATHI}:
            return document.translated_text or ""
        return document.english_text
