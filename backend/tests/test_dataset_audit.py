from __future__ import annotations

import json

import pytest

from app.ingestion.dataset_audit import (
    DATASET_REVISION,
    DatasetFileUnavailable,
    audit_records,
    combine_audit_reports,
    deterministic_json,
    parquet_uri,
    schema_contract,
    write_audit_reports,
)

LIVE_FEATURES = {
    "source_lang": {"dtype": "string", "_type": "Value"},
    "target_lang": {"dtype": "string", "_type": "Value"},
    "meta": {
        "frequency_penalty": {"dtype": "int64", "_type": "Value"},
        "max_tokens": {"dtype": "int64", "_type": "Value"},
        "model_name": {"dtype": "string", "_type": "Value"},
        "presence_penalty": {"dtype": "int64", "_type": "Value"},
        "temperature": {"dtype": "int64", "_type": "Value"},
        "top_p": {"dtype": "int64", "_type": "Value"},
    },
    "Answer": {"dtype": "string", "_type": "Value"},
    "query_id": {"dtype": "int64", "_type": "Value"},
    "query_type": {"dtype": "string", "_type": "Value"},
    "passages": {
        "English_passages": [{"dtype": "string", "_type": "Value"}],
        "Translated_passages": [{"dtype": "string", "_type": "Value"}],
        "is_selected": [{"dtype": "int64", "_type": "Value"}],
    },
    "Eng_Query": {"dtype": "string", "_type": "Value"},
    "Eng_Answer": {"dtype": "string", "_type": "Value"},
    "query": {"dtype": "string", "_type": "Value"},
}


def _record(
    query_id: int,
    english: list[str],
    translated: list[str],
    labels: list[int],
    *,
    answer: str | None = "उत्तर",
) -> dict[str, object]:
    return {
        "source_lang": "eng_Latn",
        "target_lang": "hin_Deva",
        "meta": {
            "frequency_penalty": 0,
            "max_tokens": 4096,
            "model_name": "ckpt-3epochs-sft-then-400k-kd",
            "presence_penalty": 0,
            "temperature": 0,
            "top_p": 1,
        },
        "Answer": answer,
        "query_id": query_id,
        "query_type": "DESCRIPTION",
        "passages": {
            "English_passages": english,
            "Translated_passages": translated,
            "is_selected": labels,
        },
        "Eng_Query": f"English query {query_id}",
        "Eng_Answer": f"English answer {query_id}",
        "query": f"हिंदी प्रश्न {query_id}",
    }


def test_uses_pinned_physical_parquet_paths() -> None:
    assert parquet_uri("hi", "train") == (
        "hf://datasets/ai4bharat/MSMARCO-XI@"
        f"{DATASET_REVISION}/train/hintrain.parquet"
    )
    assert parquet_uri("mr", "validation").endswith("/validation/marval.parquet")
    with pytest.raises(DatasetFileUnavailable, match="no Telugu train"):
        parquet_uri("te", "train")


def test_exact_live_schema_contract_matches() -> None:
    contract = schema_contract(LIVE_FEATURES)
    assert contract["matches"] is True
    assert contract["missing_paths"] == []
    assert contract["unexpected_paths"] == []
    assert contract["observed_leaf_types"]["Answer"] == "string"
    assert contract["observed_leaf_types"]["passages.English_passages"] == "list<string>"


def test_huggingface_features_serializer_precedes_mapping_values() -> None:
    class FeatureMapping(dict[str, object]):
        def to_dict(self) -> dict[str, object]:
            return LIVE_FEATURES

    contract = schema_contract(FeatureMapping({"Answer": object()}))
    assert contract["matches"] is True


def test_audit_reports_counts_nulls_duplicates_lengths_and_answer_case() -> None:
    alpha = "Alpha passage contains enough words for the audit."
    translated_alpha = "अल्फा अनुच्छेद में ऑडिट के लिए पर्याप्त शब्द हैं।"
    records = [
        _record(
            1,
            [alpha, "Beta distractor also contains enough words."],
            [translated_alpha, "बीटा भटकाने वाला अनुच्छेद पर्याप्त लंबा है।"],
            [1, 0],
        ),
        _record(
            2,
            [alpha, "tiny"],
            [translated_alpha, "छोटा"],
            [0, 1],
            answer=None,
        ),
    ]

    report = audit_records(
        records,
        language="hi",
        split="train",
        max_rows=10,
        observed_schema=LIVE_FEATURES,
        short_passage_chars=20,
    )

    assert report["schema"]["matches"] is True
    assert report["query_counts"]["query_rows_sampled"] == 2
    assert report["query_counts"]["unique_query_ids"] == 2
    assert report["passage_counts"]["english_passage_occurrences"] == 4
    assert report["passage_counts"]["selected_labels"] == 2
    assert report["passage_counts"]["non_selected_labels"] == 2
    assert report["passage_counts"]["selected_ratio"] == 0.5
    assert report["duplicates"]["english_passages"]["duplicate_occurrences"] == 1
    assert report["duplicates"]["english_passages"]["duplicate_rate"] == 0.25
    assert report["field_completeness"]["Answer"]["null_count"] == 1
    assert report["answer_field_detection"]["presence_counts"] == {"Answer": 2}
    assert report["answer_field_detection"]["answers_field_present"] is False
    assert report["length_distributions"]["english_passages"]["characters"]["count"] == 4
    assert "estimate, not a model tokenizer" in report["length_distributions"][
        "token_estimate_method"
    ]
    assert report["malformed"]["examples_recorded"] == 1
    assert "unexpectedly_short_passage" in report["malformed"]["examples"][0]["reasons"]


def test_audit_records_parallel_array_mismatch_without_silent_truncation() -> None:
    report = audit_records(
        [
            _record(
                3,
                ["First sufficiently long passage.", "Second sufficiently long passage."],
                ["केवल एक अनुवादित अनुच्छेद जो पर्याप्त लंबा है।"],
                [1, 0],
            )
        ],
        language="hi",
        split="validation",
        max_rows=1,
        observed_schema=LIVE_FEATURES,
    )
    assert report["passage_counts"]["array_mismatch_rows"] == 1
    assert report["passage_counts"]["english_passage_occurrences"] == 2
    assert report["passage_counts"]["translated_passage_occurrences"] == 1
    assert "parallel_passage_array_length_mismatch" in report["malformed"]["examples"][0][
        "reasons"
    ]


def test_json_and_markdown_outputs_are_deterministic(tmp_path) -> None:
    item = audit_records(
        [
            _record(
                4,
                ["A deterministic passage with several words."],
                ["कई शब्दों वाला एक नियतात्मक अनुच्छेद।"],
                [1],
            )
        ],
        language="hi",
        split="train",
        max_rows=1,
        observed_schema=LIVE_FEATURES,
    )
    combined = combine_audit_reports([item])
    json_path = tmp_path / "audit.json"
    markdown_path = tmp_path / "audit.md"

    write_audit_reports(combined, json_path=json_path, markdown_path=markdown_path)
    first_json = json_path.read_bytes()
    first_markdown = markdown_path.read_bytes()
    write_audit_reports(combined, json_path=json_path, markdown_path=markdown_path)

    assert json_path.read_bytes() == first_json
    assert markdown_path.read_bytes() == first_markdown
    assert json.loads(first_json)["dataset_revision"] == DATASET_REVISION
    assert deterministic_json(combined).encode("utf-8") == first_json
