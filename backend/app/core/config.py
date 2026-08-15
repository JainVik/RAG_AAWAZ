from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.enums import ChunkStrategy


class Settings(BaseSettings):
    """Environment-backed settings with safe, validated defaults."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Awaaz TideRAG"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = Field(default="INFO", validation_alias="RAG_LOG_LEVEL")

    sarvam_api_key: SecretStr | None = None
    sarvam_ws_url: str = "wss://api.sarvam.ai/speech-to-text-realtime/ws"
    sarvam_model: Literal["saaras:v3-realtime"] = "saaras:v3-realtime"
    sarvam_language_code: str = "auto"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "awaaz_tiderag_v1"

    rag_language: Literal[
        "as", "bn", "gu", "hi", "kn", "ml", "mr", "ne", "or", "pa", "sa", "ta", "te", "ur"
    ] = "hi"
    rag_target_unique_passages: int = Field(default=50_000, ge=1)
    rag_development_passages: int = Field(default=10_000, ge=1)
    rag_deadline_ms: int = Field(default=200, ge=20, le=30_000)
    rag_fallback_at_ms: int = Field(default=170, ge=1)
    rag_dense_model: str = "intfloat/multilingual-e5-small"
    rag_dense_model_revision: str = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    rag_generation_mode: Literal["extractive", "llama"] = "extractive"
    rag_enable_atomic_chunks: bool = True
    rag_enable_sentence_window_chunks: bool = True
    rag_enable_semantic_chunks: bool = True
    rag_enable_parent_child_chunks: bool = True
    rag_enable_bilingual_paired_chunks: bool = True
    rag_enable_sparse: bool = True
    rag_enable_late_chunking: bool = True
    rag_enable_speculative_retrieval: bool = True
    rag_store_raw_audio: bool = False
    rag_voice_idle_timeout_s: float = Field(default=30.0, ge=1.0, le=300.0)
    rag_voice_max_session_s: float = Field(default=90.0, ge=1.0, le=600.0)
    rag_api_token: SecretStr | None = None
    rag_voice_api_token: SecretStr | None = None
    rag_voice_allowed_origins: str = ""
    rag_random_seed: int = 2026
    rag_data_dir: Path = Path("data")
    rag_thresholds_path: Path = Path("data/calibration/frozen-thresholds.json")
    rag_require_frozen_thresholds: bool = False

    dense_vector_name: str = "dense"
    sparse_vector_name: str = "char_ngrams"
    dense_vector_size: int = Field(default=384, ge=1)
    dense_candidate_limit: int = Field(default=24, ge=1, le=500)
    sparse_candidate_limit: int = Field(default=24, ge=1, le=500)
    final_evidence_limit: int = Field(default=3, ge=1, le=20)
    rrf_k: int = Field(default=60, ge=1)

    min_stt_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    min_answer_score: float = Field(default=0.24, ge=-1.0)
    min_score_margin: float = Field(default=0.015, ge=0.0)
    min_evidence_agreement: float = Field(default=0.05, ge=0.0, le=1.0)
    speculative_stability_ms: int = Field(default=120, ge=0, le=5_000)
    speculative_similarity_threshold: float = Field(default=0.82, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_deadlines_and_sizes(self) -> Settings:
        if self.rag_fallback_at_ms >= self.rag_deadline_ms:
            raise ValueError("RAG_FALLBACK_AT_MS must be below RAG_DEADLINE_MS")
        if self.rag_development_passages > self.rag_target_unique_passages:
            raise ValueError("RAG_DEVELOPMENT_PASSAGES cannot exceed RAG_TARGET_UNIQUE_PASSAGES")
        if not self.enabled_chunk_strategies:
            raise ValueError(
                "At least one dense chunk representation must be enabled: atomic, "
                "sentence-window, semantic-section, parent-child, or bilingual-paired"
            )
        if self.environment == "production" and (
            self.api_token_value is None
        ):
            raise ValueError("RAG_API_TOKEN is required in production")
        return self

    @property
    def enabled_chunk_strategies(self) -> tuple[ChunkStrategy, ...]:
        flags = (
            (ChunkStrategy.ATOMIC, self.rag_enable_atomic_chunks),
            (ChunkStrategy.SENTENCE_WINDOW, self.rag_enable_sentence_window_chunks),
            (ChunkStrategy.SEMANTIC_SECTION, self.rag_enable_semantic_chunks),
            (ChunkStrategy.PARENT_CHILD, self.rag_enable_parent_child_chunks),
            (ChunkStrategy.BILINGUAL_PAIRED, self.rag_enable_bilingual_paired_chunks),
        )
        return tuple(strategy for strategy, enabled in flags if enabled)

    @property
    def retrieval_feature_flags(self) -> dict[str, bool]:
        enabled = set(self.enabled_chunk_strategies)
        return {
            ChunkStrategy.ATOMIC.value: ChunkStrategy.ATOMIC in enabled,
            ChunkStrategy.SENTENCE_WINDOW.value: ChunkStrategy.SENTENCE_WINDOW in enabled,
            ChunkStrategy.SEMANTIC_SECTION.value: ChunkStrategy.SEMANTIC_SECTION in enabled,
            ChunkStrategy.PARENT_CHILD.value: ChunkStrategy.PARENT_CHILD in enabled,
            ChunkStrategy.BILINGUAL_PAIRED.value: ChunkStrategy.BILINGUAL_PAIRED in enabled,
            "sparse": self.rag_enable_sparse,
            "late_chunking": self.rag_enable_late_chunking,
        }

    @property
    def sarvam_configured(self) -> bool:
        return self.sarvam_api_key is not None and bool(self.sarvam_api_key.get_secret_value())

    @property
    def qdrant_api_key_value(self) -> str | None:
        return self.qdrant_api_key.get_secret_value() if self.qdrant_api_key else None

    @property
    def voice_api_token_value(self) -> str | None:
        token = self.rag_voice_api_token or self.rag_api_token
        return (
            token.get_secret_value()
            if token and token.get_secret_value()
            else None
        )

    @property
    def api_token_value(self) -> str | None:
        token = self.rag_api_token or self.rag_voice_api_token
        return token.get_secret_value() if token and token.get_secret_value() else None

    @property
    def voice_allowed_origins(self) -> frozenset[str]:
        return frozenset(
            item.strip() for item in self.rag_voice_allowed_origins.split(",") if item.strip()
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
