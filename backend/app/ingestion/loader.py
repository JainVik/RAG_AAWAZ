from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.models import CorpusDocument
from app.ingestion.deduplicate import canonical_document_id
from app.ingestion.normalize import normalize_text

PASSAGE_TEXT_KEYS = (
    "English_passages",
    "passage_text",
    "text",
    "english_passage",
    "Eng_Passage",
    "passage",
)
TRANSLATED_PASSAGE_KEYS = (
    "Translated_passages",
    "translated_passage",
    "passage_text_translated",
    "translation",
    "Translated_Passage",
)
PASSAGES_CONTAINER_KEYS = ("passages", "Passages", "candidates")
QUERY_ID_KEYS = ("query_id", "qid", "Query_ID", "id")
SELECTED_KEYS = ("is_selected", "selected", "relevance", "label")

# These keys are evaluation-only and must never enter a searchable document or payload.
PROHIBITED_INDEX_KEYS = frozenset(
    {
        "query",
        "translated_query",
        "english_query",
        "eng_query",
        "answer",
        "answers",
        "eng_answer",
        "english_answer",
        "is_selected",
        "relevance",
        "label",
    }
)


@dataclass(frozen=True, slots=True)
class PassageCandidate:
    query_id: str
    position: int
    english_text: str
    translated_text: str | None
    language: str | None
    translation_model: str | None
    is_selected: bool | None


@dataclass(frozen=True, slots=True)
class EvaluationFixture:
    query_id: str
    query: str
    translated_query: str | None
    relevant_canonical_ids: tuple[str, ...]
    answer_references: tuple[str, ...]


def _first(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    lowered = {str(key).casefold(): value for key, value in mapping.items()}
    for key in keys:
        if key.casefold() in lowered:
            return lowered[key.casefold()]
    return None


def _as_rows(container: Any) -> list[dict[str, Any]]:
    if isinstance(container, list):
        return [dict(item) for item in container if isinstance(item, Mapping)]
    if not isinstance(container, Mapping):
        return []
    lengths = [len(value) for value in container.values() if isinstance(value, list)]
    if not lengths:
        return [dict(container)]
    if len(set(lengths)) != 1:
        raise ValueError(f"Parallel passage arrays have unequal lengths: {lengths}")
    row_count = max(lengths)
    rows: list[dict[str, Any]] = []
    for index in range(row_count):
        row: dict[str, Any] = {}
        for key, value in container.items():
            row[str(key)] = (
                value[index] if isinstance(value, list) and index < len(value) else value
            )
        rows.append(row)
    return rows


def extract_passage_candidates(record: Mapping[str, Any]) -> list[PassageCandidate]:
    query_id = str(_first(record, QUERY_ID_KEYS) or "")
    container = _first(record, PASSAGES_CONTAINER_KEYS)
    raw_rows = _as_rows(container)
    if not raw_rows and _first(record, PASSAGE_TEXT_KEYS):
        raw_rows = [dict(record)]

    candidates: list[PassageCandidate] = []
    for position, passage in enumerate(raw_rows):
        english = normalize_text(str(_first(passage, PASSAGE_TEXT_KEYS) or ""))
        if not english:
            continue
        translated_raw = _first(passage, TRANSLATED_PASSAGE_KEYS)
        translated = normalize_text(str(translated_raw)) if translated_raw else None
        selected_raw = _first(passage, SELECTED_KEYS)
        if selected_raw is None:
            selected = None
        elif isinstance(selected_raw, str):
            selected = selected_raw.strip().casefold() in {"1", "true", "yes"}
        else:
            selected = bool(selected_raw)
        raw_meta = record.get("meta")
        meta: Mapping[str, Any] = raw_meta if isinstance(raw_meta, Mapping) else {}
        candidates.append(
            PassageCandidate(
                query_id=query_id,
                position=position,
                english_text=english,
                translated_text=translated,
                language=str(
                    _first(passage, ("language", "translation_language", "lang"))
                    or record.get("target_lang")
                    or ""
                )
                or None,
                translation_model=str(
                    _first(passage, ("translation_model", "model"))
                    or _first(meta, ("model_name", "model"))
                    or ""
                )
                or None,
                is_selected=selected,
            )
        )
    return candidates


def record_to_documents(record: Mapping[str, Any]) -> list[CorpusDocument]:
    documents: list[CorpusDocument] = []
    for candidate in extract_passage_candidates(record):
        canonical_id = canonical_document_id(candidate.english_text)
        documents.append(
            CorpusDocument(
                canonical_doc_id=canonical_id,
                parent_id=canonical_id,
                english_text=candidate.english_text,
                translated_text=candidate.translated_text,
                translation_language=candidate.language,
                translation_model=candidate.translation_model,
                source_id=None,
            )
        )
    return documents


def record_to_evaluation_fixture(record: Mapping[str, Any]) -> EvaluationFixture:
    candidates = extract_passage_candidates(record)
    query_id = str(_first(record, QUERY_ID_KEYS) or "")
    query = normalize_text(str(_first(record, ("Eng_Query", "english_query")) or ""))
    translated = _first(
        record, ("query", "translated_query", "query_translation", "Translated_Query")
    )
    answers_raw = _first(record, ("answers", "Answer", "answer", "Eng_Answer"))
    answers: tuple[str, ...]
    if isinstance(answers_raw, str):
        answers = (normalize_text(answers_raw),) if answers_raw.strip() else ()
    elif isinstance(answers_raw, Iterable):
        answers = tuple(normalize_text(str(item)) for item in answers_raw if str(item).strip())
    else:
        answers = ()
    relevant = tuple(
        canonical_document_id(item.english_text) for item in candidates if item.is_selected
    )
    return EvaluationFixture(
        query_id=query_id,
        query=query,
        translated_query=normalize_text(str(translated)) if translated else None,
        relevant_canonical_ids=relevant,
        answer_references=answers,
    )


def unique_documents(records: Iterable[Mapping[str, Any]], limit: int) -> Iterator[CorpusDocument]:
    seen: set[str] = set()
    for record in records:
        for document in record_to_documents(record):
            if document.canonical_doc_id in seen:
                continue
            seen.add(document.canonical_doc_id)
            yield document
            if len(seen) >= limit:
                return


def assert_index_payload_is_leak_free(payload: Mapping[str, Any]) -> None:
    offending = PROHIBITED_INDEX_KEYS.intersection(key.casefold() for key in payload)
    if offending:
        raise ValueError(f"Evaluation-only fields found in indexed payload: {sorted(offending)}")
