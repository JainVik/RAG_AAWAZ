from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from app.ingestion.normalize import normalize_text

DATASET_ID = "ai4bharat/MSMARCO-XI"
DATASET_REVISION = "bf5cdc1f26e581e519018e434db14edd1b77602b"
AUDIT_REPORT_VERSION = 2
DEFAULT_STREAM_BATCH_SIZE = 64
DEFAULT_SHORT_PASSAGE_CHARS = 20
DEFAULT_MAX_MALFORMED_EXAMPLES = 20
DEFAULT_CANDIDATE_CORPUS_SIZES = (10_000, 25_000, 50_000, 100_000)
DEFAULT_DENSE_VECTOR_SIZE = 384
DEFAULT_EMBEDDING_VECTORS_PER_SECOND = 25.0
DEFAULT_UPSERT_POINTS_PER_SECOND = 1_000.0

LANGUAGE_FILES: dict[str, str] = {
    "as": "asm",
    "bn": "ben",
    "gu": "guj",
    "hi": "hin",
    "kn": "kan",
    "ml": "mal",
    "mr": "mar",
    "ne": "nep",
    "or": "ori",
    "pa": "pan",
    "sa": "san",
    "ta": "tam",
    "te": "tel",
    "ur": "urd",
}

LANGUAGE_NAMES: dict[str, str] = {
    "as": "Assamese",
    "bn": "Bengali",
    "gu": "Gujarati",
    "hi": "Hindi",
    "kn": "Kannada",
    "ml": "Malayalam",
    "mr": "Marathi",
    "ne": "Nepali",
    "or": "Odia",
    "pa": "Punjabi",
    "sa": "Sanskrit",
    "ta": "Tamil",
    "te": "Telugu",
    "ur": "Urdu",
}

TARGET_LANGUAGE_TAGS: dict[str, str] = {
    "as": "asm_Beng",
    "bn": "ben_Beng",
    "gu": "guj_Gujr",
    "hi": "hin_Deva",
    "kn": "kan_Knda",
    "ml": "mal_Mlym",
    "mr": "mar_Deva",
    "ne": "npi_Deva",
    "or": "ory_Orya",
    "pa": "pan_Guru",
    "sa": "san_Deva",
    "ta": "tam_Taml",
    "te": "tel_Telu",
    "ur": "urd_Arab",
}

EXPECTED_SCHEMA: dict[str, Any] = {
    "source_lang": "string",
    "target_lang": "string",
    "meta": {
        "frequency_penalty": "int64",
        "max_tokens": "int64",
        "model_name": "string",
        "presence_penalty": "int64",
        "temperature": "int64",
        "top_p": "int64",
    },
    "Answer": "string",
    "query_id": "int64",
    "query_type": "string",
    "passages": {
        "English_passages": "list<string>",
        "Translated_passages": "list<string>",
        "is_selected": "list<int64>",
    },
    "Eng_Query": "string",
    "Eng_Answer": "string",
    "query": "string",
}

EXPECTED_FIELD_PATHS = (
    "source_lang",
    "target_lang",
    "meta",
    "meta.frequency_penalty",
    "meta.max_tokens",
    "meta.model_name",
    "meta.presence_penalty",
    "meta.temperature",
    "meta.top_p",
    "Answer",
    "query_id",
    "query_type",
    "passages",
    "passages.English_passages",
    "passages.Translated_passages",
    "passages.is_selected",
    "Eng_Query",
    "Eng_Answer",
    "query",
)

PASSAGE_ARRAY_FIELDS = (
    "English_passages",
    "Translated_passages",
    "is_selected",
)

TOKEN_ESTIMATE_METHOD = (
    "unicode_subword_heuristic_v1: Latin/alphanumeric runs=ceil(chars/4), "
    "non-Latin runs=ceil(chars/2), punctuation=1; this is an estimate, not a model tokenizer"
)

_MISSING = object()
_WORD = re.compile(r"\w+", flags=re.UNICODE)
_TOKEN_PIECE = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)
_SENTENCE_TERMINATOR = re.compile(r"[.!?\u0964\u0965]+")
_LATIN_OR_NUMBER = re.compile(r"^[A-Za-z0-9_]+$")


class DatasetFileUnavailable(ValueError):
    """Raised when a requested language/split has no physical Parquet file."""


def parquet_path(language: str, split: str) -> str:
    if language not in LANGUAGE_FILES:
        raise ValueError(f"Unsupported MSMARCO-XI language: {language}")
    if split not in {"train", "validation"}:
        raise ValueError(f"Unsupported MSMARCO-XI split: {split}")
    if language == "te" and split == "train":
        raise DatasetFileUnavailable("MSMARCO-XI has no Telugu train Parquet file")
    suffix = "train" if split == "train" else "val"
    return f"{split}/{LANGUAGE_FILES[language]}{suffix}.parquet"


def parquet_uri(language: str, split: str, *, revision: str = DATASET_REVISION) -> str:
    return f"hf://datasets/{DATASET_ID}@{revision}/{parquet_path(language, split)}"


