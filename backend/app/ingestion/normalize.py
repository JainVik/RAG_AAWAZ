from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:!?।॥])")
_SPACE_AFTER_OPEN = re.compile(r"([\[(])\s+")


def normalize_text(text: str) -> str:
    """Normalize safely without transliteration or meaning-changing substitutions."""

    normalized = unicodedata.normalize("NFC", text or "")
    normalized = normalized.replace("\u00a0", " ").replace("\u200b", "")
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    normalized = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", normalized)
    normalized = _SPACE_AFTER_OPEN.sub(r"\1", normalized)
    return normalized


def normalize_for_matching(text: str) -> str:
    normalized = normalize_text(text).casefold()
    return " ".join(re.findall(r"[\w\u0900-\u097f]+", normalized, flags=re.UNICODE))

