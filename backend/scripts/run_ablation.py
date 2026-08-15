from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.deadlines import Deadline  # noqa: E402
from app.domain.enums import ChunkStrategy, Language  # noqa: E402
from app.evaluation.metrics import (  # noqa: E402
    RetrievalEvaluationRecord,
    latency_metrics,
    retrieval_metrics,
)
from app.retrieval.hybrid import HybridRetriever  # noqa: E402
from app.retrieval.router import RoutePlan  # noqa: E402
from scripts._common import (  # noqa: E402
    DEFAULT_CORPUS_EVALUATION_FIXTURE,
    REPORTS_ROOT,
    EvaluationError,
    base_metadata,
    corpus_index_provenance,
    enforce_distinct,
    evaluation_qualification,
    file_sha256,
    final_threshold_provenance,
    held_out_provenance,
    initialized_services,
    load_json_object,
    load_records,
    markdown_table,
    print_artifacts,
    raw_dense_score_evidence,
    require_minimum_cases,
    require_text,
    select_query_and_field,
    write_report_bundle,
)

DEFAULT_MINIMUM_QUERIES = 500


@dataclass(frozen=True, slots=True)
class AblationConfiguration:
    name: str
    strategies: tuple[ChunkStrategy, ...] | None
    sparse: bool
    routed: bool = False
    representation_languages: tuple[Language, ...] | None = None


CONFIGURATIONS = (
    AblationConfiguration(
        "atomic_dense_english",
        (ChunkStrategy.ATOMIC,),
        False,
        representation_languages=(Language.ENGLISH,),
    ),
    AblationConfiguration(
        "atomic_dense_hindi",
        (ChunkStrategy.ATOMIC,),
        False,
        representation_languages=(Language.HINDI,),
    ),
    AblationConfiguration(
        "bilingual_paired_dense",
        (ChunkStrategy.BILINGUAL_PAIRED,),
        False,
        representation_languages=(Language.CODE_MIXED,),
    ),
    AblationConfiguration("sentence_window_dense", (ChunkStrategy.SENTENCE_WINDOW,), False),
    AblationConfiguration(
        "atomic_sentence_parent_dense",
        (
            ChunkStrategy.ATOMIC,
            ChunkStrategy.SENTENCE_WINDOW,
            ChunkStrategy.PARENT_CHILD,
        ),
        False,
    ),
    AblationConfiguration(
        "dense_sparse_fusion",
        (
            ChunkStrategy.ATOMIC,
            ChunkStrategy.SENTENCE_WINDOW,
            ChunkStrategy.PARENT_CHILD,
        ),
        True,
    ),
    AblationConfiguration("all_routed", None, True, routed=True),
)

