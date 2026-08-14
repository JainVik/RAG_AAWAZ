from __future__ import annotations

from collections.abc import Sequence

from app.domain.enums import GuardrailDecision, GuardrailReason
from app.domain.models import GuardrailResult, SearchHit


def check_answerability(
    hits: Sequence[SearchHit],
    *,
    minimum_score: float,
    minimum_margin: float,
) -> GuardrailResult:
    if not hits:
        return GuardrailResult(
            decision=GuardrailDecision.ABSTAIN,
            reason=GuardrailReason.NO_RELEVANT_EVIDENCE,
            user_message="I could not find enough relevant evidence to answer.",
        )
    # RRF is a rank-fusion score: its top hit can be near 1.0 even when every
    # underlying semantic score is poor. Gate on raw dense similarity whenever
    # branch provenance is available, and retain fused-score fallback only for
    # explicit test/custom search implementations that do not expose it.
    dense_scores = sorted(
        (hit.dense_score for hit in hits if hit.dense_score is not None),
        reverse=True,
    )
    score_kind = "raw_dense_similarity" if dense_scores else "search_hit_score"
    relevance_scores = dense_scores or sorted(
        (hit.score for hit in hits), reverse=True
    )
    top = relevance_scores[0]
    second = relevance_scores[1] if len(relevance_scores) > 1 else 0.0
    margin = top - second
    if top < minimum_score or (
        len(relevance_scores) > 1 and margin < minimum_margin
    ):
        return GuardrailResult(
            decision=GuardrailDecision.ABSTAIN,
            reason=GuardrailReason.NO_RELEVANT_EVIDENCE,
            evidence={
                "top_score": top,
                "score_margin": margin,
                "minimum_score": minimum_score,
                "minimum_margin": minimum_margin,
                "score_kind": score_kind,
            },
            user_message="I could not find enough reliable evidence to answer.",
        )
    return GuardrailResult(
        decision=GuardrailDecision.ALLOW,
        evidence={
            "top_score": top,
            "score_margin": margin,
            "score_kind": score_kind,
        },
    )
