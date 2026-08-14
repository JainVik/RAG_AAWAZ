from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from app.domain.enums import AnswerMode
from app.domain.models import Citation, SearchHit
from app.generation.evidence_extractor import choose_supporting_hits
from app.ingestion.chunk_factory import sentence_spans

CoordinateSystem = Literal["parent_text", "chunk_text", "paired_representation"]


@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    text: str
    mode: AnswerMode
    citations: tuple[Citation, ...]


class GroundedAnswerGenerator(Protocol):
    async def generate(self, query: str, evidence: list[SearchHit]) -> GeneratedAnswer: ...


def evidence_coordinate_source(
    hit: SearchHit,
) -> tuple[str, CoordinateSystem, int]:
    """Return the immutable text, coordinate label, and chunk-local base offset."""

    if hit.parent_text is not None:
        start, end = hit.span_start, hit.span_end
        if 0 <= start < end <= len(hit.parent_text) and hit.parent_text[start:end] == hit.text:
            raw_coordinate = str(
                hit.metadata.get("span_coordinate_system", "parent_text")
            )
            coordinate: CoordinateSystem = (
                cast(CoordinateSystem, raw_coordinate)
                if raw_coordinate in {"parent_text", "paired_representation"}
                else "parent_text"
            )
            return hit.parent_text, coordinate, start
    return hit.text, "chunk_text", 0


def extract_first_evidence_sentence(hit: SearchHit) -> SearchHit:
    """Create one exact, source-addressable sentence from a retrieved hit."""

    spans = sentence_spans(hit.text)
    if spans:
        segment = spans[0]
        text, local_start, local_end = segment.text, segment.start, segment.end
    else:
        text = hit.text.strip()
        if not text:
            raise ValueError("Evidence did not contain an extractable sentence")
        local_start = hit.text.index(text)
        local_end = local_start + len(text)
    source, coordinate, base = evidence_coordinate_source(hit)
    return hit.model_copy(
        update={
            "text": text,
            "parent_text": source,
            "span_start": base + local_start,
            "span_end": base + local_end,
            "metadata": {
                **hit.metadata,
                "citation_coordinate_system": coordinate,
                "citation_source_text_sha256": hashlib.sha256(
                    source.encode("utf-8")
                ).hexdigest(),
            },
        }
    )


def citation_from_evidence(hit: SearchHit) -> Citation:
    source = hit.parent_text or hit.text
    raw_coordinate = str(hit.metadata.get("citation_coordinate_system", "chunk_text"))
    coordinate: CoordinateSystem = (
        cast(CoordinateSystem, raw_coordinate)
        if raw_coordinate in {"parent_text", "chunk_text", "paired_representation"}
        else "chunk_text"
    )
    return Citation(
        canonical_doc_id=hit.canonical_doc_id,
        parent_id=hit.parent_id,
        chunk_id=hit.chunk_id,
        strategy=hit.strategy,
        text=hit.text,
        span_start=hit.span_start,
        span_end=hit.span_end,
        span_coordinate_system=coordinate,
        source_text_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        dense_score=hit.dense_score,
        sparse_score=hit.sparse_score,
    )


class ExtractiveGroundedGenerator:
    """Returns only exact evidence spans, so containment verification is deterministic."""

    async def generate(self, query: str, evidence: list[SearchHit]) -> GeneratedAnswer:
        del query
        selected = choose_supporting_hits(evidence, limit=2)
        if not selected:
            raise ValueError("Cannot generate an extractive answer without evidence")
        extracted: list[SearchHit] = []
        for hit in selected:
            extracted.append(extract_first_evidence_sentence(hit))
        if not extracted:
            raise ValueError("Evidence did not contain an extractable sentence")
        answer = " ".join(hit.text for hit in extracted)
        citations = tuple(citation_from_evidence(hit) for hit in extracted)
        return GeneratedAnswer(text=answer, mode=AnswerMode.EXTRACTIVE, citations=citations)
