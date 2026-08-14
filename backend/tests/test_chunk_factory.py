from __future__ import annotations

import pytest

from app.domain.enums import ChunkStrategy, Language
from app.domain.models import CorpusDocument
from app.ingestion.chunk_factory import ChunkFactory, sentence_spans


def document(text: str, translated: str | None = None) -> CorpusDocument:
    return CorpusDocument(
        canonical_doc_id="doc",
        parent_id="doc",
        english_text=text,
        translated_text=translated,
        translation_language="hin_Deva" if translated else None,
    )


@pytest.mark.parametrize(
    ("text", "first_sentence"),
    [
        ("The rate is 3.5 percent. It later fell.", "The rate is 3.5 percent."),
        (
            "Dr. Ambedkar chaired the committee. It met often.",
            "Dr. Ambedkar chaired the committee.",
        ),
        ("See https://example.com/path. Then continue.", "See https://example.com/path."),
        ("U.S. policy changed. The record reflects it.", "U.S. policy changed."),
    ],
)
def test_sentence_spans_preserve_decimal_abbreviation_and_url_periods(
    text: str, first_sentence: str
) -> None:
    spans = sentence_spans(text)

    assert spans[0].text == first_sentence
    assert text[spans[0].start : spans[0].end] == first_sentence


def test_sentence_windows_preserve_spans_and_one_sentence_overlap() -> None:
    parent = document("One. Two. Three. Four. Five.")
    chunks = ChunkFactory(sentence_window_size=3, sentence_overlap=1).sentence_windows(parent)

    assert [chunk.text for chunk in chunks] == ["One. Two. Three.", "Three. Four. Five."]
    assert chunks[0].text == parent.english_text[chunks[0].span_start : chunks[0].span_end]
    assert chunks[1].text == parent.english_text[chunks[1].span_start : chunks[1].span_end]
    assert "Three." in chunks[0].text and chunks[1].text.startswith("Three.")


def test_semantic_splitting_bypasses_short_passages() -> None:
    factory = ChunkFactory(sentence_embedder=lambda texts: [[1.0, 0.0] for _ in texts])
    chunks = factory.semantic_sections(document("One sentence. Two sentences. Three sentences."))
    assert chunks == []


def test_semantic_sections_are_exact_parent_spans() -> None:
    vectors = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9]]
    factory = ChunkFactory(sentence_embedder=lambda texts: vectors)
    parent = document(
        "First useful sentence. Second related sentence. Third different sentence. "
        "Fourth related sentence."
    )
    chunks = factory.semantic_sections(parent)

    assert chunks
    assert all(chunk.strategy == ChunkStrategy.SEMANTIC_SECTION for chunk in chunks)
    assert all(
        chunk.text == parent.english_text[chunk.span_start : chunk.span_end] for chunk in chunks
    )


def test_semantic_cap_applies_to_short_interleaved_sentences_in_emitted_span() -> None:
    parent = document(
        "First useful statement. Yes. No. Maybe. Second useful statement. "
        "Fine. Third useful statement. Okay. Fourth useful statement."
    )
    vectors = [[1.0, 0.0], [0.99, 0.01], [0.98, 0.02], [0.97, 0.03]]
    chunks = ChunkFactory(
        semantic_max_words=6,
        sentence_embedder=lambda texts: vectors,
    ).semantic_sections(parent)

    assert chunks
    assert all(len(chunk.text.split()) <= 6 for chunk in chunks)
    assert all(
        chunk.text == parent.english_text[chunk.span_start : chunk.span_end] for chunk in chunks
    )


def test_semantic_cap_splits_one_oversized_sentence_into_exact_source_spans() -> None:
    parent = document(
        "One two three four five six seven eight nine ten eleven twelve. "
        "Second useful sentence. Third useful sentence. Fourth useful sentence."
    )
    vectors = [[1.0, 0.0], [0.99, 0.01], [0.98, 0.02], [0.97, 0.03]]
    chunks = ChunkFactory(
        semantic_max_words=5,
        sentence_embedder=lambda texts: vectors,
    ).semantic_sections(parent)

    assert chunks
    assert all(len(chunk.text.split()) <= 5 for chunk in chunks)
    assert any(chunk.metadata["oversized_sentence_split"] for chunk in chunks)
    assert all(
        chunk.text == parent.english_text[chunk.span_start : chunk.span_end] for chunk in chunks
    )