def stream_dataset(
    language: str,
    split: str,
    *,
    batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
    columns: Sequence[str] | None = None,
    revision: str = DATASET_REVISION,
) -> Any:
    """Open one physical language file without invoking the repository's legacy script."""

    if batch_size < 1 or batch_size > 4096:
        raise ValueError("batch_size must be between 1 and 4096 for bounded streaming")
    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - depends on the data extra
        raise RuntimeError("Install the project's data extra to stream MSMARCO-XI") from exc

    kwargs: dict[str, Any] = {
        "path": "parquet",
        "data_files": {split: parquet_uri(language, split, revision=revision)},
        "split": split,
        "streaming": True,
        # Each live source file is one multi-gigabyte row group. The packaged
        # Parquet builder otherwise defaults its output batch to the row group.
        "batch_size": batch_size,
    }
    if columns is not None:
        kwargs["columns"] = list(columns)
    return load_dataset(**kwargs)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    # Hugging Face ``Features`` is itself a Mapping, but its values are feature
    # objects. Prefer its canonical serializer before generic Mapping handling.
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    if isinstance(value, Mapping):
        ordered = sorted(value.items(), key=lambda item: str(item[0]))
        return {str(key): _json_safe(item) for key, item in ordered}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_safe(item) for item in value]
    return str(value)


def schema_to_dict(schema: Any) -> dict[str, Any] | None:
    if schema is None:
        return None
    converted = _json_safe(schema)
    if not isinstance(converted, dict):
        raise TypeError("observed schema must serialize to a mapping")
    return converted


def _flatten_schema_node(
    node: Any,
    *,
    path: str,
    result: dict[str, str],
    list_depth: int = 0,
) -> None:
    if isinstance(node, str):
        result[path] = f"{'list<' * list_depth}{node}{'>' * list_depth}"
        return
    if isinstance(node, list):
        if len(node) == 1:
            _flatten_schema_node(node[0], path=path, result=result, list_depth=list_depth + 1)
        return
    if not isinstance(node, Mapping):
        return

    node_type = str(node.get("_type", ""))
    if "dtype" in node and node_type in {"", "Value"}:
        dtype = str(node["dtype"])
        result[path] = f"{'list<' * list_depth}{dtype}{'>' * list_depth}"
        return
    if node_type in {"Sequence", "List", "LargeList"} and "feature" in node:
        _flatten_schema_node(
            node["feature"], path=path, result=result, list_depth=list_depth + 1
        )
        return

    for key, child in sorted(node.items(), key=lambda item: str(item[0])):
        if str(key).startswith("_") or key in {"dtype", "feature", "length"}:
            continue
        child_path = f"{path}.{key}" if path else str(key)
        _flatten_schema_node(child, path=child_path, result=result, list_depth=list_depth)


def flatten_schema(schema: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in sorted(schema.items()):
        _flatten_schema_node(value, path=str(key), result=result)
    return result


def schema_contract(observed_schema: Any) -> dict[str, Any]:
    observed = schema_to_dict(observed_schema)
    expected_leaf_types = flatten_schema(EXPECTED_SCHEMA)
    if observed is None:
        return {
            "matches": False,
            "status": "not_observed",
            "expected": EXPECTED_SCHEMA,
            "observed": None,
            "expected_leaf_types": expected_leaf_types,
            "observed_leaf_types": {},
            "missing_paths": sorted(expected_leaf_types),
            "unexpected_paths": [],
            "type_mismatches": [],
        }

    observed_leaf_types = flatten_schema(observed)
    missing = sorted(set(expected_leaf_types) - set(observed_leaf_types))
    unexpected = sorted(set(observed_leaf_types) - set(expected_leaf_types))
    mismatches = [
        {
            "path": path,
            "expected": expected_leaf_types[path],
            "observed": observed_leaf_types[path],
        }
        for path in sorted(set(expected_leaf_types) & set(observed_leaf_types))
        if expected_leaf_types[path] != observed_leaf_types[path]
    ]
    return {
        "matches": not missing and not unexpected and not mismatches,
        "status": "matched" if not missing and not unexpected and not mismatches else "mismatch",
        "expected": EXPECTED_SCHEMA,
        "observed": observed,
        "expected_leaf_types": expected_leaf_types,
        "observed_leaf_types": observed_leaf_types,
        "missing_paths": missing,
        "unexpected_paths": unexpected,
        "type_mismatches": mismatches,
    }


def _get_path(record: Mapping[str, Any], path: str) -> Any:
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _is_empty(value: Any) -> bool:
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, Sequence | Mapping) and not isinstance(
        value, str | bytes | bytearray
    ):
        return len(value) == 0
    return False


