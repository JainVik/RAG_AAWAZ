from __future__ import annotations

import re

from app.domain.enums import GuardrailDecision, GuardrailReason
from app.domain.models import GuardrailResult

# Deliberately narrow rules catch explicit facilitation requests. This is not a learned model.
_HARMFUL_PATTERNS = (
    r"\b(?:build|make|assemble) (?:a )?(?:bomb|explosive device)\b",
    r"\b(?:poison|kill) (?:someone|a person) without (?:being caught|detection)\b",
    r"\bsteal (?:a )?(?:password|credit card|identity)\b",
    r"(?:बम|विस्फोटक) (?:कैसे )?(?:बनाएँ|बनाना)",
)


def check_safety(query: str) -> GuardrailResult:
    if any(re.search(pattern, query, flags=re.IGNORECASE) for pattern in _HARMFUL_PATTERNS):
        return GuardrailResult(
            decision=GuardrailDecision.BLOCK,
            reason=GuardrailReason.UNSAFE_REQUEST,
            user_message="I cannot help with instructions that facilitate serious harm.",
        )
    return GuardrailResult(decision=GuardrailDecision.ALLOW)
