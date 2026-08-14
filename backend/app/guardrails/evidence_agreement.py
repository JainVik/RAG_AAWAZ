from __future__ import annotations

from app.domain.enums import GuardrailDecision, GuardrailReason
from app.domain.models import GuardrailResult


def check_evidence_agreement(value: float, minimum: float) -> GuardrailResult:
    if value < minimum:
        return GuardrailResult(
            decision=GuardrailDecision.ABSTAIN,
            reason=GuardrailReason.RETRIEVAL_DISAGREEMENT,
            evidence={"agreement": value, "minimum": minimum},
            user_message="The available evidence disagrees, so I cannot answer reliably.",
        )
    return GuardrailResult(decision=GuardrailDecision.ALLOW)

