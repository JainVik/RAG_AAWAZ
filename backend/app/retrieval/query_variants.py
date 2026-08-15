from __future__ import annotations

import re
import unicodedata

from app.domain.enums import Language
from app.ingestion.normalize import normalize_text

MAX_ROMAN_HINDI_QUERY_CHARS = 512
MAX_ROMAN_HINDI_TOKENS = 64

ROMAN_HINDI_SHORT_FACTUAL = frozenset(
    {
        "kab",
        "kahaan",
        "kahan",
        "kaun",
        "kis",
        "kitna",
        "kitne",
        "kitni",
        "kya",
    }
)
ROMAN_HINDI_DESCRIPTIVE = frozenset(
    {
        "bataie",
        "bataiye",
        "batao",
        "kaise",
        "kyon",
        "kyu",
        "kyun",
        "samjhaie",
        "samjhaiye",
        "samjhao",
    }
)
_STRONG_FUNCTION_WORDS = frozenset(
    {
        "hai",
        "hain",
        "ka",
        "ki",
        "ko",
        "liye",
        "matlab",
        "mein",
        "nahi",
        "nahin",
        "tha",
        "thi",
    }
)
_WEAK_FUNCTION_WORDS = frozenset({"aur", "ke", "par", "se", "ya"})
_STRONG_MARKERS = (
    ROMAN_HINDI_SHORT_FACTUAL | ROMAN_HINDI_DESCRIPTIVE | _STRONG_FUNCTION_WORDS
)

# This is deliberately a small grammar/question-word normalization, not a
# general transliterator. Unknown content, names, and English/domain terms stay
# byte-for-byte unchanged in the retrieval variant.
_HIGH_CONFIDENCE_REWRITES = {
    "bataie": "बताइए",
    "bataiye": "बताइए",
    "batao": "बताओ",
    "hai": "है",
    "hain": "हैं",
    "ka": "का",
    "kahaan": "कहाँ",
    "kahan": "कहाँ",
    "kaise": "कैसे",
    "kaun": "कौन",
    "ke": "के",
    "ki": "की",
    "kis": "किस",
    "kitna": "कितना",
    "kitne": "कितने",
    "kitni": "कितनी",
    "ko": "को",
    "kya": "क्या",
    "kyon": "क्यों",
    "kyu": "क्यों",
    "kyun": "क्यों",
    "liye": "लिए",
    "matlab": "मतलब",
    "mein": "में",
    "nahi": "नहीं",
    "nahin": "नहीं",
    "samjhaie": "समझाइए",
    "samjhaiye": "समझाइए",
    "samjhao": "समझाओ",
    "tha": "था",
    "thi": "थी",
}
_ASCII_WORD = re.compile(r"[A-Za-z]+")


def unicode_word_tokens(text: str) -> tuple[str, ...]:
    """Split words without breaking Indic combining marks."""

    tokens: list[str] = []
    current: list[str] = []
    for character in normalize_text(text).casefold():
        if unicodedata.category(character)[0] in {"L", "M", "N"}:
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current.clear()
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


def is_romanized_hindi(query: str, *, language_hint: Language | None) -> bool:
    """Recognize bounded Roman Hindi only when the caller supplied an Indic hint."""

    normalized = normalize_text(query)
    if language_hint not in {Language.HINDI, Language.CODE_MIXED}:
        return False
    if not normalized or len(normalized) > MAX_ROMAN_HINDI_QUERY_CHARS:
        return False
    if any("\u0900" <= character <= "\u097f" for character in normalized):
        return False
    tokens = unicode_word_tokens(normalized)
    if len(tokens) < 2 or len(tokens) > MAX_ROMAN_HINDI_TOKENS:
        return False
    latin_tokens = {token for token in tokens if token.isascii() and token.isalpha()}
    if len(latin_tokens) < 2:
        return False
    if latin_tokens.intersection(_STRONG_MARKERS):
        return True
    return len(latin_tokens.intersection(_WEAK_FUNCTION_WORDS)) >= 2


def build_retrieval_query(query: str, *, romanized_hindi: bool) -> str:
    """Build one mixed-script retrieval query while leaving the transcript untouched."""

    original = normalize_text(query)
    if not romanized_hindi:
        return original

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        return _HIGH_CONFIDENCE_REWRITES.get(token.casefold(), token)

    return _ASCII_WORD.sub(replace, original)