REQUIRED_SPEC_CONFIGURATIONS = (
    "atomic_dense_english",
    "atomic_dense_hindi",
    "bilingual_paired_dense",
    "sentence_window_dense",
    "atomic_sentence_parent_dense",
    "dense_sparse_fusion",
    "all_routed",
    "quantized_vs_reference_dense_embeddings",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure required chunking/retrieval ablations on held-out queries."
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_CORPUS_EVALUATION_FIXTURE)
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        help=(
            "Source CorpusWriter manifest for --fixture; defaults to its sibling "
            "manifest. Required with a partition outside the corpus directory."
        ),
    )
    parser.add_argument(
        "--partition-manifest",
        type=Path,
        help=(
            "Manifest emitted by split_evaluation_fixture.py; defaults to a sibling "
            "partition-manifest.json when present."
        ),
    )
    parser.add_argument("--output-prefix", type=Path, default=REPORTS_ROOT / "retrieval-ablation")
    parser.add_argument(
        "--query-field",
        choices=("auto", "query", "english_query", "translated_query"),
        default="auto",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--minimum-queries", type=int, default=DEFAULT_MINIMUM_QUERIES)
    parser.add_argument("--deadline-ms", type=int, default=5_000)
    parser.add_argument("--allow-small-smoke", action="store_true")
    parser.add_argument(
        "--embedding-variant",
        choices=("auto", "reference", "quantized"),
        default="auto",
        help="Claimed active variant; it is checked against service/manifest evidence.",
    )
    parser.add_argument(
        "--paired-variant-report",
        type=Path,
        help="Measured JSON summary from the opposite embedding variant.",
    )
    parser.add_argument(
        "--configuration-build-artifact",
        action="append",
        default=[],
        metavar="CONFIG=PATH",
        help=(
            "Repeat once per configuration with a separately built Qdrant measurement "
            "artifact containing actual qdrant_index_bytes and build_time_seconds."
        ),
    )
    parser.add_argument(
        "--require-embedding-comparison",
        action="store_true",
        help="Fail unless a compatible measured opposite-variant report is supplied.",
    )
    parser.add_argument(
        "--cache-policy",
        choices=("cold", "warm", "mixed", "uncontrolled"),
        default="warm",
    )
    return parser


def _string_list(value: Any, *, row: int) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise EvaluationError(f"Row {row} relevant_canonical_ids must be an array of strings")
    values = list(dict.fromkeys(item.strip() for item in value if item.strip()))
    if not values:
        raise EvaluationError(f"Row {row} has no relevance labels")
    return values


def _prepare(
    records: list[dict[str, Any]], *, query_field: str, limit: int | None
) -> list[dict[str, Any]]:
    if limit is not None and limit < 1:
        raise EvaluationError("--limit must be positive")
    selected = records if limit is None else records[:limit]
    prepared: list[dict[str, Any]] = []
    for row_number, record in enumerate(selected, start=1):
        query, query_source_field = select_query_and_field(
            record, preferred=query_field, row=row_number
        )
        prepared.append(
            {
                **record,
                "query_id": require_text(record, "query_id", row=row_number),
                "_evaluation_query": query,
                "_query_source_field": query_source_field,
                "relevant_canonical_ids": _string_list(
                    record.get("relevant_canonical_ids"), row=row_number
                ),
            }
        )
    enforce_distinct(prepared, id_field="query_id", content_field="_evaluation_query")
    return prepared


def _manifest(services: Any) -> tuple[Path, dict[str, Any]]:
    path = getattr(services, "index_manifest_path", None)
    if not isinstance(path, Path) or not path.is_file():
        raise EvaluationError(
            "Ablation requires DefaultServices.index_manifest_path with measured chunk counts, "
            "artifact sizes, and build times"
        )
    manifest = load_json_object(path)
    strategies = manifest.get("strategies")
    if not isinstance(strategies, dict):
        raise EvaluationError(f"Index manifest {path} lacks per-strategy measurement metadata")
    required = {
        ChunkStrategy.ATOMIC.value,
        ChunkStrategy.BILINGUAL_PAIRED.value,
        ChunkStrategy.SENTENCE_WINDOW.value,
        ChunkStrategy.PARENT_CHILD.value,
    }
    missing = [
        name
        for name in sorted(required)
        if not isinstance(strategies.get(name), dict) or int(strategies[name].get("count", 0)) < 1
    ]
    if missing:
        raise EvaluationError(
            f"Index manifest has no measured chunks for required strategies: {missing}"
        )
    for field in ("point_count",):
        if field not in manifest:
            raise EvaluationError(f"Index manifest lacks required measured field {field!r}")
    return path, manifest


def _variant_evidence(manifest: dict[str, Any], services: Any) -> str:
    candidates = [
        manifest.get("embedding_variant"),
        manifest.get("dense_embedding_variant"),
        (
            manifest.get("vectors", {}).get("dense", {}).get("quantization")
            if isinstance(manifest.get("vectors"), dict)
            and isinstance(manifest.get("vectors", {}).get("dense"), dict)
            else None
        ),
    ]
    checks = getattr(services, "_checks", {})
    if isinstance(checks, dict) and isinstance(checks.get("model"), dict):
        candidates.append(checks["model"].get("backend"))
    rendered = " ".join(str(item).casefold() for item in candidates if item is not None)
    if any(token in rendered for token in ("quant", "int8")):
        return "quantized"
    if "torch" in rendered:
        return "reference"
    return "unreported"


def _resolve_variant(requested: str, manifest: dict[str, Any], services: Any) -> str:
    observed = _variant_evidence(manifest, services)
    if requested == "auto":
        if observed == "unreported":
            raise EvaluationError(
                "Embedding variant is not documented by the service/index manifest; pass a "
                "variant only after adding measured build metadata"
            )
        return observed
    if observed != requested:
        raise EvaluationError(
            f"--embedding-variant={requested} conflicts with service/index evidence "
            f"({observed}); refusing to mislabel results"
        )
    return requested


def _plan(configuration: AblationConfiguration, routed: RoutePlan) -> RoutePlan:
    if configuration.routed:
        return routed
    assert configuration.strategies is not None
    return RoutePlan(
        language=routed.language,
        category=configuration.name,
        strategies=configuration.strategies,
        dense_weight=0.65 if configuration.sparse else 1.0,
        sparse_weight=0.35 if configuration.sparse else 0.0,
        dense_limit=routed.dense_limit,
        sparse_limit=routed.sparse_limit,
        low_stt_confidence=False,
        representation_languages=(
            configuration.representation_languages
            if configuration.representation_languages is not None
            else routed.representation_languages
        ),
    )


def _configuration_contract() -> list[dict[str, Any]]:
    return [
        {
            "name": configuration.name,
            "strategies": (
                [strategy.value for strategy in configuration.strategies]
                if configuration.strategies is not None
                else None
            ),
            "sparse": configuration.sparse,
            "routed": configuration.routed,
            "representation_languages": (
                [language.value for language in configuration.representation_languages]
                if configuration.representation_languages is not None
                else "query_routed"
            ),
        }
        for configuration in CONFIGURATIONS
    ]


def _contract_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _chunk_footprints(
    manifest_path: Path, manifest: Mapping[str, Any]
) -> dict[tuple[str, str], dict[str, int]]:
    artifacts = manifest.get("artifacts")
    chunks = artifacts.get("chunks") if isinstance(artifacts, Mapping) else None
    if not isinstance(chunks, Mapping):
        raise EvaluationError("Index manifest has no artifacts.chunks measurement")
    filename = chunks.get("filename")
    expected_hash = chunks.get("sha256")
    if not isinstance(filename, str) or not filename.strip():
        raise EvaluationError("Index manifest artifacts.chunks.filename is invalid")
    chunks_path = manifest_path.parent / filename
    if not chunks_path.is_file():
        raise EvaluationError(f"Measured chunk artifact does not exist: {chunks_path}")
    if expected_hash != file_sha256(chunks_path):
        raise EvaluationError("Chunk artifact checksum differs from index manifest")

    footprints: dict[tuple[str, str], dict[str, int]] = {}
    total = 0
    try:
        with chunks_path.open("rb") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.strip():
                    continue
                value = json.loads(raw)
                if not isinstance(value, Mapping):
                    raise EvaluationError(
                        f"Chunk artifact row {line_number} must be a JSON object"
                    )
                strategy = value.get("strategy")
                language = value.get("language")
                if not isinstance(strategy, str) or not isinstance(language, str):
                    raise EvaluationError(
                        f"Chunk artifact row {line_number} lacks strategy/language"
                    )
                measurement = footprints.setdefault(
                    (strategy, language), {"count": 0, "jsonl_bytes": 0}
                )
                measurement["count"] += 1
                measurement["jsonl_bytes"] += len(raw)
                total += 1
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"Could not measure chunk artifact {chunks_path}: {exc}") from exc
    if total != manifest.get("point_count"):
        raise EvaluationError(
            "Chunk artifact record count differs from index manifest point_count"
        )
    return footprints


