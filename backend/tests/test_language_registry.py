from __future__ import annotations

from app.domain.enums import Language
from app.domain.languages import analyze_language, language_from_tag
from app.domain.models import CorpusDocument
from app.ingestion.chunk_factory import ChunkFactory
from app.retrieval.router import TideRouter


def test_all_msmarco_language_tags_resolve_centrally() -> None:
    assert language_from_tag("asm_Beng") == Language.ASSAMESE
    assert language_from_tag("guj_Gujr") == Language.GUJARATI
    assert language_from_tag("npi_Deva") == Language.NEPALI
    assert language_from_tag("urd_Arab") == Language.URDU
    assert language_from_tag("mr-IN") == Language.MARATHI
    assert language_from_tag("unknown") == Language.UNKNOWN


def test_script_analysis_is_structured_and_marks_shared_script_ambiguity() -> None:
    gujarati = analyze_language("ગુજરાત રાજ્ય ક્યારે બન્યું?")
    devanagari = analyze_language("गोवा राज्य कब बना?")
    marathi_hint = analyze_language("गोवा राज्य कधी बनले?", hint=Language.MARATHI)

    assert gujarati.language == Language.GUJARATI
    assert gujarati.scripts == ("Gujarati",)
    assert gujarati.fallback_used is False
    assert devanagari.language == Language.HINDI
    assert devanagari.ambiguous is True
    assert devanagari.fallback_used is True
    assert marathi_hint.language == Language.MARATHI
    assert marathi_hint.source == "provider_hint"
    assert marathi_hint.hint_script_mismatch is False


def test_code_mix_retains_component_languages_for_cross_language_search() -> None:
    analysis = analyze_language("Goa ગુજરાત ક્યારે બન્યું?")
    plan = TideRouter().route("Goa ગુજરાત ક્યારે બન્યું?")

    assert analysis.language == Language.CODE_MIXED
    assert analysis.code_mixed is True
    assert Language.ENGLISH in analysis.component_languages
    assert Language.GUJARATI in analysis.component_languages
    assert plan.representation_languages is not None
    assert plan.representation_languages[0] == Language.CODE_MIXED
    assert Language.ENGLISH in plan.representation_languages
    assert Language.GUJARATI in plan.representation_languages


def test_chunk_factory_uses_registry_instead_of_hindi_default() -> None:
    document = CorpusDocument(
        canonical_doc_id="doc",
        parent_id="parent",
        english_text="English passage.",
        translated_text="ગુજરાતી અનુવાદ.",
        translation_language="guj_Gujr",
    )

    languages = ChunkFactory.document_languages(document)
    translated = ChunkFactory().atomic(document, Language.GUJARATI)

    assert languages == (Language.ENGLISH, Language.GUJARATI)
    assert translated[0].text == document.translated_text
    assert translated[0].language == Language.GUJARATI


def test_explicit_language_hint_supports_romanized_indic_queries() -> None:
    plan = TideRouter().route(
        "Goa rajya kab bana?",
        language_hint=Language.HINDI,
        language_confidence=0.91,
    )

    assert plan.language == Language.HINDI
    assert plan.representation_languages == (Language.HINDI, Language.CODE_MIXED)
    assert plan.language_confidence == 0.91
    assert plan.scripts == ("Latin",)
    assert plan.romanized_hindi is True

    tagged = TideRouter().route("Goa rajya kab bana?", language_hint="hin_Deva")
    assert tagged.language == Language.HINDI
