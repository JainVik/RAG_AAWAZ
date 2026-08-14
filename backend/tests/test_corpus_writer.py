from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.ingestion.corpus_writer import (
    CHECKPOINT_FILENAME,
    CORPUS_PAYLOAD_FIELDS,
    CorpusBuildConfig,
    build_corpus_artifacts,
)
from app.ingestion.deduplicate import canonical_document_id
from app.ingestion.loader import PROHIBITED_INDEX_KEYS


def _record(
    query_id: int,
    english: list[str],
    translated: list[str],
    labels: list[int],
) -> dict[str, object]:
    return {
        "source_lang": "eng_Latn",
        "target_lang": "hin_Deva",
        "meta": {
            "frequency_penalty": 0,
            "max_tokens": 4096,
            "model_name": "translation-model",
            "presence_penalty": 0,
            "temperature": 0,
            "top_p": 1,
        },
        "Answer": f"अनुवादित उत्तर {query_id}",
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


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _config(output_dir: Path, *, target: int = 100, resume: bool = False) -> CorpusBuildConfig:
    return CorpusBuildConfig(
        output_dir=output_dir,
        target_unique_passages=target,
        seed=2026,
        shuffle_buffer_size=1,
        checkpoint_every=1,
        resume=resume,
    )


def test_corpus_is_leak_free_and_evaluation_fields_are_separate(tmp_path) -> None:
    alpha = "Alpha canonical passage."
    records = [
        _record(
            1,
            [alpha, "Distractor passage."],
            ["अल्फा कैनोनिकल अनुच्छेद।", "भटकाने वाला अनुच्छेद।"],
            [1, 0],
        ),
        _record(
            2,
            [alpha, "Third passage."],
            ["अल्फा कैनोनिकल अनुच्छेद।", "तीसरा अनुच्छेद।"],
            [0, 1],
        ),
    ]

    result = build_corpus_artifacts(records, _config(tmp_path))
    corpus = _read_jsonl(result.corpus_path)
    fixtures = _read_jsonl(result.evaluation_path)

    assert len(corpus) == 3
    assert len(fixtures) == 2
    assert result.manifest["counts"]["candidate_occurrences_considered"] == 4
    assert result.manifest["counts"]["duplicate_candidate_occurrences"] == 1
    assert result.manifest["counts"]["selected_candidate_labels"] == 2
    assert result.manifest["counts"]["non_selected_candidate_labels"] == 2

    for payload in corpus:
        assert set(payload) <= CORPUS_PAYLOAD_FIELDS
        assert not ({key.casefold() for key in payload} & PROHIBITED_INDEX_KEYS)
        serialized = json.dumps(payload, ensure_ascii=False).casefold()
        assert "english query" not in serialized
        assert "english answer" not in serialized
        assert "हिंदी प्रश्न" not in serialized
        assert "अनुवादित उत्तर" not in serialized
        assert "is_selected" not in serialized

    assert fixtures[0]["english_query"] == "English query 1"
    assert fixtures[0]["translated_query"] == "हिंदी प्रश्न 1"
    assert fixtures[0]["english_answer_references"] == ["English answer 1"]
    assert fixtures[0]["answer_references"] == ["अनुवादित उत्तर 1"]
    assert fixtures[0]["relevant_canonical_ids"] == [canonical_document_id(alpha)]


def test_sampling_preserves_whole_candidate_row_at_target_boundary(tmp_path) -> None:
    records = [
        _record(
            10,
            ["Passage one.", "Passage two.", "Passage three."],
            ["अनुच्छेद एक।", "अनुच्छेद दो।", "अनुच्छेद तीन।"],
            [1, 0, 0],
        ),
        _record(11, ["Passage four."], ["अनुच्छेद चार।"], [1]),
    ]
    result = build_corpus_artifacts(records, _config(tmp_path, target=2))

    assert len(_read_jsonl(result.corpus_path)) == 3
    assert result.manifest["sampling"]["target_reached"] is True
    assert result.manifest["sampling"]["target_overshoot"] == 1
    assert result.manifest["sampling"]["whole_query_rows_preserved"] is True
    assert result.manifest["counts"]["records_processed"] == 1


def test_same_seed_and_input_produce_identical_artifacts(tmp_path) -> None:
    records = [
        _record(index, [f"Passage {index}."], [f"अनुच्छेद {index}।"], [index % 2])
        for index in range(1, 8)
    ]
    first = build_corpus_artifacts(
        records,
        CorpusBuildConfig(
            output_dir=tmp_path / "first",
            target_unique_passages=100,
            seed=99,
            shuffle_buffer_size=3,
            checkpoint_every=2,
            resume=False,
        ),
    )
    second = build_corpus_artifacts(
        records,
        CorpusBuildConfig(
            output_dir=tmp_path / "second",
            target_unique_passages=100,
            seed=99,
            shuffle_buffer_size=3,
            checkpoint_every=2,
            resume=False,
        ),
    )

    assert first.corpus_path.read_bytes() == second.corpus_path.read_bytes()
    assert first.evaluation_path.read_bytes() == second.evaluation_path.read_bytes()
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()


class _FailAfterFirst:
    def __init__(self, first: dict[str, object]) -> None:
        self.first = first

    def __iter__(self) -> Iterator[dict[str, object]]:
        yield self.first
        raise RuntimeError("simulated interrupted stream")


def test_interrupted_build_resumes_from_atomic_checkpoint(tmp_path) -> None:
    records = [
        _record(1, ["First passage."], ["पहला अनुच्छेद।"], [1]),
        _record(2, ["Second passage."], ["दूसरा अनुच्छेद।"], [0]),
        _record(3, ["Third passage."], ["तीसरा अनुच्छेद।"], [1]),
    ]
    resumed_dir = tmp_path / "resumed"
    resume_config = _config(resumed_dir, resume=True)

    with pytest.raises(RuntimeError, match="simulated interrupted stream"):
        build_corpus_artifacts(_FailAfterFirst(records[0]), resume_config)
    assert (resumed_dir / CHECKPOINT_FILENAME).exists()

    resumed = build_corpus_artifacts(records, resume_config)
    clean = build_corpus_artifacts(records, _config(tmp_path / "clean", resume=False))

    assert resumed.corpus_path.read_bytes() == clean.corpus_path.read_bytes()
    assert resumed.evaluation_path.read_bytes() == clean.evaluation_path.read_bytes()
    assert resumed.manifest_path.read_bytes() == clean.manifest_path.read_bytes()
    assert not (resumed_dir / CHECKPOINT_FILENAME).exists()


def test_existing_valid_manifest_is_reused(tmp_path) -> None:
    records = [_record(1, ["A passage."], ["एक अनुच्छेद।"], [1])]
    config = _config(tmp_path, resume=True)
    first = build_corpus_artifacts(records, config)
    second = build_corpus_artifacts([], config)

    assert first.reused_existing is False
    assert second.reused_existing is True
    assert second.manifest == first.manifest


def test_mismatched_parallel_arrays_fail_in_strict_mode(tmp_path) -> None:
    malformed = _record(
        1,
        ["First passage.", "Second passage."],
        ["केवल एक अनुच्छेद।"],
        [1, 0],
    )
    with pytest.raises(ValueError, match="unequal lengths"):
        build_corpus_artifacts([malformed], _config(tmp_path))
