from __future__ import annotations

import itertools
import re
from collections.abc import Sequence

from app.domain.enums import GuardrailDecision, GuardrailReason
from app.domain.models import GuardrailResult, SearchHit
from app.ingestion.normalize import normalize_for_matching

_NEGATIONS = frozenset(
    {
        "no",
        "not",
        "never",
        "neither",
        "without",
        "न",
        "नहीं",
        "नही",
        "मत",
    }
)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "be",
        "became",
        "did",
        "for",
        "in",
        "is",
        "it",
        "of",
        "on",
        "the",
        "to",
        "was",
        "were",
        "है",
        "था",
        "थी",
        "में",
        "का",
        "की",
        "के",
        "और",
    }
)
_NUMBER = re.compile(r"\d+(?:[.,:/-]\d+)*")


def _features(text: str) -> tuple[frozenset[str], frozenset[str], bool]:
    normalized = normalize_for_matching(text)
    tokens = normalized.split()
    content = frozenset(
        token for token in tokens if token not in _STOPWORDS and token not in _NEGATIONS
    )
    numbers = frozenset(_NUMBER.findall(normalized))
    negated = any(token in _NEGATIONS for token in tokens)
    return content, numbers, negated


def check_evidence_conflict(
    hits: Sequence[SearchHit], *, maximum_hits: int = 5
) -> GuardrailResult:
    """Refuse closely matching claims with conflicting polarity or numbers.

    This is deliberately conservative and deterministic. It is not a general
    natural-language-inference model; claims outside these explicit patterns
    remain subject to dense/sparse agreement and exact grounding checks.
    """

    candidates = hits[:maximum_hits]
    for left, right in itertools.combinations(candidates, 2):
        if left.parent_id == right.parent_id:
            continue
        left_content, left_numbers, left_negated = _features(left.text)
        right_content, right_numbers, right_negated = _features(right.text)
        if not left_content or not right_content:
            continue
        shared = left_content & right_content
        containment = len(shared) / min(len(left_content), len(right_content))
        if len(shared) < 2 or containment < 0.6:
            continue
        conflict_type: str | None = None
        if left_negated != right_negated:
            conflict_type = "opposite_negation"
        elif left_numbers and right_numbers and left_numbers.isdisjoint(right_numbers):
            conflict_type = "incompatible_numbers"
        if conflict_type is not None:
            return GuardrailResult(
                decision=GuardrailDecision.ABSTAIN,
                reason=GuardrailReason.RETRIEVAL_DISAGREEMENT,
                evidence={
                    "conflict_type": conflict_type,
                    "left_chunk_id": left.chunk_id,
                    "right_chunk_id": right.chunk_id,
                    "content_overlap": containment,
                },
                user_message=(
                    "The retrieved passages contain conflicting claims, so I cannot "
                    "answer reliably."
                ),
            )
    return GuardrailResult(decision=GuardrailDecision.ALLOW)
