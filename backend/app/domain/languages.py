from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import Language


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    language: Language
    name: str
    scripts: tuple[str, ...]
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LanguageAnalysis:
    language: Language
    scripts: tuple[str, ...]
    component_languages: tuple[Language, ...]
    code_mixed: bool
    confidence: float | None
    source: str
    ambiguous: bool
    fallback_used: bool
    hint_script_mismatch: bool = False


LANGUAGE_PROFILES: dict[Language, LanguageProfile] = {
    Language.ASSAMESE: LanguageProfile(
        Language.ASSAMESE, "Assamese", ("Bengali",), ("as", "asm", "asm_beng")
    ),
    Language.BENGALI: LanguageProfile(
        Language.BENGALI, "Bengali", ("Bengali",), ("bn", "ben", "ben_beng")
    ),
    Language.ENGLISH: LanguageProfile(
        Language.ENGLISH, "English", ("Latin",), ("en", "eng", "eng_latn")
    ),
    Language.GUJARATI: LanguageProfile(
        Language.GUJARATI, "Gujarati", ("Gujarati",), ("gu", "guj", "guj_gujr")
    ),
    Language.HINDI: LanguageProfile(
        Language.HINDI, "Hindi", ("Devanagari",), ("hi", "hin", "hin_deva")
    ),
    Language.KANNADA: LanguageProfile(
        Language.KANNADA, "Kannada", ("Kannada",), ("kn", "kan", "kan_knda")
    ),
    Language.MALAYALAM: LanguageProfile(
        Language.MALAYALAM, "Malayalam", ("Malayalam",), ("ml", "mal", "mal_mlym")
    ),
    Language.MARATHI: LanguageProfile(
        Language.MARATHI, "Marathi", ("Devanagari",), ("mr", "mar", "mar_deva")
    ),
    Language.NEPALI: LanguageProfile(
        Language.NEPALI, "Nepali", ("Devanagari",), ("ne", "nep", "npi", "npi_deva")
    ),
    Language.ODIA: LanguageProfile(
        Language.ODIA, "Odia", ("Odia",), ("or", "ori", "ory", "ory_orya")
    ),
    Language.PUNJABI: LanguageProfile(
        Language.PUNJABI, "Punjabi", ("Gurmukhi",), ("pa", "pan", "pan_guru")
    ),
    Language.SANSKRIT: LanguageProfile(
        Language.SANSKRIT, "Sanskrit", ("Devanagari",), ("sa", "san", "san_deva")
    ),
    Language.TAMIL: LanguageProfile(
        Language.TAMIL, "Tamil", ("Tamil",), ("ta", "tam", "tam_taml")
    ),
    Language.TELUGU: LanguageProfile(
        Language.TELUGU, "Telugu", ("Telugu",), ("te", "tel", "tel_telu")
    ),
    Language.URDU: LanguageProfile(
        Language.URDU, "Urdu", ("Arabic",), ("ur", "urd", "urd_arab")
    ),
}

_ALIAS_TO_LANGUAGE = {
    alias.casefold(): profile.language
    for profile in LANGUAGE_PROFILES.values()
    for alias in profile.aliases
}
_SCRIPT_DEFAULTS = {
    "Arabic": Language.URDU,
    "Bengali": Language.BENGALI,
    "Devanagari": Language.HINDI,
    "Gujarati": Language.GUJARATI,
    "Gurmukhi": Language.PUNJABI,
    "Kannada": Language.KANNADA,
    "Latin": Language.ENGLISH,
    "Malayalam": Language.MALAYALAM,
    "Odia": Language.ODIA,
    "Tamil": Language.TAMIL,
    "Telugu": Language.TELUGU,
}
_SCRIPT_RANGES = {
    "Arabic": ((0x0600, 0x06FF), (0x0750, 0x077F)),
    "Bengali": ((0x0980, 0x09FF),),
    "Devanagari": ((0x0900, 0x097F),),
    "Gujarati": ((0x0A80, 0x0AFF),),
    "Gurmukhi": ((0x0A00, 0x0A7F),),
    "Kannada": ((0x0C80, 0x0CFF),),
    "Malayalam": ((0x0D00, 0x0D7F),),
    "Odia": ((0x0B00, 0x0B7F),),
    "Tamil": ((0x0B80, 0x0BFF),),
    "Telugu": ((0x0C00, 0x0C7F),),
}


