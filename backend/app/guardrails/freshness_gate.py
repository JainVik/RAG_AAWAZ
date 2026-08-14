from __future__ import annotations

import re

from app.domain.enums import GuardrailDecision, GuardrailReason
from app.domain.models import GuardrailResult

_FRESHNESS_PATTERNS = (
    (
        r"\b(today|currently|current|latest|right now|live price|present president|"
        r"present prime minister)\b"
    ),
    r"\b(आज|अभी|वर्तमान|नवीनतम|ताज़ा|लाइव कीमत|मौजूदा)\b",
)


def check_freshness(query: str) -> GuardrailResult:
    if any(re.search(pattern, query, flags=re.IGNORECASE) for pattern in _FRESHNESS_PATTERNS):
        return GuardrailResult(
            decision=GuardrailDecision.ABSTAIN,
            reason=GuardrailReason.STALE_CORPUS,
            evidence={"corpus_type": "static_msmarco_xi"},
            user_message=(
                "This knowledge base is static and cannot reliably answer current or "
                "live questions."
            ),
        )
    return GuardrailResult(decision=GuardrailDecision.ALLOW)
