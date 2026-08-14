from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from app.domain.models import CorpusDocument
from app.ingestion.dataset_audit import DATASET_ID, DATASET_REVISION
from app.ingestion.loader import (
    PROHIBITED_INDEX_KEYS,
    EvaluationFixture,
    PassageCandidate,
    assert_index_payload_is_leak_free,
    extract_passage_candidates,
    record_to_documents,
    record_to_evaluation_fixture,
)
from app.ingestion.normalize import normalize_text

CORPUS_ARTIFACT_VERSION = 1
CORPUS_FILENAME = "corpus.jsonl"
EVALUATION_FILENAME = "evaluation-fixtures.jsonl"
MANIFEST_FILENAME = "corpus-manifest.json"
CORPUS_PARTIAL_FILENAME = ".corpus.jsonl.partial"
EVALUATION_PARTIAL_FILENAME = ".evaluation-fixtures.jsonl.partial"
CHECKPOINT_FILENAME = ".corpus-build.checkpoint.json"

CORPUS_PAYLOAD_FIELDS = frozenset(
    {
        "canonical_doc_id",
        "parent_id",
        "english_text",
        "translated_text",
        "translation_language",
        "translation_model",
    }
)


@dataclass(frozen=True, slots=True)
class CorpusBuildConfig:
    output_dir: Path
    target_unique_passages: int
    language: str = "hi"
    split: str = "train"
    seed: int = 2026
    shuffle_buffer_size: int = 10_000
    checkpoint_every: int = 100
    dataset_id: str = DATASET_ID
    dataset_revision: str = DATASET_REVISION
    strict: bool = True
    resume: bool = True

    def __post_init__(self) -> None:
        if self.target_unique_passages < 1:
            raise ValueError("target_unique_passages must be positive")
        if self.shuffle_buffer_size < 1:
            raise ValueError("shuffle_buffer_size must be positive")
        if self.checkpoint_every < 1:
            raise ValueError("checkpoint_every must be positive")
        if self.split not in {"train", "validation"}:
            raise ValueError("split must be train or validation")

    @property
    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "artifact_version": CORPUS_ARTIFACT_VERSION,
            "dataset_id": self.dataset_id,
            "dataset_revision": self.dataset_revision,
            "language": self.language,
            "split": self.split,
            "target_unique_passages": self.target_unique_passages,
            "seed": self.seed,
            "shuffle_buffer_size": self.shuffle_buffer_size,
            "strict": self.strict,
        }

    @property
    def fingerprint(self) -> str:
        material = _json_bytes(self.fingerprint_payload, newline=False)
        return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class CorpusBuildResult:
    corpus_path: Path
    evaluation_path: Path
    manifest_path: Path
    manifest: dict[str, Any]
    reused_existing: bool = False


def _json_bytes(value: Mapping[str, Any], *, newline: bool = True) -> bytes:
    suffix = b"\n" if newline else b""
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        + suffix
    )


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
                + b"\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_line(handle: BinaryIO, payload: Mapping[str, Any]) -> None:
    handle.write(_json_bytes(payload))