def _configuration_build_specs(values: Sequence[str]) -> dict[str, Path]:
    known = {configuration.name for configuration in CONFIGURATIONS}
    parsed: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        name = name.strip()
        if not separator or not name or not raw_path.strip():
            raise EvaluationError(
                "--configuration-build-artifact must use CONFIG=PATH"
            )
        if name not in known:
            raise EvaluationError(
                f"Unknown configuration build artifact {name!r}; expected {sorted(known)}"
            )
        if name in parsed:
            raise EvaluationError(f"Duplicate build artifact for configuration {name!r}")
        parsed[name] = Path(raw_path.strip())
    return parsed


def _load_configuration_build_artifacts(
    values: Sequence[str],
    *,
    shared_manifest: Mapping[str, Any],
    footprints: Mapping[tuple[str, str], Mapping[str, int]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    specs = _configuration_build_specs(values)
    loaded: dict[str, dict[str, Any]] = {}
    collections: set[str] = set()
    for configuration in CONFIGURATIONS:
        path = specs.get(configuration.name)
        if path is None:
            continue
        artifact = load_json_object(path)
        if artifact.get("configuration") != configuration.name:
            raise EvaluationError(
                f"Separate build artifact for {configuration.name} must declare its "
                "configuration"
            )
        if artifact.get("measurement_scope") != "separate_qdrant_collection_build":
            raise EvaluationError(
                f"Separate build artifact for {configuration.name} must declare "
                "measurement_scope='separate_qdrant_collection_build'"
            )
        expected_strategies = sorted(
            strategy.value
            for strategy in (
                configuration.strategies
                or tuple(
                    ChunkStrategy(name)
                    for name, details in shared_manifest["strategies"].items()
                    if details.get("enabled")
                )
            )
        )
        observed_strategies = artifact.get("strategies")
        if not isinstance(observed_strategies, list) or sorted(
            observed_strategies
        ) != expected_strategies:
            raise EvaluationError(
                f"Separate build artifact for {configuration.name} has incompatible strategies"
            )
        expected_languages = (
            sorted(language.value for language in configuration.representation_languages)
            if configuration.representation_languages is not None
            else sorted(
                {
                    language
                    for strategy, language in footprints
                    if strategy in expected_strategies
                }
            )
        )
        observed_languages = artifact.get("representation_languages")
        if not isinstance(observed_languages, list) or sorted(
            observed_languages
        ) != expected_languages:
            raise EvaluationError(
                f"Separate build artifact for {configuration.name} has incompatible languages"
            )
        if artifact.get("sparse_vectors_built") is not configuration.sparse:
            raise EvaluationError(
                f"Separate build artifact for {configuration.name} has incompatible "
                "sparse_vectors_built"
            )
        compatibility_fields = (
            "corpus_manifest_sha256",
            "dense_model",
            "model_revision",
        )
        mismatches = [
            field
            for field in compatibility_fields
            if artifact.get(field) != shared_manifest.get(field)
        ]
        if mismatches:
            raise EvaluationError(
                f"Separate build artifact for {configuration.name} is incompatible: "
                + ", ".join(mismatches)
            )
        collection = artifact.get("collection")
        qdrant_bytes = artifact.get("qdrant_index_bytes")
        build_seconds = artifact.get("build_time_seconds")
        point_count = artifact.get("point_count")
        if not isinstance(collection, str) or not collection.strip():
            raise EvaluationError(
                f"Separate build artifact for {configuration.name} lacks collection"
            )
        if collection in collections or collection == shared_manifest.get("collection"):
            raise EvaluationError(
                "Configuration build artifacts must use distinct, separate collections"
            )
        collections.add(collection)
        if (
            isinstance(qdrant_bytes, bool)
            or not isinstance(qdrant_bytes, int)
            or qdrant_bytes <= 0
        ):
            raise EvaluationError(
                f"Separate build artifact for {configuration.name} requires positive "
                "qdrant_index_bytes"
            )
        if (
            isinstance(build_seconds, bool)
            or not isinstance(build_seconds, int | float)
            or build_seconds <= 0
        ):
            raise EvaluationError(
                f"Separate build artifact for {configuration.name} requires positive "
                "build_time_seconds"
            )
        if isinstance(point_count, bool) or not isinstance(point_count, int) or point_count <= 0:
            raise EvaluationError(
                f"Separate build artifact for {configuration.name} requires point_count"
            )
        loaded[configuration.name] = {
            "status": "measured_separate_qdrant_build",
            "artifact_path": str(path.resolve()),
            "artifact_sha256": file_sha256(path),
            "collection": collection,
            "point_count": point_count,
            "qdrant_index_bytes": qdrant_bytes,
            "build_time_seconds": float(build_seconds),
        }
    missing = [
        configuration.name
        for configuration in CONFIGURATIONS
        if configuration.name not in loaded
    ]
    return loaded, {
        "qualifying": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing_configurations": missing,
    }


def _configuration_artifacts(
    configuration: AblationConfiguration,
    manifest: Mapping[str, Any],
    footprints: Mapping[tuple[str, str], Mapping[str, int]],
    separate_build: Mapping[str, Any] | None,
) -> dict[str, Any]:
    strategy_metadata = manifest["strategies"]
    if configuration.routed:
        names = [name for name, values in strategy_metadata.items() if values.get("enabled")]
    else:
        assert configuration.strategies is not None
        names = [strategy.value for strategy in configuration.strategies]
    fixed_languages = (
        {language.value for language in configuration.representation_languages}
        if configuration.representation_languages is not None
        else None
    )
    selected = [
        measurement
        for (strategy, language), measurement in footprints.items()
        if strategy in names and (fixed_languages is None or language in fixed_languages)
    ]
    artifacts = manifest.get("artifacts", {})
    sparse = artifacts.get("sparse_encoder", {}) if isinstance(artifacts, Mapping) else {}
    return {
        "evaluation_scope": "shared_index_routing_only",
        "strategies": names,
        "representation_languages": (
            sorted(fixed_languages) if fixed_languages is not None else "query_routed"
        ),
        "selected_chunk_count": sum(item["count"] for item in selected),
        "selected_chunk_jsonl_bytes": sum(item["jsonl_bytes"] for item in selected),
        "selected_chunk_measurement": (
            "eligible rows in the shared deterministic chunk JSONL; not Qdrant storage"
        ),
        "sparse_encoder_state_bytes": (
            int(sparse.get("bytes", 0))
            if configuration.sparse and isinstance(sparse, Mapping)
            else 0
        ),
        "separate_qdrant_build": separate_build
        or {
            "status": "not_measured",
            "qdrant_index_bytes": None,
            "build_time_seconds": None,
        },
    }


def _paired_comparison(
    path: Path | None,
    *,
    current_variant: str,
    current_metadata: Mapping[str, Any],
    current_configurations: dict[str, Any],
    required: bool,
) -> dict[str, Any]:
    if path is None:
        if required:
            raise EvaluationError(
                "The required quantized-versus-reference ablation needs --paired-variant-report "
                "from a separately measured opposite embedding service/index"
            )
        return {
            "status": "not_measured",
            "reason": (
                "Current DefaultServices has no retriever factory for a second embedding "
                "variant; supply a separately measured --paired-variant-report"
            ),
        }
    paired = load_json_object(path)
    metadata = paired.get("metadata")
    configs = paired.get("configurations")
    if not isinstance(metadata, dict) or not isinstance(configs, dict):
        raise EvaluationError(f"Paired report has no metadata/configurations: {path}")
    paired_variant = metadata.get("embedding_variant")
    expected_variant = "quantized" if current_variant == "reference" else "reference"
    if paired_variant != expected_variant:
        raise EvaluationError(
            f"Paired report must be variant {expected_variant!r}, got {paired_variant!r}"
        )
    def nested(source: Mapping[str, Any], *keys: str) -> Any:
        value: Any = source
        for key in keys:
            if not isinstance(value, Mapping):
                return None
            value = value.get(key)
        return value

    compatibility_fields = {
        "fixture hash": ("fixture", "sha256"),
        "held-out corpus manifest": ("held_out_provenance", "manifest_sha256"),
        "corpus/index provenance": (
            "index_manifest",
            "corpus_manifest_sha256",
        ),
        "chunk build": ("index_manifest", "chunk_build_id"),
        "chunk artifact": ("index_manifest", "chunks_sha256"),
        "point count": ("index_manifest", "point_count"),
        "query set": ("query_set_sha256",),
        "query field": ("query_field",),
        "deadline": ("deadline_ms",),
        "cache policy": ("cache_policy",),
        "score contract": ("score_contract",),
        "configuration contract": ("configuration_contract_sha256",),
    }
    mismatches = [
        label
        for label, keys in compatibility_fields.items()
        if nested(metadata, *keys) != nested(current_metadata, *keys)
    ]
    if mismatches:
        raise EvaluationError(
            "Paired variant report is not evaluation-compatible: "
            + ", ".join(mismatches)
        )
    expected_names = {configuration.name for configuration in CONFIGURATIONS}
    if set(configs) != expected_names or set(current_configurations) != expected_names:
        raise EvaluationError(
            "Paired variant reports must contain the same complete configuration set"
        )
    if any(
        not isinstance(configs[name], Mapping)
        or not isinstance(current_configurations[name], Mapping)
        for name in expected_names
    ):
        raise EvaluationError("Paired variant configuration results must be objects")
    incomplete = [
        name
        for name in sorted(expected_names)
        if configs[name].get("retrieval_completion_coverage") != 1.0
        or configs[name].get("failure_count") != 0
        or current_configurations[name].get("retrieval_completion_coverage") != 1.0
        or current_configurations[name].get("failure_count") != 0
    ]
    if incomplete:
        raise EvaluationError(
            "Paired variant comparison contains failed/incomplete configurations: "
            + ", ".join(incomplete)
        )
    paired_all = configs.get("all_routed")
    current_all = current_configurations.get("all_routed")
    if not isinstance(paired_all, dict) or not isinstance(current_all, dict):
        raise EvaluationError("Both variant reports must contain measured all_routed results")
    return {
        "status": "measured",
        "current_variant": current_variant,
        "current": current_all,
        "paired_variant": paired_variant,
        "paired": paired_all,
        "paired_report": str(path.resolve()),
        "paired_report_sha256": file_sha256(path),
    }


async def run(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_records = load_records(args.fixture)
    provenance = held_out_provenance(
        args.fixture,
        source_records,
        corpus_manifest=getattr(args, "corpus_manifest", None),
        partition_manifest=getattr(args, "partition_manifest", None),
        query_field=args.query_field,
    )
    fixture_rows = _prepare(
        source_records, query_field=args.query_field, limit=args.limit
    )
    size_qualification = require_minimum_cases(
        len(fixture_rows),
        max(DEFAULT_MINIMUM_QUERIES, args.minimum_queries),
        suite="Retrieval ablation",
        allow_small_smoke=args.allow_small_smoke,
    )
    raw_rows: list[dict[str, Any]] = []
    records_by_config: dict[str, list[RetrievalEvaluationRecord]] = {
        configuration.name: [] for configuration in CONFIGURATIONS
    }
    durations_by_config: dict[str, list[float]] = {
        configuration.name: [] for configuration in CONFIGURATIONS
    }
    successes_by_config = {configuration.name: 0 for configuration in CONFIGURATIONS}
    request_failures_by_config = {
        configuration.name: 0 for configuration in CONFIGURATIONS
    }
    configuration_failures_by_config = {
        configuration.name: 0 for configuration in CONFIGURATIONS
    }
    query_set_sha256 = _contract_sha256(
        [
            {
                "query_id": fixture["query_id"],
                "query": fixture["_evaluation_query"],
                "query_source_field": fixture["_query_source_field"],
            }
            for fixture in fixture_rows
        ]
    )
    contract = _configuration_contract()

    async with initialized_services() as services:
        orchestrator = services.orchestrator
        assert orchestrator is not None
        manifest_path, manifest = _manifest(services)
        index_provenance = corpus_index_provenance(
            provenance,
            index_manifest_path=manifest_path,
            index_manifest=manifest,
        )
        threshold_provenance = final_threshold_provenance(
            services,
            final_fixture_sha256=provenance["fixture_sha256"],
            final_query_ids=[str(row["query_id"]) for row in fixture_rows],
            final_queries=[str(row["_evaluation_query"]) for row in fixture_rows],
            index_manifest_path=manifest_path,
            index_manifest=manifest,
        )
        variant = _resolve_variant(args.embedding_variant, manifest, services)
        footprints = _chunk_footprints(manifest_path, manifest)
        separate_builds, separate_build_status = _load_configuration_build_artifacts(
            getattr(args, "configuration_build_artifact", []),
            shared_manifest=manifest,
            footprints=footprints,
        )
        retriever = orchestrator.retriever
        if retriever.final_limit < 10:
            raise EvaluationError(
                "Retriever final_limit must be at least 10 to measure @10 quality metrics "
                "without truncation"
            )
        configuration_retrievers: dict[str, HybridRetriever] = {}
        configuration_setup_errors: dict[str, dict[str, str]] = {}
        for configuration in CONFIGURATIONS:
            try:
                if configuration.sparse and retriever.sparse_searcher is None:
                    raise EvaluationError(
                        "configuration requires an initialized sparse searcher"
                    )
                configuration_retrievers[configuration.name] = (
                    retriever
                    if configuration.routed
                    else HybridRetriever(
                        retriever.dense_searcher,
                        retriever.sparse_searcher if configuration.sparse else None,
                        rrf_k=retriever.rrf_k,
                        final_limit=retriever.final_limit,
                    )
                )
            except Exception as exc:
                configuration_setup_errors[configuration.name] = {
                    "kind": "configuration",
                    "stage": "retriever_setup",
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
        for fixture in fixture_rows:
            query_id = str(fixture["query_id"])
            query = str(fixture["_evaluation_query"])
            relevant = frozenset(str(item) for item in fixture["relevant_canonical_ids"])
            routed: RoutePlan | None = None
            routing_error: dict[str, str] | None = None
            try:
                language_hint = (
                    "en"
                    if fixture["_query_source_field"] == "english_query"
                    else fixture.get("language")
                )
                routed = orchestrator.router.route(
                    query, language_hint=language_hint
                )
            except Exception as exc:
                routing_error = {
                    "kind": "configuration",
                    "stage": "routing",
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            for configuration in CONFIGURATIONS:
                started_ns = time.perf_counter_ns()
                plan: RoutePlan | None = None
                retrieved_ids: tuple[str, ...] = ()
                agreement: float | None = None
                sparse_failed: bool | None = None
                score_evidence = raw_dense_score_evidence(())
                error = routing_error or configuration_setup_errors.get(
                    configuration.name
                )
                if error is None:
                    try:
                        assert routed is not None
                        plan = _plan(configuration, routed)
                    except Exception as exc:
                        error = {
                            "kind": "configuration",
                            "stage": "configuration_plan",
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                if error is None:
                    try:
                        assert plan is not None
                        result = await configuration_retrievers[
                            configuration.name
                        ].retrieve(
                            query,
                            plan,
                            Deadline.after_ms(
                                args.deadline_ms, max(1, args.deadline_ms - 1)
                            ),
                        )
                        retrieved_ids = tuple(
                            hit.canonical_doc_id for hit in result.fused_hits
                        )
                        agreement = result.agreement
                        sparse_failed = result.sparse_failed
                        score_evidence = raw_dense_score_evidence(result.fused_hits)
                        if sparse_failed:
                            error = {
                                "kind": "request",
                                "stage": "sparse_retrieval",
                                "type": "SparseBranchFailure",
                                "message": (
                                    "Sparse retrieval failed; dense-only fallback retained"
                                ),
                            }
                    except Exception as exc:
                        error = {
                            "kind": "request",
                            "stage": "retrieval",
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                if error is None:
                    successes_by_config[configuration.name] += 1
                elif error["kind"] == "request":
                    request_failures_by_config[configuration.name] += 1
                else:
                    configuration_failures_by_config[configuration.name] += 1
                duration_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
                durations_by_config[configuration.name].append(duration_ms)
                record = RetrievalEvaluationRecord(
                    query_id=query_id,
                    relevant_ids=relevant,
                    retrieved_ids=retrieved_ids,
                    language=(
                        "en"
                        if fixture["_query_source_field"] == "english_query"
                        else str(
                            fixture.get("language")
                            or (routed.language.value if routed is not None else "unknown")
                        )
                    ),
                    category=str(
                        fixture.get("category")
                        or (routed.category if routed is not None else "routing_failed")
                    ),
                )
                records_by_config[configuration.name].append(record)
                per_query = retrieval_metrics([record])
                raw_rows.append(
                    {
                        "query_id": query_id,
                        "query": query,
                        "query_source_field": fixture["_query_source_field"],
                        "configuration": configuration.name,
                        "embedding_variant": variant,
                        "strategies": (
                            [item.value for item in plan.strategies]
                            if plan is not None
                            else []
                        ),
                        "representation_languages": (
                            [
                                language.value
                                for language in plan.representation_languages
                            ]
                            if plan is not None
                            and plan.representation_languages is not None
                            else []
                        ),
                        "uses_sparse": configuration.sparse,
                        "relevant_ids": sorted(relevant),
                        "retrieved_ids": list(retrieved_ids),
                        "duration_ms": duration_ms,
                        "evidence_agreement": agreement,
                        "sparse_failed": sparse_failed,
                        "success": error is None,
                        "error": error,
                        **score_evidence,
                        "recall_at_1": per_query["recall_at_1"],
                        "recall_at_5": per_query["recall_at_5"],
                        "recall_at_10": per_query["recall_at_10"],
                        "mrr_at_10": per_query["mrr_at_10"],
                        "ndcg_at_10": per_query["ndcg_at_10"],
                    }
                )

        configurations: dict[str, Any] = {}
        for configuration in CONFIGURATIONS:
            configurations[configuration.name] = {
                "quality": retrieval_metrics(records_by_config[configuration.name]),
                "latency": latency_metrics(
                    durations_by_config[configuration.name],
                    total_requests=len(fixture_rows),
                    completed_answers=successes_by_config[configuration.name],
                ),
                "retrieval_completion_coverage": (
                    successes_by_config[configuration.name] / len(fixture_rows)
                ),
                "failure_count": (
                    request_failures_by_config[configuration.name]
                    + configuration_failures_by_config[configuration.name]
                ),
                "request_failure_count": request_failures_by_config[configuration.name],
                "configuration_failure_count": configuration_failures_by_config[
                    configuration.name
                ],
                "artifacts": _configuration_artifacts(
                    configuration,
                    manifest,
                    footprints,
                    separate_builds.get(configuration.name),
                ),
            }
        metadata = base_metadata(
            command="run_ablation",
            fixture=args.fixture,
            cache_policy=args.cache_policy,
            concurrency=1,
            qualification="pending_integrity_checks",
        )
        metadata.update(
            {
                "embedding_variant": variant,
                "index_manifest": {
                    "path": str(manifest_path.resolve()),
                    "sha256": file_sha256(manifest_path),
                    "corpus_manifest_sha256": manifest.get(
                        "corpus_manifest_sha256"
                    ),
                    "chunk_build_id": manifest.get("chunk_build_id"),
                    "chunks_sha256": (
                        manifest.get("checksums", {}).get("chunks")
                        if isinstance(manifest.get("checksums"), dict)
                        else None
                    ),
                    "point_count": manifest.get("point_count"),
                    "feature_flags": manifest.get("feature_flags"),
                    "enabled_dense_strategies": manifest.get("enabled_dense_strategies"),
                },
                "shared_index_routing_source": {
                    "scope": "one shared index used only for routing/query evaluation",
                    "local_chunk_and_sparse_artifact_bytes": manifest.get("disk_bytes"),
                    "active_shared_build_time_seconds": manifest.get(
                        "build_time_seconds"
                    ),
                    "qdrant_index_bytes": None,
                    "qdrant_index_bytes_status": "not measured by index manifest",
                },
                "configuration_build_artifacts": separate_build_status,
                "held_out_provenance": provenance,
                "corpus_index_provenance": index_provenance,
                "frozen_thresholds": threshold_provenance,
                "runtime_feature_flags": orchestrator.settings.retrieval_feature_flags,
                "query_field": args.query_field,
                "query_set_sha256": query_set_sha256,
                "deadline_ms": args.deadline_ms,
                "score_contract": {
                    key: raw_dense_score_evidence(())[key]
                    for key in ("score_kind", "score_contract_version")
                },
                "configuration_contract": contract,
                "configuration_contract_sha256": _contract_sha256(contract),
                "required_spec_configurations": list(REQUIRED_SPEC_CONFIGURATIONS),
            }
        )

    comparison = _paired_comparison(
        args.paired_variant_report,
        current_variant=variant,
        current_metadata=metadata,
        current_configurations=configurations,
        required=args.require_embedding_comparison,
    )
    request_failures = sum(request_failures_by_config.values())
    configuration_failures = sum(configuration_failures_by_config.values())
    successful_requests = sum(successes_by_config.values())
    expected_requests = len(fixture_rows) * len(CONFIGURATIONS)
    qualification = evaluation_qualification(
        size_qualification=size_qualification,
        provenance=provenance,
        index_provenance=index_provenance,
        thresholds=threshold_provenance,
        expected_requests=expected_requests,
        recorded_requests=len(raw_rows),
        successful_requests=successful_requests,
        request_failures=request_failures,
        configuration_failures=configuration_failures,
        additional_checks={
            "separate_configuration_build_artifacts": separate_build_status[
                "qualifying"
            ],
            # Quality/latency rows above are intentionally measured through one
            # active shared collection with representation filters. Separate
            # build artifacts establish footprint only; they do not prove the
            # query behavior of those collections. Keep this development
            # comparison non-qualifying until the runner executes every query
            # against each artifact's own collection.
            "quality_latency_measured_on_each_separate_collection": False,
            "embedding_variant_comparison_measured": comparison["status"]
            == "measured",
        },
    )
    metadata["qualification"] = qualification["status"]
    metadata["qualifying"] = qualification["qualifying"]
    metadata["qualification_checks"] = qualification
    summary = {
        "metadata": metadata,
        "configurations": configurations,
        "quantized_vs_reference_dense_embeddings": comparison,
    }
    return summary, raw_rows


def _markdown(summary: dict[str, Any]) -> str:
    rows = []
    for name, result in summary["configurations"].items():
        quality = result["quality"]
        latency = result["latency"]
        artifacts = result["artifacts"]
        rows.append(
            (
                name,
                quality["recall_at_10"],
                quality["mrr_at_10"],
                quality["ndcg_at_10"],
                latency.get("p50_ms"),
                latency.get("p70_ms"),
                latency.get("p95_ms"),
                latency.get("p100_ms"),
                result["retrieval_completion_coverage"],
                artifacts["selected_chunk_count"],
                artifacts["selected_chunk_jsonl_bytes"],
                artifacts["separate_qdrant_build"]["qdrant_index_bytes"],
                artifacts["separate_qdrant_build"]["build_time_seconds"],
            )
        )
    comparison = summary["quantized_vs_reference_dense_embeddings"]
    if comparison["status"] == "measured":
        comparison_rows = []
        for variant_key, result_key in (
            ("current_variant", "current"),
            ("paired_variant", "paired"),
        ):
            result = comparison[result_key]
            comparison_rows.append(
                (
                    comparison[variant_key],
                    result["quality"]["recall_at_10"],
                    result["quality"]["mrr_at_10"],
                    result["quality"]["ndcg_at_10"],
                    result["latency"].get("p50_ms"),
                    result["latency"].get("p70_ms"),
                    result["latency"].get("p95_ms"),
                    result["latency"].get("p100_ms"),
                )
            )
        comparison_text = markdown_table(
            (
                "Variant",
                "Recall@10",
                "MRR@10",
                "nDCG@10",
                "P50 ms",
                "P70 ms",
                "P95 ms",
                "P100 ms (max)",
            ),
            comparison_rows,
        )
    else:
        comparison_text = f"Not measured: {comparison['reason']}"
    return "\n".join(
        [
            "# Chunking and retrieval ablation",
            "",
            f"Qualification: **{summary['metadata']['qualification']}**",
            "",
            markdown_table(
                (
                    "Configuration",
                    "Recall@10",
                    "MRR@10",
                    "nDCG@10",
                    "P50 ms",
                    "P70 ms",
                    "P95 ms",
                    "P100 ms (max)",
                    "Retrieval coverage",
                    "Selected chunks",
                    "Selected chunk JSONL bytes",
                    "Separate Qdrant bytes",
                    "Separate build seconds",
                ),
                rows,
            ),
            "",
            "## Quantized versus reference dense embeddings",
            "",
            comparison_text,
            "",
            (
                "Each row is a routing evaluation against one shared index. Selected "
                "chunk JSONL bytes are not Qdrant index size. Per-configuration Qdrant "
                "bytes/build times appear only when supplied from compatible, separate "
                "build artifacts; values are never estimated. Raw request failures are "
                "preserved in JSONL and CSV."
            ),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.minimum_queries < DEFAULT_MINIMUM_QUERIES:
        parser.error(
            f"--minimum-queries cannot be below {DEFAULT_MINIMUM_QUERIES}; "
            "use --allow-small-smoke for a non-qualifying smaller run"
        )
    if args.deadline_ms < 20:
        parser.error("--deadline-ms must be at least 20")
    try:
        summary, rows = asyncio.run(run(args))
        paths = write_report_bundle(
            args.output_prefix, rows=rows, summary=summary, markdown=_markdown(summary)
        )
    except (EvaluationError, TypeError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print_artifacts(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