def test_bilingual_view_keeps_shared_canonical_identity() -> None:
    parent = document("Goa became a state in 1987.", "गोवा 1987 में राज्य बना।")
    paired = ChunkFactory().bilingual_paired(parent)[0]

    assert paired.canonical_doc_id == parent.canonical_doc_id
    assert paired.parent_id == parent.parent_id
    assert paired.language == Language.CODE_MIXED
    assert paired.strategy == ChunkStrategy.BILINGUAL_PAIRED
    assert "[EN]" in paired.text


def test_all_enabled_has_unique_ids_for_single_sentence_translation() -> None:
    parent = document("One English sentence.", "Eka anuvadita vakya.")

    chunks = ChunkFactory().all_enabled(parent, enable_semantic=False)
    chunk_ids = [chunk.chunk_id for chunk in chunks]

    assert len(chunk_ids) == len(set(chunk_ids))
    for language in (Language.ENGLISH, Language.HINDI):
        atomic = next(
            chunk
            for chunk in chunks
            if chunk.language == language and chunk.strategy == ChunkStrategy.ATOMIC
        )
        window = next(
            chunk
            for chunk in chunks
            if chunk.language == language and chunk.strategy == ChunkStrategy.SENTENCE_WINDOW
        )
        assert atomic.chunk_id != window.chunk_id
        assert window.metadata["single_sentence_geometry"] == "atomic_span"


def test_all_enabled_rejects_an_empty_strategy_set() -> None:
    with pytest.raises(ValueError, match="at least one enabled strategy"):
        ChunkFactory().all_enabled(
            document("One sentence."),
            enable_atomic=False,
            enable_sentence_window=False,
            enable_semantic=False,
            enable_parent_child=False,
            enable_bilingual=False,
        )


def test_translated_chunk_language_tracks_corpus_metadata() -> None:
    parent = CorpusDocument(
        canonical_doc_id="marathi-doc",
        parent_id="marathi-doc",
        english_text="One English sentence.",
        translated_text="Eka Marathi vakya.",
        translation_language="mar_Deva",
    )

    chunks = ChunkFactory().all_enabled(parent, enable_semantic=False)

    translated_chunks = [
        chunk
        for chunk in chunks
        if chunk.strategy != ChunkStrategy.BILINGUAL_PAIRED and chunk.language != Language.ENGLISH
    ]
    assert translated_chunks
    assert {chunk.language for chunk in translated_chunks} == {Language.MARATHI}


def test_bilingual_pairs_are_bounded_and_have_unambiguous_spans() -> None:
    parent = document(
        "English source section " * 12,
        "Translated source section " * 15,
    )
    maximum = 64

    chunks = ChunkFactory(bilingual_max_characters=maximum).bilingual_paired(parent)

    assert len(chunks) > 1
    translated_source_spans: set[tuple[int, int]] = set()
    english_source_spans: set[tuple[int, int]] = set()
    for chunk in chunks:
        metadata = chunk.metadata
        translated_span = tuple(metadata["translated_source_span"])
        english_span = tuple(metadata["english_source_span"])
        translated_representation = tuple(metadata["translated_representation_span"])
        english_representation = tuple(metadata["english_representation_span"])
        assert len(chunk.text) <= maximum
        assert chunk.span_start == 0
        assert chunk.span_end == len(chunk.text)
        assert metadata["span_coordinate_system"] == "paired_representation"
        assert metadata["representation_span"] == [0, len(chunk.text)]
        assert (
            chunk.text[slice(*translated_representation)]
            == parent.translated_text[slice(*translated_span)]
        )
        assert (
            chunk.text[slice(*english_representation)] == parent.english_text[slice(*english_span)]
        )
        translated_source_spans.add(translated_span)
        english_source_spans.add(english_span)

    translated_parts = [
        parent.translated_text[slice(*span)] for span in sorted(translated_source_spans)
    ]
    english_parts = [parent.english_text[slice(*span)] for span in sorted(english_source_spans)]
    assert "".join(translated_parts) == parent.translated_text
    assert "".join(english_parts) == parent.english_text