def _normalize_references(value: Any) -> list[str]:
    if value is None:
        return []
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, Iterable) or isinstance(values, bytes | bytearray | Mapping):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        normalized = normalize_text(str(item))
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _assert_no_prohibited_keys(value: Any, *, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if key_text.casefold() in PROHIBITED_INDEX_KEYS:
                raise ValueError(f"Evaluation-only key found at {path}.{key_text}")
            _assert_no_prohibited_keys(child, path=f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_prohibited_keys(child, path=f"{path}[{index}]")


def corpus_payload(document: CorpusDocument) -> dict[str, Any]:
    """Construct an index-safe payload from a typed document, never from a source row."""

    payload: dict[str, Any] = {
        "canonical_doc_id": document.canonical_doc_id,
        "parent_id": document.parent_id,
        "english_text": document.english_text,
    }
    if document.translated_text:
        payload["translated_text"] = document.translated_text
    if document.translation_language:
        payload["translation_language"] = document.translation_language
    if document.translation_model:
        payload["translation_model"] = document.translation_model

    unexpected = set(payload) - CORPUS_PAYLOAD_FIELDS
    if unexpected:
        raise ValueError(f"Unexpected corpus payload fields: {sorted(unexpected)}")
    assert_index_payload_is_leak_free(payload)
    _assert_no_prohibited_keys(payload)
    return payload


def _evaluation_payload(
    fixture: EvaluationFixture,
    record: Mapping[str, Any],
    *,
    language: str,
    split: str,
) -> dict[str, Any]:
    return {
        "query_id": fixture.query_id,
        "english_query": fixture.query,
        "translated_query": fixture.translated_query,
        "answer_references": list(dict.fromkeys(fixture.answer_references)),
        "english_answer_references": _normalize_references(record.get("Eng_Answer")),
        "relevant_canonical_ids": list(dict.fromkeys(fixture.relevant_canonical_ids)),
        "language": language,
        "split": split,
    }


def deterministic_shuffle_buffer(
    records: Iterable[Mapping[str, Any]], *, seed: int, buffer_size: int
) -> Iterator[Mapping[str, Any]]:
    """Bounded-memory, replayable shuffle; output is stable for stable input order."""

    if buffer_size < 1:
        raise ValueError("buffer_size must be positive")
    source = iter(records)
    buffer: list[Mapping[str, Any]] = []
    for _ in range(buffer_size):
        try:
            buffer.append(next(source))
        except StopIteration:
            break
    generator = random.Random(seed)
    while buffer:
        index = generator.randrange(len(buffer))
        record = buffer[index]
        yield record
        try:
            buffer[index] = next(source)
        except StopIteration:
            buffer.pop(index)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def _truncate(path: Path, offset: int) -> None:
    if offset < 0:
        raise ValueError("checkpoint offsets must not be negative")
    if not path.exists():
        raise FileNotFoundError(f"Missing resumable artifact: {path}")
    if path.stat().st_size < offset:
        raise ValueError(f"Checkpoint offset exceeds partial artifact size: {path}")
    with path.open("r+b") as handle:
        handle.truncate(offset)


def _read_identifier_set(path: Path, field: str) -> set[str]:
    result: set[str] = set()
    with path.open("rb") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
            identifier = payload.get(field)
            if not isinstance(identifier, str) or not identifier:
                raise ValueError(f"Missing {field} at {path}:{line_number}")
            result.add(identifier)
    return result


class CorpusWriter:
    """Build leak-free corpus/evaluation artifacts with resumable checkpoints."""

    def __init__(self, config: CorpusBuildConfig) -> None:
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.corpus_path = self.output_dir / CORPUS_FILENAME
        self.evaluation_path = self.output_dir / EVALUATION_FILENAME
        self.manifest_path = self.output_dir / MANIFEST_FILENAME
        self.corpus_partial_path = self.output_dir / CORPUS_PARTIAL_FILENAME
        self.evaluation_partial_path = self.output_dir / EVALUATION_PARTIAL_FILENAME
        self.checkpoint_path = self.output_dir / CHECKPOINT_FILENAME

    def _existing_result(self) -> CorpusBuildResult | None:
        if not self.config.resume or not self.manifest_path.exists():
            return None
        manifest = _read_json(self.manifest_path)
        if manifest.get("config_fingerprint") != self.config.fingerprint:
            raise ValueError(
                "Existing corpus manifest uses different build settings; "
                "pass resume=False to rebuild"
            )
        for name, path in (
            ("corpus", self.corpus_path),
            ("evaluation_fixtures", self.evaluation_path),
        ):
            if not path.exists():
                raise FileNotFoundError(f"Manifest references missing artifact: {path}")
            expected = manifest["artifacts"][name]["sha256"]
            if _sha256_file(path) != expected:
                raise ValueError(f"Artifact checksum mismatch: {path}")
        return CorpusBuildResult(
            corpus_path=self.corpus_path,
            evaluation_path=self.evaluation_path,
            manifest_path=self.manifest_path,
            manifest=manifest,
            reused_existing=True,
        )

    def _recover_finalized_partial(self, partial: Path, final: Path, offset: int) -> None:
        if partial.exists():
            return
        if final.exists() and final.stat().st_size == offset:
            os.replace(final, partial)
            return
        raise FileNotFoundError(f"Missing resumable artifact: {partial}")

    def _prepare_state(self) -> tuple[Counter[str], set[str], set[str]]:
        counters: Counter[str] = Counter()
        if not self.config.resume or not self.checkpoint_path.exists():
            self.corpus_partial_path.write_bytes(b"")
            self.evaluation_partial_path.write_bytes(b"")
            return counters, set(), set()

        checkpoint = _read_json(self.checkpoint_path)
        if checkpoint.get("config_fingerprint") != self.config.fingerprint:
            raise ValueError(
                "Checkpoint uses different build settings; pass resume=False to rebuild"
            )
        corpus_offset = int(checkpoint["corpus_offset"])
        evaluation_offset = int(checkpoint["evaluation_offset"])
        self._recover_finalized_partial(
            self.corpus_partial_path, self.corpus_path, corpus_offset
        )
        self._recover_finalized_partial(
            self.evaluation_partial_path, self.evaluation_path, evaluation_offset
        )
        _truncate(self.corpus_partial_path, corpus_offset)
        _truncate(self.evaluation_partial_path, evaluation_offset)
        checkpoint_counts = checkpoint.get("counts", {})
        if not isinstance(checkpoint_counts, Mapping):
            raise ValueError("Checkpoint counts must be an object")
        counters.update({str(key): int(value) for key, value in checkpoint_counts.items()})
        document_ids = _read_identifier_set(self.corpus_partial_path, "canonical_doc_id")
        query_ids = _read_identifier_set(self.evaluation_partial_path, "query_id")
        counters["unique_documents_written"] = len(document_ids)
        counters["evaluation_fixtures_written"] = len(query_ids)
        return counters, document_ids, query_ids

    def _persist_checkpoint(
        self,
        corpus_handle: BinaryIO,
        evaluation_handle: BinaryIO,
        counters: Counter[str],
    ) -> None:
        corpus_handle.flush()
        evaluation_handle.flush()
        os.fsync(corpus_handle.fileno())
        os.fsync(evaluation_handle.fileno())
        checkpoint = {
            "checkpoint_version": 1,
            "config_fingerprint": self.config.fingerprint,
            "corpus_offset": corpus_handle.tell(),
            "evaluation_offset": evaluation_handle.tell(),
            "counts": {key: counters[key] for key in sorted(counters)},
        }
        _atomic_write_json(self.checkpoint_path, checkpoint)

    @staticmethod
    def _count_labels(candidates: Iterable[PassageCandidate], counters: Counter[str]) -> None:
        for candidate in candidates:
            if candidate.is_selected is True:
                counters["selected_candidate_labels"] += 1
            elif candidate.is_selected is False:
                counters["non_selected_candidate_labels"] += 1
            else:
                counters["unknown_candidate_labels"] += 1

    def _process_record(
        self,
        record: Mapping[str, Any],
        *,
        corpus_handle: BinaryIO,
        evaluation_handle: BinaryIO,
        counters: Counter[str],
        document_ids: set[str],
        query_ids: set[str],
    ) -> None:
        candidates = extract_passage_candidates(record)
        documents = record_to_documents(record)
        if len(candidates) != len(documents):
            raise ValueError("Candidate/document conversion changed candidate cardinality")

        counters["candidate_occurrences_considered"] += len(candidates)
        self._count_labels(candidates, counters)
        for document in documents:
            if document.canonical_doc_id in document_ids:
                counters["duplicate_candidate_occurrences"] += 1
                continue
            payload = corpus_payload(document)
            _write_json_line(corpus_handle, payload)
            document_ids.add(document.canonical_doc_id)
            counters["unique_documents_written"] += 1

        fixture = record_to_evaluation_fixture(record)
        if fixture.query_id and fixture.query_id not in query_ids:
            _write_json_line(
                evaluation_handle,
                _evaluation_payload(
                    fixture,
                    record,
                    language=self.config.language,
                    split=self.config.split,
                ),
            )
            query_ids.add(fixture.query_id)
            counters["evaluation_fixtures_written"] += 1
        elif fixture.query_id:
            counters["duplicate_evaluation_query_ids"] += 1
        else:
            counters["records_without_query_id"] += 1

    def _manifest(self, counters: Counter[str]) -> dict[str, Any]:
        target_reached = counters["unique_documents_written"] >= self.config.target_unique_passages
        return {
            "artifact_version": CORPUS_ARTIFACT_VERSION,
            "config_fingerprint": self.config.fingerprint,
            "dataset": {
                "id": self.config.dataset_id,
                "revision": self.config.dataset_revision,
                "language": self.config.language,
                "split": self.config.split,
            },
            "sampling": {
                "method": "deterministic_bounded_shuffle_buffer_v1",
                "seed": self.config.seed,
                "shuffle_buffer_size": self.config.shuffle_buffer_size,
                "target_unique_passages": self.config.target_unique_passages,
                "target_reached": target_reached,
                "target_overshoot": max(
                    0,
                    counters["unique_documents_written"]
                    - self.config.target_unique_passages,
                ),
                "whole_query_rows_preserved": True,
            },
            "counts": {key: counters[key] for key in sorted(counters)},
            "artifacts": {
                "corpus": {
                    "filename": CORPUS_FILENAME,
                    "sha256": _sha256_file(self.corpus_path),
                    "bytes": self.corpus_path.stat().st_size,
                    "records": counters["unique_documents_written"],
                },
                "evaluation_fixtures": {
                    "filename": EVALUATION_FILENAME,
                    "sha256": _sha256_file(self.evaluation_path),
                    "bytes": self.evaluation_path.stat().st_size,
                    "records": counters["evaluation_fixtures_written"],
                },
            },
            "leak_prevention": {
                "corpus_payload_fields": sorted(CORPUS_PAYLOAD_FIELDS),
                "evaluation_only_fields_excluded": sorted(PROHIBITED_INDEX_KEYS),
                "evaluation_fixtures_separate": True,
                "relevance_labels_in_corpus": False,
            },
        }

    def build(self, records: Iterable[Mapping[str, Any]]) -> CorpusBuildResult:
        existing = self._existing_result()
        if existing is not None:
            return existing

        self.output_dir.mkdir(parents=True, exist_ok=True)
        counters, document_ids, query_ids = self._prepare_state()
        processed_before_resume = counters["records_processed"]

        corpus_partial = self.corpus_partial_path
        evaluation_partial = self.evaluation_partial_path
        with corpus_partial.open("ab") as corpus_handle, evaluation_partial.open(
            "ab"
        ) as evaluation_handle:
            if not self.checkpoint_path.exists() or not self.config.resume:
                self._persist_checkpoint(corpus_handle, evaluation_handle, counters)

            if counters["unique_documents_written"] < self.config.target_unique_passages:
                shuffled = deterministic_shuffle_buffer(
                    records,
                    seed=self.config.seed,
                    buffer_size=self.config.shuffle_buffer_size,
                )
                for sequence_index, record in enumerate(shuffled):
                    if sequence_index < processed_before_resume:
                        continue
                    try:
                        if not isinstance(record, Mapping):
                            raise ValueError("Source record is not a mapping")
                        self._process_record(
                            record,
                            corpus_handle=corpus_handle,
                            evaluation_handle=evaluation_handle,
                            counters=counters,
                            document_ids=document_ids,
                            query_ids=query_ids,
                        )
                    except (TypeError, ValueError):
                        if self.config.strict:
                            raise
                        counters["malformed_records_skipped"] += 1

                    counters["records_processed"] += 1
                    if counters["records_processed"] % self.config.checkpoint_every == 0:
                        self._persist_checkpoint(corpus_handle, evaluation_handle, counters)

                    # Stop only after the complete query row, so selected and distractor
                    # candidates from that row cannot be split by the target boundary.
                    if len(document_ids) >= self.config.target_unique_passages:
                        break

            self._persist_checkpoint(corpus_handle, evaluation_handle, counters)

        os.replace(self.corpus_partial_path, self.corpus_path)
        os.replace(self.evaluation_partial_path, self.evaluation_path)
        manifest = self._manifest(counters)
        _atomic_write_json(self.manifest_path, manifest)
        self.checkpoint_path.unlink(missing_ok=True)
        return CorpusBuildResult(
            corpus_path=self.corpus_path,
            evaluation_path=self.evaluation_path,
            manifest_path=self.manifest_path,
            manifest=manifest,
        )


def build_corpus_artifacts(
    records: Iterable[Mapping[str, Any]], config: CorpusBuildConfig
) -> CorpusBuildResult:
    return CorpusWriter(config).build(records)