def language_from_tag(value: str | None) -> Language:
    normalized = (value or "").strip().casefold().replace("-", "_")
    if not normalized:
        return Language.UNKNOWN
    direct = _ALIAS_TO_LANGUAGE.get(normalized)
    if direct is not None:
        return direct
    prefix = normalized.split("_", 1)[0]
    return _ALIAS_TO_LANGUAGE.get(prefix, Language.UNKNOWN)


def _script_for_character(character: str) -> str | None:
    codepoint = ord(character)
    if ("A" <= character <= "Z") or ("a" <= character <= "z"):
        return "Latin"
    for script, ranges in _SCRIPT_RANGES.items():
        if any(start <= codepoint <= end for start, end in ranges):
            return script
    return None


def _languages_for_scripts(scripts: tuple[str, ...]) -> tuple[Language, ...]:
    found: list[Language] = []
    for script in scripts:
        for profile in LANGUAGE_PROFILES.values():
            if script in profile.scripts and profile.language not in found:
                found.append(profile.language)
    return tuple(found)


def analyze_language(
    text: str,
    *,
    hint: Language | None = None,
    language_confidence: float | None = None,
) -> LanguageAnalysis:
    counts: dict[str, int] = {}
    for character in text:
        script = _script_for_character(character)
        if script is not None:
            counts[script] = counts.get(script, 0) + 1
    scripts = tuple(sorted(counts, key=lambda item: (-counts[item], item)))
    component_languages = _languages_for_scripts(scripts)
    concrete_hint = hint not in {None, Language.UNKNOWN, Language.CODE_MIXED}
    if hint == Language.CODE_MIXED:
        return LanguageAnalysis(
            language=Language.CODE_MIXED,
            scripts=scripts,
            component_languages=component_languages,
            code_mixed=True,
            confidence=language_confidence,
            source="provider_hint",
            ambiguous=False,
            fallback_used=False,
        )
    if concrete_hint:
        assert hint is not None
        profile = LANGUAGE_PROFILES[hint]
        mismatch = bool(scripts) and not set(profile.scripts).intersection(scripts)
        is_code_mixed = len(scripts) > 1
        effective_language = Language.CODE_MIXED if is_code_mixed else hint
        return LanguageAnalysis(
            language=effective_language,
            scripts=scripts,
            component_languages=tuple(dict.fromkeys((hint, *component_languages))),
            code_mixed=is_code_mixed,
            confidence=language_confidence,
            source="provider_hint" if not is_code_mixed else "script_codemix",
            ambiguous=mismatch or len(profile.scripts) != 1,
            fallback_used=False,
            hint_script_mismatch=mismatch,
        )
    if not scripts:
        return LanguageAnalysis(
            language=Language.UNKNOWN,
            scripts=(),
            component_languages=(),
            code_mixed=False,
            confidence=None,
            source="fallback",
            ambiguous=True,
            fallback_used=True,
        )
    total = sum(counts.values())
    local_confidence = counts[scripts[0]] / total
    if len(scripts) > 1:
        return LanguageAnalysis(
            language=Language.CODE_MIXED,
            scripts=scripts,
            component_languages=component_languages,
            code_mixed=True,
            confidence=local_confidence,
            source="script",
            ambiguous=len(component_languages) > len(scripts),
            fallback_used=False,
        )
    candidates = component_languages
    chosen = _SCRIPT_DEFAULTS[scripts[0]]
    ambiguous = len(candidates) > 1
    return LanguageAnalysis(
        language=chosen,
        scripts=scripts,
        component_languages=candidates,
        code_mixed=False,
        confidence=local_confidence,
        source="script_fallback" if ambiguous else "script",
        ambiguous=ambiguous,
        fallback_used=ambiguous,
    )
