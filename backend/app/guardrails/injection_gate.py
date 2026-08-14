from __future__ import annotations

import re

from app.domain.enums import GuardrailDecision, GuardrailReason
from app.domain.models import GuardrailResult

_INJECTION_PATTERNS = (
    r"ignore (?:all |the )?(?:(?:previous|prior) )?(?:system )?instructions",
    r"reveal (?:the )?(?:system prompt|hidden instructions|developer message)",
    r"act as (?:the )?system",
    r"override (?:your |the )?(?:rules|guardrails|instructions)",
    r"पिछले निर्देश(?:ों)? को (?:भूल|नज़रअंदाज़)",
)


def check_prompt_injection(query: str) -> GuardrailResult:
    if any(re.search(pattern, query, flags=re.IGNORECASE) for pattern in _INJECTION_PATTERNS):
        return GuardrailResult(
            decision=GuardrailDecision.BLOCK,
            reason=GuardrailReason.PROMPT_INJECTION,
            user_message="I cannot follow requests to override the retrieval and grounding rules.",
        )
    return GuardrailResult(decision=GuardrailDecision.ALLOW)
