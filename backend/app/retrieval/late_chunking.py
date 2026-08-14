from __future__ import annotations

import re
from collections.abc import Sequence

from app.domain.enums import ChunkStrategy, Language
from app.domain.models import SearchHit
from app.ingestion.chunk_factory import sentence_spans
from app.ingestion.deduplicate import stable_id
from app.ingestion.normalize import normalize_for_matching


def _query_terms(text: str) -> set[str]:
    return set(re.findall(r"[\w\u0900-\u097f]+", normalize_for_matching(text)))


def select_evidence_windows(
    query: str,
    parents: Sequence[SearchHit],
    *,
    limit: int = 3,
    sentences_per_window: int = 2,
    preferred_language: Language | None = None,
) -> list[SearchHit]:
    """Segment and score only retrieved parents; this is request-time late chunking."""

    query_terms = _query_terms(query)
    candidates: list[tuple[float, SearchHit]] = []
    for parent in parents:
        parent_source = parent.parent_text or parent.text
        spans = sentence_spans(parent_source)
        if not spans:
            continue
        for index in range(len(spans)):
            window = spans[index : index + sentences_per_window]
            if not window:
                continue
            start, end = window[0].start, window[-1].end
            window_text = parent_source[start:end]
            terms = _query_terms(window_text)
            lexical = len(query_terms & terms) / max(1, len(query_terms))
            number_bonus = 0.1 if re.search(r"\d", query) and re.search(r"\d", window_text) else 0.0
            language_bonus = 0.0
            if preferred_language == parent.language:
                language_bonus = 0.05
            elif preferred_language == Language.CODE_MIXED and parent.language in {
                Language.CODE_MIXED,
                Language.HINDI,
                Language.ENGLISH,
            }:
                language_bonus = 0.025
            score = 0.65 * parent.score + 0.35 * lexical + number_bonus + language_bonus
            if parent.parent_text is not None:
                absolute_start, absolute_end = start, end
            else:
                absolute_start = parent.span_start + start
                absolute_end = parent.span_start + end
            hit = parent.model_copy(
                update={
                    "chunk_id": stable_id(parent.chunk_id, "late", str(start), str(end)),
                    "text": window_text,
                    "strategy": ChunkStrategy.SENTENCE_WINDOW,
                    "span_start": absolute_start,
                    "span_end": absolute_end,
                    "score": score,
                    "metadata": {**parent.metadata, "late_chunked": True},
                }
            )
            candidates.append((score, hit))
    candidates.sort(key=lambda pair: (-pair[0], pair[1].parent_id, pair[1].span_start))
    selected: list[SearchHit] = []
    seen_parents: set[str] = set()
    for _, hit in candidates:
        if hit.parent_id in seen_parents:
            continue
        seen_parents.add(hit.parent_id)
        selected.append(hit)
        if len(selected) >= limit:
            break
    return selected
