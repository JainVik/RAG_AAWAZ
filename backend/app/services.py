from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.core.config import Settings
from app.embeddings.dense import SentenceTransformerDenseEncoder
from app.embeddings.sparse_char_ngram import SparseCharNgramEncoder
from app.evaluation.thresholds import (
    fixture_sha256,
    frozen_threshold_binding_errors,
    load_frozen_thresholds,
)
from app.generation.grounded_generator import ExtractiveGroundedGenerator
from app.harness.circuit_breaker import CircuitBreaker
from app.harness.orchestrator import PipelineOrchestrator
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.qdrant_store import QdrantStore
from app.retrieval.router import TideRouter
from app.stt.base import SpeechToTextProvider, SttProviderError
from app.stt.sarvam_realtime import (
    SARVAM_REALTIME_ENDPOINT,
    SARVAM_REALTIME_MODEL,
    SarvamLanguageCode,
    SarvamRealtimeConfig,
    SarvamRealtimeProvider,
    SarvamStreamType,
)
from app.stt.stability import normalize_transcript


class SarvamSmokeArtifact(BaseModel):
    """Validated credentialed-smoke evidence; raw audio and credentials are excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    success: Literal[True]
    endpoint: str
    model: str
    provider_request_id: str = Field(min_length=1, max_length=512)
    observed_session_begin: Literal[True]
    observed_final: Literal[True]
    observed_session_end: Literal[True]
    normalized_final_transcript: str = Field(min_length=1, max_length=20_000)
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: AwareDatetime
    adapter: Literal["SarvamRealtimeProvider"] = "SarvamRealtimeProvider"
    audio_encoding: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate_hz: Literal[16000] = 16000
    channels: Literal[1] = 1

    @field_validator("provider_request_id")
    @classmethod
    def validate_provider_request_id(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("provider_request_id must not contain surrounding whitespace")
        if not value:
            raise ValueError("provider_request_id must be nonempty")
        return value

    @field_validator("endpoint")
    @classmethod
    def validate_official_endpoint(cls, value: str) -> str:
        if value != SARVAM_REALTIME_ENDPOINT:
            raise ValueError("smoke evidence must use the official Sarvam endpoint")
        return value

    @field_validator("model")
    @classmethod
    def validate_official_model(cls, value: str) -> str:
        if value != SARVAM_REALTIME_MODEL:
            raise ValueError("smoke evidence must use the official Sarvam model")
        return value

    @field_validator("normalized_final_transcript")
    @classmethod
    def validate_normalized_transcript(cls, value: str) -> str:
        normalized = normalize_transcript(value)
        if not normalized:
            raise ValueError("final transcript must be nonempty after normalization")
        if value != normalized:
            raise ValueError("final transcript must use canonical transcript normalization")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at_utc(cls, value: AwareDatetime) -> AwareDatetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("created_at must be UTC")
        return value


def load_sarvam_smoke_artifact(path: Path) -> SarvamSmokeArtifact:
    """Parse strict readiness evidence; empty and malformed files fail validation."""

    value = json.loads(path.read_text(encoding="utf-8"))
    return SarvamSmokeArtifact.model_validate(value)


class DefaultServices:
    """Owns long-lived model/provider clients and exposes truthful readiness."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.orchestrator: PipelineOrchestrator | None = None
        self.stt_factory: Callable[[], SpeechToTextProvider] | None = None
        self.sarvam_breaker = CircuitBreaker(
            "sarvam",
            failure_threshold=3,
            recovery_timeout_s=15.0,
            should_count_failure=lambda exc: isinstance(exc, SttProviderError),
            reset_on_call_success=False,
        )
        self.qdrant_store: QdrantStore | None = None
        self._manifest: dict[str, Any] | None = None
        self._checks: dict[str, dict[str, Any]] = {}

    @property
    def index_dir(self) -> Path:
        return self.settings.rag_data_dir / "index"

    @property
    def index_manifest_path(self) -> Path:
        return self.index_dir / "index-manifest.json"

    @property
    def sparse_state_path(self) -> Path:
        return self.index_dir / "sparse-encoder.json"

    async def initialize(self) -> None:
        self._configure_sarvam()
        if not self.index_manifest_path.exists():
            self._checks["index"] = {
                "ready": False,
                "reason": "index_manifest_missing",
                "path": str(self.index_manifest_path),
            }
            self._checks["model"] = {"ready": False, "reason": "index_not_built"}
            self._checks["qdrant"] = {"ready": False, "reason": "index_not_built"}
            self._configure_thresholds(index_manifest=None)
            return
        try:
            loaded = json.loads(self.index_manifest_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("index manifest must be a JSON object")
            if loaded.get("collection") != self.settings.qdrant_collection:
                raise ValueError("index manifest collection does not match QDRANT_COLLECTION")
            if loaded.get("dense_model") != self.settings.rag_dense_model:
                raise ValueError("index manifest dense model does not match RAG_DENSE_MODEL")
            if loaded.get("model_revision") != self.settings.rag_dense_model_revision:
                raise ValueError(
                    "index manifest model revision does not match RAG_DENSE_MODEL_REVISION"
                )
            sparse_built = loaded.get("sparse_vectors_built")
            if not isinstance(sparse_built, bool):
                raise ValueError("index manifest must declare sparse_vectors_built")
            if sparse_built != self.settings.rag_enable_sparse:
                self._checks["index"] = {
                    "ready": False,
                    "reason": "sparse_mode_mismatch",
                    "manifest_sparse_vectors_built": sparse_built,
                    "configured_sparse_enabled": self.settings.rag_enable_sparse,
                }
                self._configure_thresholds(index_manifest=None)
                return
            built_strategies = loaded.get("enabled_dense_strategies")
            if not isinstance(built_strategies, list) or any(
                not isinstance(strategy, str) for strategy in built_strategies
            ):
                raise ValueError(
                    "index manifest must declare enabled_dense_strategies"
                )
            configured_strategies = {
                strategy.value for strategy in self.settings.enabled_chunk_strategies
            }
            missing_strategies = sorted(
                configured_strategies - set(built_strategies)
            )
            if missing_strategies:
                self._checks["index"] = {
                    "ready": False,
                    "reason": "dense_strategy_not_built",
                    "missing_strategies": missing_strategies,
                    "manifest_enabled_dense_strategies": sorted(
                        set(built_strategies)
                    ),
                }
                self._configure_thresholds(index_manifest=None)
                return
        except Exception as exc:
            self._checks["index"] = {
                "ready": False,
                "reason": "invalid_index_artifacts",
                "error_type": type(exc).__name__,
            }
            self._configure_thresholds(index_manifest=None)
            return

        if self.settings.rag_enable_sparse and not self.sparse_state_path.exists():
            self._checks["index"] = {
                "ready": False,
                "reason": "sparse_encoder_state_missing",
                "path": str(self.sparse_state_path),
            }
            self._configure_thresholds(index_manifest=None)
            return
        if self.settings.rag_enable_sparse:
            checksums = loaded.get("checksums")
            expected_sparse_sha256 = (
                checksums.get("sparse_encoder")
                if isinstance(checksums, dict)
                else None
            )
            if not isinstance(expected_sparse_sha256, str):
                self._checks["index"] = {
                    "ready": False,
                    "reason": "sparse_encoder_checksum_missing",
                }
                self._configure_thresholds(index_manifest=None)
                return
            observed_sparse_sha256 = fixture_sha256(self.sparse_state_path)
            if observed_sparse_sha256 != expected_sparse_sha256:
                self._checks["index"] = {
                    "ready": False,
                    "reason": "sparse_encoder_checksum_mismatch",
                    "expected_sha256": expected_sparse_sha256,
                    "observed_sha256": observed_sparse_sha256,
                }
                self._configure_thresholds(index_manifest=None)
                return
        try:
            sparse_encoder = (
                SparseCharNgramEncoder.load(self.sparse_state_path)
                if self.settings.rag_enable_sparse
                else None
            )
        except Exception as exc:
            self._checks["index"] = {
                "ready": False,
                "reason": "invalid_sparse_encoder_state",
                "error_type": type(exc).__name__,
            }
            self._configure_thresholds(index_manifest=None)
            return
        self._manifest = loaded

        if (
            not self._configure_thresholds(index_manifest=loaded)
            and self.settings.rag_require_frozen_thresholds
        ):
            return

        try:
            dense_encoder = await asyncio.to_thread(
                SentenceTransformerDenseEncoder,
                self.settings.rag_dense_model,
                revision=self.settings.rag_dense_model_revision,
                backend="torch",
                device="cpu",
            )
            if dense_encoder.dimension != self.settings.dense_vector_size:
                raise ValueError(
                    f"Loaded model dimension {dense_encoder.dimension} does not match "
                    f"RAG dense size {self.settings.dense_vector_size}"
                )
            self._checks["model"] = {
                "ready": True,
                "name": self.settings.rag_dense_model,
                "revision": self.settings.rag_dense_model_revision,
                "dimension": dense_encoder.dimension,
                "backend": "torch",
            }
        except Exception as exc:
            self._checks["model"] = {
                "ready": False,
                "reason": "dense_model_load_failed",
                "error_type": type(exc).__name__,
            }
            return

        self.qdrant_store = QdrantStore(
            self.settings,
            dense_encoder,
            sparse_encoder,
            collection_metadata={
                "corpus_manifest_sha256": self._manifest.get("corpus_manifest_sha256", ""),
                "chunk_build_id": self._manifest.get("chunk_build_id", ""),
            },
        )
        retriever = HybridRetriever(
            self.qdrant_store,
            self.qdrant_store if self.settings.rag_enable_sparse else None,
            rrf_k=self.settings.rrf_k,
            # Evaluation requires Recall@10; late evidence selection still narrows
            # this candidate pool to ``final_evidence_limit`` for generation.
            final_limit=max(10, self.settings.final_evidence_limit),
        )
        self.orchestrator = PipelineOrchestrator(
            settings=self.settings,
            retriever=retriever,
            generator=ExtractiveGroundedGenerator(),
            router=TideRouter(
                self.settings.dense_candidate_limit,
                self.settings.sparse_candidate_limit,
            ),
        )
        try:
            await self.qdrant_store.initialize()
            self._checks["qdrant"] = await self.qdrant_store.readiness_details(
                expected_points=self._expected_point_count(), require_green=False
            )
        except Exception as exc:
            self._checks["qdrant"] = {
                "ready": False,
                "reason": "qdrant_initialize_failed",
                "error_type": type(exc).__name__,
            }
        self._checks["index"] = {
            "ready": bool(self._manifest),
            "path": str(self.index_manifest_path),
            "expected_points": self._expected_point_count(),
        }

    def _configure_thresholds(self, *, index_manifest: dict[str, Any] | None) -> bool:
        path = self.settings.rag_thresholds_path
        if not path.exists():
            self._checks["thresholds"] = {
                "ready": False,
                "reason": "frozen_development_thresholds_missing",
                "path": str(path),
                "using_provisional_defaults": not self.settings.rag_require_frozen_thresholds,
            }
            return False
        binding_errors: list[str] = []
        try:
            frozen = load_frozen_thresholds(path)
            if index_manifest is None:
                raise ValueError("active index manifest is unavailable")
            binding_errors = frozen_threshold_binding_errors(
                frozen,
                index_manifest=index_manifest,
                index_manifest_sha256=fixture_sha256(self.index_manifest_path),
                runtime_settings=self.settings,
            )
            if binding_errors:
                raise ValueError(
                    "frozen threshold retrieval binding is invalid: " + ", ".join(binding_errors)
                )
            settings_data = self.settings.model_dump(mode="python")
            settings_data.update(
                {
                    "min_answer_score": frozen.minimum_answer_score,
                    "min_score_margin": frozen.minimum_score_margin,
                    "min_evidence_agreement": frozen.minimum_evidence_agreement,
                }
            )
            self.settings = Settings.model_validate(settings_data)
        except Exception as exc:
            self._checks["thresholds"] = {
                "ready": False,
                "reason": "invalid_frozen_thresholds",
                "error_type": type(exc).__name__,
                "binding_errors": binding_errors,
            }
            return False
        self._checks["thresholds"] = {
            "ready": True,
            "path": str(path),
            "source_split": frozen.source_split,
            "development_fixture_sha256": frozen.development_fixture_sha256,
            "score_kind": frozen.score_kind,
            "score_contract_version": frozen.score_contract_version,
            "retrieval_artifacts_bound": frozen.retrieval_artifacts is not None,
        }
        return True

    def _configure_sarvam(self) -> None:
        if not self.settings.sarvam_configured:
            self._checks["sarvam"] = {
                "ready": False,
                "reason": "SARVAM_API_KEY_not_configured",
                "credentialed_smoke_verified": False,
            }
            return
        try:
            api_key = self.settings.sarvam_api_key
            assert api_key is not None
            config = SarvamRealtimeConfig(
                api_key=api_key,
                endpoint=self.settings.sarvam_ws_url,
                model=self.settings.sarvam_model,
                language_code=SarvamLanguageCode(self.settings.sarvam_language_code),
                stream_type=SarvamStreamType.FAST,
            )
        except Exception as exc:
            self._checks["sarvam"] = {
                "ready": False,
                "reason": "invalid_sarvam_configuration",
                "error_type": type(exc).__name__,
            }
            return
        self.stt_factory = lambda: SarvamRealtimeProvider(config)
        smoke_path = self.settings.rag_data_dir / "sarvam-smoke.json"
        smoke_artifact: SarvamSmokeArtifact | None = None
        smoke_reason: str | None = None
        try:
            smoke_artifact = load_sarvam_smoke_artifact(smoke_path)
            if smoke_artifact.endpoint != config.endpoint:
                raise ValueError("smoke endpoint does not match configured endpoint")
            if smoke_artifact.model != config.model:
                raise ValueError("smoke model does not match configured model")
        except FileNotFoundError:
            smoke_reason = "credentialed_smoke_not_verified"
        except Exception:
            smoke_reason = "credentialed_smoke_artifact_invalid"
        smoke_verified = smoke_artifact is not None
        self._checks["sarvam"] = {
            "ready": smoke_verified,
            "configured": True,
            "endpoint": config.endpoint,
            "model": config.model,
            "credentialed_smoke_verified": smoke_verified,
            "reason": smoke_reason,
        }
        if smoke_artifact is not None:
            self._checks["sarvam"].update(
                {
                    "smoke_schema_version": smoke_artifact.schema_version,
                    "smoke_created_at": smoke_artifact.created_at.isoformat(),
                    "provider_request_id_received": bool(smoke_artifact.provider_request_id),
                    "observed_session_begin": smoke_artifact.observed_session_begin,
                    "observed_final": smoke_artifact.observed_final,
                    "observed_session_end": smoke_artifact.observed_session_end,
                }
            )

    def _expected_point_count(self) -> int | None:
        if self._manifest is None:
            return None
        value = self._manifest.get("point_count", self._manifest.get("chunk_count"))
        return int(value) if value is not None else None

    async def readiness(self) -> dict[str, Any]:
        checks = {key: dict(value) for key, value in self._checks.items()}
        if self.qdrant_store is not None:
            try:
                checks["qdrant"] = await self.qdrant_store.readiness_details(
                    expected_points=self._expected_point_count(), require_green=True
                )
            except Exception as exc:
                checks["qdrant"] = {
                    "ready": False,
                    "reason": "qdrant_readiness_failed",
                    "error_type": type(exc).__name__,
                }
        required = ("index", "model", "qdrant", "sarvam", "thresholds")
        all_ready = all(checks.get(key, {}).get("ready") is True for key in required)
        return {"status": "ready" if all_ready else "not_ready", "checks": checks}

    async def close(self) -> None:
        if self.qdrant_store is not None:
            await self.qdrant_store.close()