def _field_completeness(records_seen: int, counters: Mapping[str, Counter[str]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path in EXPECTED_FIELD_PATHS:
        counts = counters[path]
        missing = counts["missing"]
        null = counts["null"]
        empty = counts["empty"]
        denominator = records_seen or 1
        result[path] = {
            "missing_count": missing,
            "null_count": null,
            "empty_count": empty,
            "missing_rate": round(missing / denominator, 6),
            "null_rate": round(null / denominator, 6),
            "missing_or_null_rate": round((missing + null) / denominator, 6),
            "empty_rate": round(empty / denominator, 6),
        }
    return result


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def sentence_count(text: str) -> int:
    normalized = normalize_text(text)
    if not normalized:
        return 0
    terminators = len(_SENTENCE_TERMINATOR.findall(normalized))
    tail = _SENTENCE_TERMINATOR.split(normalized)[-1].strip()
    return terminators + (1 if tail else 0)


def estimate_model_tokens(text: str) -> int:
    total = 0
    for piece in _TOKEN_PIECE.findall(normalize_text(text)):
        if len(piece) == 1 and not piece.isalnum() and piece != "_":
            total += 1
        elif _LATIN_OR_NUMBER.fullmatch(piece):
            total += max(1, math.ceil(len(piece) / 4))
        else:
            total += max(1, math.ceil(len(piece) / 2))
    return total


def _nearest_rank(sorted_values: Sequence[int], percentile: int) -> int | None:
    if not sorted_values:
        return None
    if percentile <= 0:
        return sorted_values[0]
    index = min(len(sorted_values) - 1, math.ceil(percentile / 100 * len(sorted_values)) - 1)
    return sorted_values[index]


def _distribution(values: Sequence[int]) -> dict[str, Any]:
    ordered = sorted(values)
    if not ordered:
        return {
            "count": 0,
            "min": None,
            "p25": None,
            "p50": None,
            "p70": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "p100": None,
            "max": None,
            "mean": None,
        }
    return {
        "count": len(ordered),
        "min": ordered[0],
        "p25": _nearest_rank(ordered, 25),
        "p50": _nearest_rank(ordered, 50),
        "p70": _nearest_rank(ordered, 70),
        "p75": _nearest_rank(ordered, 75),
        "p90": _nearest_rank(ordered, 90),
        "p95": _nearest_rank(ordered, 95),
        "p99": _nearest_rank(ordered, 99),
        "p100": ordered[-1],
        "max": ordered[-1],
        "mean": round(sum(ordered) / len(ordered), 6),
    }


def _duplicate_summary(counter: Counter[str]) -> dict[str, Any]:
    total = counter.total()
    unique = len(counter)
    duplicate_occurrences = max(0, total - unique)
    return {
        "nonempty_occurrences": total,
        "unique_values": unique,
        "duplicate_occurrences": duplicate_occurrences,
        "duplicate_rate": round(duplicate_occurrences / total, 6) if total else 0.0,
    }


def _lengths_for_text(text: str, accumulator: dict[str, list[int]]) -> None:
    accumulator["characters"].append(len(text))
    accumulator["words"].append(word_count(text))
    accumulator["sentences"].append(sentence_count(text))
    accumulator["model_token_estimate"].append(estimate_model_tokens(text))


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _length_accumulator() -> dict[str, list[int]]:
    return {
        "characters": [],
        "words": [],
        "sentences": [],
        "model_token_estimate": [],
    }


def _sentence_window_count(text: str, *, size: int = 3, overlap: int = 1) -> int:
    sentences = sentence_count(text)
    if sentences <= 1:
        return 1 if text else 0
    step = size - overlap
    return max(1, math.ceil(max(0, sentences - size) / step) + 1)


def _corpus_scale_estimates(
    *,
    unique_passages: int,
    strategy_vectors: Counter[str],
    strategy_payload_bytes: Counter[str],
    candidate_sizes: Sequence[int],
    dense_vector_size: int,
    embedding_vectors_per_second: float,
    upsert_points_per_second: float,
) -> dict[str, Any]:
    hnsw_multiplier = 1.35
    sparse_bytes_per_vector = 2_048
    assumptions = {
        "dense_vector_size": dense_vector_size,
        "dense_value_bytes": 4,
        "hnsw_multiplier": hnsw_multiplier,
        "sparse_bytes_per_vector": sparse_bytes_per_vector,
        "embedding_vectors_per_second": embedding_vectors_per_second,
        "upsert_points_per_second": upsert_points_per_second,
        "note": (
            "Planning estimates extrapolated from the bounded sample. HNSW, sparse, "
            "embedding, and upsert factors are explicit heuristics, not measured results."
        ),
    }
    if unique_passages <= 0:
        return {"assumptions": assumptions, "candidate_sizes": []}
    rows: list[dict[str, Any]] = []
    for target in candidate_sizes:
        strategy_counts = {
            strategy: round(count / unique_passages * target)
            for strategy, count in sorted(strategy_vectors.items())
        }
        total_vectors = sum(strategy_counts.values())
        payload_bytes = round(
            sum(strategy_payload_bytes.values()) / unique_passages * target
        )
        dense_bytes = total_vectors * dense_vector_size * 4
        sparse_bytes = total_vectors * sparse_bytes_per_vector
        qdrant_bytes = round(dense_bytes * hnsw_multiplier)
        qdrant_bytes += sparse_bytes + payload_bytes
        rows.append(
            {
                "target_unique_passages": target,
                "estimated_vectors_by_strategy": strategy_counts,
                "estimated_total_vectors": total_vectors,
                "estimated_dense_vector_bytes": dense_bytes,
                "estimated_sparse_vector_bytes": sparse_bytes,
                "estimated_payload_bytes": payload_bytes,
                "estimated_qdrant_bytes": qdrant_bytes,
                "estimated_embedding_seconds": round(
                    total_vectors / embedding_vectors_per_second, 3
                ),
                "estimated_upsert_seconds": round(
                    total_vectors / upsert_points_per_second, 3
                ),
            }
        )
    return {"assumptions": assumptions, "candidate_sizes": rows}


def audit_records(
    records: Iterable[Mapping[str, Any]],
    *,
    language: str,
    split: str,
    max_rows: int,
    observed_schema: Any = None,
    batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
    short_passage_chars: int = DEFAULT_SHORT_PASSAGE_CHARS,
    max_malformed_examples: int = DEFAULT_MAX_MALFORMED_EXAMPLES,
    token_counter: Callable[[str], int] = estimate_model_tokens,
    token_method: str = TOKEN_ESTIMATE_METHOD,
    candidate_corpus_sizes: Sequence[int] = DEFAULT_CANDIDATE_CORPUS_SIZES,
    dense_vector_size: int = DEFAULT_DENSE_VECTOR_SIZE,
    embedding_vectors_per_second: float = DEFAULT_EMBEDDING_VECTORS_PER_SECOND,
    upsert_points_per_second: float = DEFAULT_UPSERT_POINTS_PER_SECOND,
) -> dict[str, Any]:
    """Audit a bounded deterministic stream prefix without retaining source rows."""

    if language not in LANGUAGE_FILES:
        raise ValueError(f"Unsupported MSMARCO-XI language: {language}")
    parquet_path(language, split)
    if max_rows < 1:
        raise ValueError("max_rows must be positive")
    if short_passage_chars < 0:
        raise ValueError("short_passage_chars must be non-negative")
    if max_malformed_examples < 0:
        raise ValueError("max_malformed_examples must be non-negative")
    if not candidate_corpus_sizes or any(size < 1 for size in candidate_corpus_sizes):
        raise ValueError("candidate_corpus_sizes must contain positive values")
    if dense_vector_size < 1:
        raise ValueError("dense_vector_size must be positive")
    if embedding_vectors_per_second <= 0 or upsert_points_per_second <= 0:
        raise ValueError("throughput assumptions must be positive")

    field_counters: dict[str, Counter[str]] = {
        path: Counter() for path in EXPECTED_FIELD_PATHS
    }
    answer_field_presence = Counter[str]()
    source_languages = Counter[str]()
    target_languages = Counter[str]()
    language_pairs = Counter[str]()
    translation_models = Counter[str]()
    translation_profiles = Counter[str]()
    query_types = Counter[str]()
    query_ids: set[str] = set()
    english_query_duplicates = Counter[str]()
    translated_query_duplicates = Counter[str]()
    english_duplicates = Counter[str]()
    translated_duplicates = Counter[str]()
    passage_query_ids: dict[str, set[str]] = defaultdict(set)
    strategy_vectors = Counter[str]()
    strategy_payload_bytes = Counter[str]()
    malformed_examples: list[dict[str, Any]] = []

    english_lengths = _length_accumulator()
    translated_lengths = _length_accumulator()
    english_query_lengths = _length_accumulator()
    translated_query_lengths = _length_accumulator()
    english_answer_lengths = _length_accumulator()
    translated_answer_lengths = _length_accumulator()
    passages_per_query: list[int] = []
    selected_passages_per_query: list[int] = []

    counts = Counter[str]()
    for sample_index, record in enumerate(records):
        if sample_index >= max_rows:
            break
        counts["rows_sampled"] += 1
        reasons: list[str] = []
        short_candidates: list[dict[str, Any]] = []

        if not isinstance(record, Mapping):
            for path in EXPECTED_FIELD_PATHS:
                field_counters[path]["missing"] += 1
            reasons.append("record_not_mapping")
            if len(malformed_examples) < max_malformed_examples:
                malformed_examples.append(
                    {"sample_index": sample_index, "query_id": None, "reasons": reasons}
                )
            continue

        for path in EXPECTED_FIELD_PATHS:
            value = _get_path(record, path)
            if value is _MISSING:
                field_counters[path]["missing"] += 1
            elif value is None:
                field_counters[path]["null"] += 1
            elif _is_empty(value):
                field_counters[path]["empty"] += 1

        for candidate_name in ("Answer", "answers", "answer"):
            if candidate_name in record:
                answer_field_presence[candidate_name] += 1

        query_id_value = record.get("query_id")
        row_query_key = (
            str(query_id_value)
            if query_id_value is not None and str(query_id_value).strip()
            else f"sample:{sample_index}"
        )
        if query_id_value is not None and str(query_id_value).strip():
            query_ids.add(str(query_id_value))
            counts["rows_with_query_id"] += 1
        english_query = record.get("Eng_Query")
        if isinstance(english_query, str) and english_query.strip():
            normalized = normalize_text(english_query)
            counts["nonempty_english_queries"] += 1
            english_query_duplicates[normalized] += 1
            _lengths_for_text(normalized, english_query_lengths)
            english_query_lengths["model_token_estimate"][-1] = token_counter(normalized)
        translated_query = record.get("query")
        if isinstance(translated_query, str) and translated_query.strip():
            normalized = normalize_text(translated_query)
            counts["nonempty_translated_queries"] += 1
            translated_query_duplicates[normalized] += 1
            _lengths_for_text(normalized, translated_query_lengths)
            translated_query_lengths["model_token_estimate"][-1] = token_counter(normalized)
        english_answer = record.get("Eng_Answer")
        if isinstance(english_answer, str) and english_answer.strip():
            normalized = normalize_text(english_answer)
            _lengths_for_text(normalized, english_answer_lengths)
            english_answer_lengths["model_token_estimate"][-1] = token_counter(normalized)
        translated_answer = record.get("Answer")
        if isinstance(translated_answer, str) and translated_answer.strip():
            normalized = normalize_text(translated_answer)
            _lengths_for_text(normalized, translated_answer_lengths)
            translated_answer_lengths["model_token_estimate"][-1] = token_counter(normalized)
        query_type = record.get("query_type")
        if isinstance(query_type, str) and query_type.strip():
            query_types[query_type.strip()] += 1

        source_lang = record.get("source_lang")
        target_lang = record.get("target_lang")
        if isinstance(source_lang, str) and source_lang.strip():
            source_languages[source_lang] += 1
        if isinstance(target_lang, str) and target_lang.strip():
            target_languages[target_lang] += 1
        if (
            isinstance(source_lang, str)
            and source_lang.strip()
            and isinstance(target_lang, str)
            and target_lang.strip()
        ):
            language_pairs[f"{source_lang.strip()}->{target_lang.strip()}"] += 1

        meta = record.get("meta")
        if isinstance(meta, Mapping):
            model_name = meta.get("model_name")
            if isinstance(model_name, str) and model_name.strip():
                translation_models[model_name] += 1
            profile = {key: _json_safe(meta.get(key)) for key in sorted(meta)}
            translation_profiles[json.dumps(profile, ensure_ascii=False, sort_keys=True)] += 1
        elif meta is not None:
            reasons.append("meta_not_mapping")

        passages = record.get("passages")
        if not isinstance(passages, Mapping):
            reasons.append("passages_not_mapping")
            passages = {}

        arrays: dict[str, list[Any] | None] = {}
        array_lengths: dict[str, int | None] = {}
        for field in PASSAGE_ARRAY_FIELDS:
            value = passages.get(field, _MISSING)
            if isinstance(value, list):
                arrays[field] = value
                array_lengths[field] = len(value)
            else:
                arrays[field] = None
                array_lengths[field] = None
                if value is not _MISSING and value is not None:
                    reasons.append(f"passages.{field}_not_list")

        concrete_lengths = [length for length in array_lengths.values() if length is not None]
        if len(concrete_lengths) == len(PASSAGE_ARRAY_FIELDS) and len(set(concrete_lengths)) > 1:
            reasons.append("parallel_passage_array_length_mismatch")
            counts["array_mismatch_rows"] += 1

        english = arrays["English_passages"] or []
        translated = arrays["Translated_passages"] or []
        labels = arrays["is_selected"] or []
        passages_per_query.append(len(english))
        selected_passages_per_query.append(
            sum(label in {1, "1", "true", "True"} for label in labels)
        )
        counts["english_passage_occurrences"] += len(english)
        counts["translated_passage_occurrences"] += len(translated)
        counts["label_occurrences"] += len(labels)
        if english:
            counts["rows_with_passages"] += 1
        if concrete_lengths:
            counts["aligned_candidate_positions"] += min(concrete_lengths)

        for index, value in enumerate(english):
            if not isinstance(value, str):
                reasons.append(f"english_passage_{index}_not_string")
                counts["invalid_english_passages"] += 1
                continue
            normalized = normalize_text(value)
            if not normalized:
                counts["empty_english_passages"] += 1
                reasons.append(f"english_passage_{index}_empty")
                continue
            english_duplicates[normalized] += 1
            canonical_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            first_canonical_occurrence = canonical_hash not in passage_query_ids
            passage_query_ids[canonical_hash].add(row_query_key)
            _lengths_for_text(normalized, english_lengths)
            english_lengths["model_token_estimate"][-1] = token_counter(normalized)
            if len(normalized) < short_passage_chars:
                counts["short_english_passages"] += 1
                if len(short_candidates) < 3:
                    short_candidates.append(
                        {
                            "field": "English_passages",
                            "position": index,
                            "characters": len(normalized),
                            "preview": normalized[:120],
                        }
                    )
            if first_canonical_occurrence:
                translated_value = translated[index] if index < len(translated) else None
                translated_normalized = (
                    normalize_text(translated_value)
                    if isinstance(translated_value, str)
                    else ""
                )
                variants = [normalized]
                if translated_normalized:
                    variants.append(translated_normalized)
                atomic_count = len(variants)
                window_count = sum(_sentence_window_count(item) for item in variants)
                semantic_count = sum(
                    max(1, math.ceil(max(1, word_count(item)) / 180))
                    for item in variants
                )
                bilingual_count = (
                    max(
                        math.ceil(len(normalized) / 397),
                        math.ceil(len(translated_normalized) / 397),
                    )
                    if translated_normalized
                    else 0
                )
                strategy_vectors.update(
                    {
                        "atomic": atomic_count,
                        "sentence_window": window_count,
                        "semantic_section_cap_heuristic": semantic_count,
                        "parent_child": window_count,
                        "bilingual_paired": bilingual_count,
                    }
                )
                source_bytes = sum(len(item.encode("utf-8")) for item in variants)
                strategy_payload_bytes.update(
                    {
                        "atomic": source_bytes,
                        "sentence_window": round(source_bytes * 1.5),
                        "semantic_section_cap_heuristic": source_bytes,
                        "parent_child": round(source_bytes * 1.5),
                        "bilingual_paired": (
                            len(
                                f"{translated_normalized}\n[EN] {normalized}".encode()
                            )
                            if translated_normalized
                            else 0
                        ),
                    }
                )

        for index, value in enumerate(translated):
            if not isinstance(value, str):
                reasons.append(f"translated_passage_{index}_not_string")
                counts["invalid_translated_passages"] += 1
                continue
            normalized = normalize_text(value)
            if not normalized:
                counts["empty_translated_passages"] += 1
                reasons.append(f"translated_passage_{index}_empty")
                continue
            translated_duplicates[normalized] += 1
            _lengths_for_text(normalized, translated_lengths)
            translated_lengths["model_token_estimate"][-1] = token_counter(normalized)
            if len(normalized) < short_passage_chars:
                counts["short_translated_passages"] += 1
                if len(short_candidates) < 3:
                    short_candidates.append(
                        {
                            "field": "Translated_passages",
                            "position": index,
                            "characters": len(normalized),
                            "preview": normalized[:120],
                        }
                    )

        for label in labels:
            if label in {1, "1", "true", "True"}:
                counts["selected_labels"] += 1
            elif label in {0, "0", "false", "False"}:
                counts["non_selected_labels"] += 1
            else:
                counts["invalid_labels"] += 1

        if short_candidates:
            reasons.append("unexpectedly_short_passage")
        if reasons and len(malformed_examples) < max_malformed_examples:
            malformed_examples.append(
                {
                    "sample_index": sample_index,
                    "query_id": str(query_id_value) if query_id_value is not None else None,
                    "reasons": sorted(set(reasons)),
                    "array_lengths": array_lengths,
                    "short_passages": short_candidates,
                }
            )

    rows_sampled = counts["rows_sampled"]
    label_denominator = counts["selected_labels"] + counts["non_selected_labels"]
    length_distributions = {
        "normalization": "NFC and conservative whitespace/punctuation normalization",
        "token_estimate_method": token_method,
        "english_passages": {
            key: _distribution(values) for key, values in sorted(english_lengths.items())
        },
        "translated_passages": {
            key: _distribution(values) for key, values in sorted(translated_lengths.items())
        },
        "english_queries": {
            key: _distribution(values)
            for key, values in sorted(english_query_lengths.items())
        },
        "translated_queries": {
            key: _distribution(values)
            for key, values in sorted(translated_query_lengths.items())
        },
        "english_answers": {
            key: _distribution(values)
            for key, values in sorted(english_answer_lengths.items())
        },
        "translated_answers": {
            key: _distribution(values)
            for key, values in sorted(translated_answer_lengths.items())
        },
    }
    reused_across_queries = sum(
        len(associated_query_ids) > 1
        for associated_query_ids in passage_query_ids.values()
    )

    profiles = [
        {"settings": json.loads(serialized), "count": count}
        for serialized, count in sorted(translation_profiles.items())
    ]
    return {
        "report_version": AUDIT_REPORT_VERSION,
        "dataset": {
            "id": DATASET_ID,
            "revision": DATASET_REVISION,
            "language": language,
            "language_name": LANGUAGE_NAMES[language],
            "expected_target_lang": TARGET_LANGUAGE_TAGS[language],
            "split": split,
            "physical_path": parquet_path(language, split),
            "uri": parquet_uri(language, split),
        },
        "sampling": {
            "method": "deterministic_stream_prefix",
            "max_rows": max_rows,
            "rows_sampled": rows_sampled,
            "stream_batch_size": batch_size,
            "short_passage_threshold_characters": short_passage_chars,
            "note": "A bounded prefix is reproducible but is not a random population estimate.",
        },
        "schema": schema_contract(observed_schema),
        "answer_field_detection": {
            "live_expected_field": "Answer",
            "presence_counts": _counter_dict(answer_field_presence),
            "answers_field_present": answer_field_presence["answers"] > 0,
        },
        "query_counts": {
            "query_rows_sampled": rows_sampled,
            "rows_with_query_id": counts["rows_with_query_id"],
            "unique_query_ids": len(query_ids),
            "nonempty_english_queries": counts["nonempty_english_queries"],
            "nonempty_translated_queries": counts["nonempty_translated_queries"],
            "duplicate_query_id_rows": max(
                0, counts["rows_with_query_id"] - len(query_ids)
            ),
            "query_type_distribution": _counter_dict(query_types),
            "english_query_duplicates": _duplicate_summary(english_query_duplicates),
            "translated_query_duplicates": _duplicate_summary(
                translated_query_duplicates
            ),
            "passages_per_query": _distribution(passages_per_query),
            "selected_passages_per_query": _distribution(
                selected_passages_per_query
            ),
        },
        "passage_counts": {
            "rows_with_passages": counts["rows_with_passages"],
            "english_passage_occurrences": counts["english_passage_occurrences"],
            "translated_passage_occurrences": counts["translated_passage_occurrences"],
            "label_occurrences": counts["label_occurrences"],
            "aligned_candidate_positions": counts["aligned_candidate_positions"],
            "selected_labels": counts["selected_labels"],
            "non_selected_labels": counts["non_selected_labels"],
            "invalid_labels": counts["invalid_labels"],
            "selected_ratio": round(counts["selected_labels"] / label_denominator, 6)
            if label_denominator
            else None,
            "array_mismatch_rows": counts["array_mismatch_rows"],
            "empty_english_passages": counts["empty_english_passages"],
            "empty_translated_passages": counts["empty_translated_passages"],
            "short_english_passages": counts["short_english_passages"],
            "short_translated_passages": counts["short_translated_passages"],
        },
        "field_completeness": _field_completeness(rows_sampled, field_counters),
        "length_distributions": length_distributions,
        "duplicates": {
            "english_passages": _duplicate_summary(english_duplicates),
            "translated_passages": _duplicate_summary(translated_duplicates),
            "canonical_passages_reused_across_queries": reused_across_queries,
            "canonical_passage_reuse_rate": round(
                reused_across_queries / len(passage_query_ids), 6
            )
            if passage_query_ids
            else 0.0,
        },
        "corpus_scale_estimates": _corpus_scale_estimates(
            unique_passages=len(passage_query_ids),
            strategy_vectors=strategy_vectors,
            strategy_payload_bytes=strategy_payload_bytes,
            candidate_sizes=tuple(dict.fromkeys(candidate_corpus_sizes)),
            dense_vector_size=dense_vector_size,
            embedding_vectors_per_second=embedding_vectors_per_second,
            upsert_points_per_second=upsert_points_per_second,
        ),
        "translation_metadata": {
            "source_lang_counts": _counter_dict(source_languages),
            "target_lang_counts": _counter_dict(target_languages),
            "source_target_pair_counts": _counter_dict(language_pairs),
            "translation_model_counts": _counter_dict(translation_models),
            "parameter_profiles": profiles,
        },
        "malformed": {
            "example_limit": max_malformed_examples,
            "examples_recorded": len(malformed_examples),
            "examples": malformed_examples,
        },
    }


def combine_audit_reports(reports: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        (_json_safe(report) for report in reports),
        key=lambda report: (
            str(report["dataset"]["language"]),
            str(report["dataset"]["split"]),
        ),
    )
    return {
        "report_version": AUDIT_REPORT_VERSION,
        "dataset_id": DATASET_ID,
        "dataset_revision": DATASET_REVISION,
        "reports": ordered,
    }


def deterministic_json(report: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _markdown_distribution_table(title: str, distributions: Mapping[str, Any]) -> list[str]:
    lines = [
        f"#### {title}",
        "",
        "| Measure | Count | Min | P50 | P70 | P75 | P90 | P95 | P99 | P100 | Mean |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for measure, stats in sorted(distributions.items()):
        lines.append(
            "| {measure} | {count} | {min} | {p50} | {p70} | {p75} | {p90} | "
            "{p95} | {p99} | {p100} | {mean} |".format(
                measure=measure,
                **{
                    key: stats.get(key)
                    for key in (
                        "count",
                        "min",
                        "p50",
                        "p70",
                        "p75",
                        "p90",
                        "p95",
                        "p99",
                        "p100",
                        "mean",
                    )
                },
            )
        )
    lines.append("")
    return lines


def render_audit_markdown(report: Mapping[str, Any]) -> str:
    reports_value = report.get("reports")
    reports = list(reports_value) if isinstance(reports_value, list) else [report]
    lines = [
        "# MSMARCO-XI Dataset Audit",
        "",
        f"- Dataset: `{DATASET_ID}`",
        f"- Pinned revision: `{DATASET_REVISION}`",
        "- Sampling is a deterministic bounded stream prefix; it is not a random estimate.",
        "",
    ]
    for item in reports:
        dataset = item["dataset"]
        sampling = item["sampling"]
        schema = item["schema"]
        queries = item["query_counts"]
        passages = item["passage_counts"]
        duplicates = item["duplicates"]
        lines.extend(
            [
                f"## {dataset['language']} / {dataset['split']}",
                "",
                f"- Physical file: `{dataset['physical_path']}`",
                f"- Rows sampled: {sampling['rows_sampled']} of at most {sampling['max_rows']}",
                f"- Schema status: `{schema['status']}`",
                f"- Unique sampled query IDs: {queries['unique_query_ids']}",
                f"- Duplicate query-ID rows: {queries['duplicate_query_id_rows']}",
                "- Query types: "
                f"`{json.dumps(queries['query_type_distribution'], sort_keys=True)}`",
                f"- English passage occurrences: {passages['english_passage_occurrences']}",
                f"- Translated passage occurrences: {passages['translated_passage_occurrences']}",
                "- Selected/non-selected: "
                f"{passages['selected_labels']}/{passages['non_selected_labels']}",
                f"- Selected ratio: {passages['selected_ratio']}",
                f"- English duplicate rate: {duplicates['english_passages']['duplicate_rate']}",
                "- Translated duplicate rate: "
                f"{duplicates['translated_passages']['duplicate_rate']}",
                "- Canonical passages reused across queries: "
                f"{duplicates['canonical_passages_reused_across_queries']}",
                "",
                "### Field completeness",
                "",
                "| Field | Missing | Null | Empty | Missing/null rate |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for field, stats in sorted(item["field_completeness"].items()):
            lines.append(
                f"| `{field}` | {stats['missing_count']} | {stats['null_count']} | "
                f"{stats['empty_count']} | {stats['missing_or_null_rate']} |"
            )
        lines.extend(["", "### Passage length distributions", ""])
        lengths = item["length_distributions"]
        lines.append(f"Token method: {lengths['token_estimate_method']}")
        lines.append("")
        lines.extend(
            _markdown_distribution_table("English passages", lengths["english_passages"])
        )
        lines.extend(
            _markdown_distribution_table(
                "Translated passages", lengths["translated_passages"]
            )
        )
        lines.extend(_markdown_distribution_table("English queries", lengths["english_queries"]))
        lines.extend(
            _markdown_distribution_table("Translated queries", lengths["translated_queries"])
        )
        lines.extend(_markdown_distribution_table("English answers", lengths["english_answers"]))
        lines.extend(
            _markdown_distribution_table("Translated answers", lengths["translated_answers"])
        )
        lines.extend(
            _markdown_distribution_table(
                "Passages per query",
                {"candidate_passages": queries["passages_per_query"]},
            )
        )
        lines.extend(
            _markdown_distribution_table(
                "Selected passages per query",
                {"selected_passages": queries["selected_passages_per_query"]},
            )
        )
        lines.extend(
            [
                "### Corpus scaling estimates",
                "",
                "These are sample extrapolations with explicit heuristic assumptions, not "
                "measured Qdrant or embedding benchmarks.",
                "",
                "| Target passages | Estimated vectors | Dense bytes | Sparse bytes | "
                "Payload bytes | Qdrant bytes | Embedding seconds | Upsert seconds |",
                "|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for estimate in item["corpus_scale_estimates"]["candidate_sizes"]:
            lines.append(
                f"| {estimate['target_unique_passages']} | "
                f"{estimate['estimated_total_vectors']} | "
                f"{estimate['estimated_dense_vector_bytes']} | "
                f"{estimate['estimated_sparse_vector_bytes']} | "
                f"{estimate['estimated_payload_bytes']} | "
                f"{estimate['estimated_qdrant_bytes']} | "
                f"{estimate['estimated_embedding_seconds']} | "
                f"{estimate['estimated_upsert_seconds']} |"
            )
        lines.extend(
            [
                "",
                "Assumptions:",
                "",
                "```json",
                json.dumps(
                    item["corpus_scale_estimates"]["assumptions"],
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                "```",
                "",
            ]
        )
        lines.extend(["### Translation metadata", "", "```json"])
        lines.append(
            json.dumps(item["translation_metadata"], ensure_ascii=False, indent=2, sort_keys=True)
        )
        lines.extend(["```", "", "### Malformed or short examples", "", "```json"])
        lines.append(json.dumps(item["malformed"], ensure_ascii=False, indent=2, sort_keys=True))
        lines.extend(["```", ""])
    return "\n".join(lines).rstrip() + "\n"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def write_audit_reports(
    report: Mapping[str, Any], *, json_path: Path, markdown_path: Path
) -> tuple[Path, Path]:
    _atomic_write_text(json_path, deterministic_json(report))
    _atomic_write_text(markdown_path, render_audit_markdown(report))
    return json_path, markdown_path
