from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.ingestion.normalize import normalize_for_matching
from app.retrieval.router import TIDE_ROUTER_CONTRACT_VERSION

RAW_DENSE_SCORE_KIND: Literal["raw_dense_similarity"] = "raw_dense_similarity"
RAW_DENSE_SCORE_CONTRACT_VERSION: Literal["raw-dense-similarity-v1"] = (
    "raw-dense-similarity-v1"
)


class RetrievalArtifactBinding(BaseModel):
    """Immutable identity of the retrieval artifacts used for calibration."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    index_manifest_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    corpus_manifest_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    corpus_artifact_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    chunk_build_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    collection: str | None = None
    dense_model: str | None = None
    model_revision: str | None = None
    retrieval_contract_version: str | None = None
    retrieval_contract_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def validate_retrieval_contract_pair(self) -> RetrievalArtifactBinding:
        if (self.retrieval_contract_version is None) != (
            self.retrieval_contract_sha256 is None
        ):
            raise ValueError(
                "retrieval_contract_version and retrieval_contract_sha256 must be "
                "declared together"
            )
        return self


class FrozenThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    schema_version: Literal[1, 2, 3] = 3
    status: Literal["frozen"] = "frozen"
    source_split: Literal["development"] = "development"
    score_kind: Literal["raw_dense_similarity"] = RAW_DENSE_SCORE_KIND
    score_contract_version: Literal["raw-dense-similarity-v1"] = (
        RAW_DENSE_SCORE_CONTRACT_VERSION
    )
    development_fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_query_ids: tuple[str, ...] = Field(min_length=1)
    development_query_count: int = Field(ge=1)
    development_query_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_query_content_hashes: tuple[str, ...] = Field(min_length=1)
    development_query_content_count: int = Field(ge=1)
    development_query_content_hashes_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    frozen_at: AwareDatetime
    minimum_answer_score: float = Field(ge=-1.0, le=1.0)
    minimum_score_margin: float = Field(ge=0.0)
    minimum_evidence_agreement: float = Field(ge=0.0, le=1.0)
    retrieval_artifacts: RetrievalArtifactBinding | None = None

    @field_validator("frozen_at")
    @classmethod
    def frozen_at_must_be_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("frozen_at must be UTC-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_development_query_ids(self) -> FrozenThresholds:
        if any(not item or item != item.strip() for item in self.development_query_ids):
            raise ValueError("development_query_ids must contain non-empty trimmed strings")
        if tuple(sorted(set(self.development_query_ids))) != self.development_query_ids:
            raise ValueError("development_query_ids must be sorted and unique")
        if len(self.development_query_ids) != self.development_query_count:
            raise ValueError(
                "development_query_count does not match development_query_ids"
            )
        if query_ids_sha256(self.development_query_ids) != self.development_query_ids_sha256:
            raise ValueError("development_query_ids_sha256 does not match the stored IDs")
        if (
            tuple(sorted(set(self.development_query_content_hashes)))
            != self.development_query_content_hashes
            or any(
                re.fullmatch(r"[0-9a-f]{64}", item) is None
                for item in self.development_query_content_hashes
            )
        ):
            raise ValueError(
                "development_query_content_hashes must be sorted, unique SHA-256 values"
            )
        if (
            len(self.development_query_content_hashes)
            != self.development_query_content_count
        ):
            raise ValueError(
                "development_query_content_count does not match stored content hashes"
            )
        if (
            query_ids_sha256(self.development_query_content_hashes)
            != self.development_query_content_hashes_sha256
        ):
            raise ValueError(
                "development_query_content_hashes_sha256 does not match stored hashes"
            )
        return self


def fixture_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def query_ids_sha256(query_ids: Sequence[str]) -> str:
    normalized = sorted(
        dict.fromkeys(str(item).strip() for item in query_ids if str(item).strip())
    )
    material = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def query_content_sha256(query: str) -> str:
    normalized = normalize_for_matching(query)
    if not normalized:
        raise ValueError("Query content must not be empty")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _fixture_values(path: Path) -> list[Mapping[str, Any]]:
    values: list[Mapping[str, Any]] = []
    if path.suffix.casefold() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            values.extend(dict(row) for row in csv.DictReader(handle))
    elif path.suffix.casefold() == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, Mapping):
                    raise ValueError(f"Development fixture row {line_number} is not an object")
                values.append(value)
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or any(not isinstance(item, Mapping) for item in raw):
            raise ValueError("Development JSON fixture must be an array of objects")
        values.extend(raw)
    return values


def _fixture_query_ids(values: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    identifiers = [str(value.get("query_id") or "").strip() for value in values]
    if not identifiers or any(not item for item in identifiers):
        raise ValueError("Every development fixture row must contain a query_id")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Development fixture query_id values must be unique")
    return tuple(sorted(identifiers))


def _fixture_query_contents(values: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    contents: list[str] = []
    for row_number, value in enumerate(values, start=1):
        language = str(value.get("language") or "").strip().casefold()
        candidates = (
            ("translated_query", "english_query", "query")
            if language in {"hi", "hindi"} or language.startswith("hi-")
            else ("english_query", "query", "translated_query")
        )
        selected = next(
            (
                str(value[field]).strip()
                for field in candidates
                if isinstance(value.get(field), str) and str(value[field]).strip()
            ),
            None,
        )
        if selected is None:
            raise ValueError(
                f"Development fixture row {row_number} has no usable query content"
            )
        contents.append(selected)
    return tuple(contents)


def retrieval_runtime_contract(settings: Any) -> dict[str, Any]:
    strategies = settings.enabled_chunk_strategies
    enable_sparse = bool(settings.rag_enable_sparse)
    return {
        "contract_version": TIDE_ROUTER_CONTRACT_VERSION,
        "enabled_dense_strategies": [str(strategy.value) for strategy in strategies],
        "enable_sparse": enable_sparse,
        "dense_candidate_limit": int(settings.dense_candidate_limit),
        "sparse_candidate_limit": (
            int(settings.sparse_candidate_limit) if enable_sparse else 0
        ),
        "rrf_k": int(settings.rrf_k),
        "hybrid_final_limit": max(10, int(settings.final_evidence_limit)),
    }


def retrieval_runtime_contract_sha256(settings: Any) -> str:
    material = json.dumps(
        retrieval_runtime_contract(settings),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def freeze_development_thresholds(
    output_path: Path,
    development_fixture: Path,
    *,
    minimum_answer_score: float,
    minimum_score_margin: float,
    minimum_evidence_agreement: float,
    source_split: str = "development",
    retrieval_artifacts: RetrievalArtifactBinding | Mapping[str, Any] | None = None,
    development_query_contents: Sequence[str] | None = None,
) -> FrozenThresholds:
    if source_split != "development":
        raise ValueError("Thresholds may be frozen only from the development split")
    fixture_values = _fixture_values(development_fixture)
    development_query_ids = _fixture_query_ids(fixture_values)
    query_contents = (
        tuple(development_query_contents)
        if development_query_contents is not None
        else _fixture_query_contents(fixture_values)
    )
    if len(query_contents) != len(development_query_ids):
        raise ValueError(
            "development_query_contents must contain one query for every fixture row"
        )
    content_hashes = tuple(sorted({query_content_sha256(item) for item in query_contents}))
    binding = (
        retrieval_artifacts
        if isinstance(retrieval_artifacts, RetrievalArtifactBinding)
        else RetrievalArtifactBinding.model_validate(retrieval_artifacts)
        if retrieval_artifacts is not None
        else None
    )
    frozen = FrozenThresholds(
        development_fixture_sha256=fixture_sha256(development_fixture),
        development_query_ids=development_query_ids,
        development_query_count=len(development_query_ids),
        development_query_ids_sha256=query_ids_sha256(development_query_ids),
        development_query_content_hashes=content_hashes,
        development_query_content_count=len(content_hashes),
        development_query_content_hashes_sha256=query_ids_sha256(content_hashes),
        frozen_at=datetime.now(UTC),
        minimum_answer_score=minimum_answer_score,
        minimum_score_margin=minimum_score_margin,
        minimum_evidence_agreement=minimum_evidence_agreement,
        retrieval_artifacts=binding,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(frozen.model_dump_json(indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return frozen


def load_frozen_thresholds(path: Path) -> FrozenThresholds:
    raw = json.loads(path.read_text(encoding="utf-8"))
    frozen = FrozenThresholds.model_validate(raw)
    if frozen.status != "frozen" or frozen.source_split != "development":
        raise ValueError("Final evaluation requires development-frozen thresholds")
    return frozen


def frozen_threshold_binding_errors(
    frozen: FrozenThresholds,
    *,
    index_manifest: Mapping[str, Any],
    index_manifest_sha256: str,
    runtime_settings: Any,
) -> list[str]:
    """Return missing or mismatched active-index bindings for runtime readiness."""

    if frozen.schema_version != 3:
        return ["schema_version_must_be_3"]
    if frozen.retrieval_artifacts is None:
        return ["retrieval_artifacts_unbound"]
    checksums = index_manifest.get("checksums")
    observed = {
        "index_manifest_sha256": index_manifest_sha256,
        "corpus_manifest_sha256": index_manifest.get("corpus_manifest_sha256"),
        "corpus_artifact_sha256": (
            checksums.get("corpus") if isinstance(checksums, Mapping) else None
        ),
        "chunk_build_id": index_manifest.get("chunk_build_id"),
        "collection": index_manifest.get("collection"),
        "dense_model": index_manifest.get("dense_model"),
        "model_revision": index_manifest.get("model_revision"),
        "retrieval_contract_version": TIDE_ROUTER_CONTRACT_VERSION,
        "retrieval_contract_sha256": retrieval_runtime_contract_sha256(runtime_settings),
    }
    expected = frozen.retrieval_artifacts.model_dump(mode="json")
    errors: list[str] = []
    for field, value in observed.items():
        if value is None:
            continue
        if expected.get(field) is None:
            errors.append(f"{field}_unbound")
        elif expected[field] != value:
            errors.append(f"{field}_mismatch")
    return errors
