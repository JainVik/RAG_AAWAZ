from __future__ import annotations

import hashlib
from collections.abc import Sequence

from app.domain.enums import GuardrailDecision, GuardrailReason
from app.domain.models import GuardrailResult, SearchHit
from app.generation.grounded_generator import GeneratedAnswer, evidence_coordinate_source
from app.ingestion.normalize import normalize_for_matching


def verify_extractive_grounding(
    answer: GeneratedAnswer, retrieved_evidence: Sequence[SearchHit]
) -> GuardrailResult:
    normalized_answer = normalize_for_matching(answer.text)
    normalized_evidence = " ".join(
        normalize_for_matching(item.text) for item in answer.citations
    )
    citation_spans_valid = bool(answer.citations)
    for citation in answer.citations:
        candidates = (
            hit
            for hit in retrieved_evidence
            if hit.canonical_doc_id == citation.canonical_doc_id
            and hit.parent_id == citation.parent_id
            and hit.chunk_id == citation.chunk_id
            and hit.strategy == citation.strategy
        )
        resolved = False
        for hit in candidates:
            source, coordinate, _base = evidence_coordinate_source(hit)
            if (
                citation.span_coordinate_system == coordinate
                and hashlib.sha256(source.encode("utf-8")).hexdigest()
                == citation.source_text_sha256
                and 0 <= citation.span_start < citation.span_end <= len(source)
                and source[citation.span_start : citation.span_end] == citation.text
            ):
                resolved = True
                break
        if not resolved:
            citation_spans_valid = False
            break
    supported = bool(normalized_answer) and normalized_answer == normalized_evidence
    if not supported or not citation_spans_valid:
        return GuardrailResult(
            decision=GuardrailDecision.ABSTAIN,
            reason=GuardrailReason.UNSUPPORTED_CLAIM,
            evidence={"citation_count": len(answer.citations)},
            user_message="I found evidence but could not verify the final wording.",
        )
    return GuardrailResult(decision=GuardrailDecision.ALLOW)
