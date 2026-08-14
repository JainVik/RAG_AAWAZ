from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from app.domain.enums import (
    AnswerMode,
    ChunkStrategy,
    ErrorCode,
    GuardrailDecision,
    GuardrailReason,
    Language,
    PipelineState,
    SttEventType,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
QueryText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_096)
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryRequest(StrictModel):
    query: QueryText
    language: Language = Language.UNKNOWN
    request_id: str | None = Field(default=None, max_length=128)
    deadline_ms: int | None = Field(default=None, ge=20, le=30_000)


class Transcript(StrictModel):
    text: QueryText
    language: Language = Language.UNKNOWN
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_final: bool
    received_ns: int


class CorpusDocument(StrictModel):
    canonical_doc_id: str
    parent_id: str
    english_text: str
    translated_text: str | None = None
    translation_language: str | None = None
    translation_model: str | None = None
    source_id: str | None = None


class Chunk(StrictModel):
    canonical_doc_id: str
    parent_id: str
    chunk_id: str
    language: Language
    strategy: ChunkStrategy
    text: str
    span_start: int = Field(ge=0)
    span_end: int = Field(ge=0)
    english_text: str | None = None
    translated_text: str | None = None
    translation_model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_span(self) -> Chunk:
        if self.span_end < self.span_start:
            raise ValueError("span_end must not precede span_start")
        return self


class SparseVector(StrictModel):
    indices: list[int]
    values: list[float]

    @model_validator(mode="after")
    def validate_lengths(self) -> SparseVector:
        if len(self.indices) != len(self.values):
            raise ValueError("sparse indices and values must have equal lengths")
        if self.indices != sorted(self.indices):
            raise ValueError("sparse indices must be sorted")
        return self


class SearchHit(StrictModel):
    canonical_doc_id: str
    parent_id: str
    chunk_id: str
    text: str
    parent_text: str | None = None
    language: Language
    strategy: ChunkStrategy
    span_start: int
    span_end: int
    score: float
    dense_score: float | None = None
    sparse_score: float | None = None
    rank_sources: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(StrictModel):
    canonical_doc_id: str
    parent_id: str
    chunk_id: str
    strategy: ChunkStrategy
    text: str
    span_start: int
    span_end: int
    span_coordinate_system: Literal[
        "parent_text", "chunk_text", "paired_representation"
    ]
    source_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dense_score: float | None = None
    sparse_score: float | None = None


class GuardrailResult(StrictModel):
    decision: GuardrailDecision
    reason: GuardrailReason | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    user_message: str | None = None


class StageTiming(StrictModel):
    state: PipelineState
    started_ns: int
    ended_ns: int
    duration_ms: float = Field(ge=0.0)
    outcome: Literal["ok", "fallback", "error", "cancelled"] = "ok"
    error_code: ErrorCode | None = None


class QueryResponse(StrictModel):
    request_id: str
    transcript: str
    language: Language
    answer: str | None
    answer_mode: AnswerMode
    citations: list[Citation] = Field(default_factory=list)
    guardrail: GuardrailResult
    evidence_agreement: float | None = Field(default=None, ge=0.0, le=1.0)
    state: PipelineState
    timings_ms: dict[str, float] = Field(default_factory=dict)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PipelineErrorResponse(StrictModel):
    request_id: str = Field(max_length=128)
    code: ErrorCode
    state: PipelineState
    message: str = Field(min_length=1, max_length=1_024)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class SttEvent(StrictModel):
    event_type: SttEventType
    text: str = ""
    language: Language = Language.UNKNOWN
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class AudioStartEvent(StrictModel):
    type: Literal["start"]
    version: Literal["1"]
    request_id: str | None = Field(default=None, max_length=128)
    encoding: Literal["pcm_s16le", "wav", "webm_opus"] = "pcm_s16le"
    sample_rate_hz: int = Field(default=16_000, ge=8_000, le=48_000)
    language: Language = Language.UNKNOWN


class AudioChunkEvent(StrictModel):
    type: Literal["audio_chunk"]
    version: Literal["1"]
    sequence: int = Field(ge=0)
    audio_b64: str = Field(min_length=1, max_length=2_560_000)


class EndOfStreamEvent(StrictModel):
    type: Literal["end_of_stream"]
    version: Literal["1"]


class SttPartialPayload(StrictModel):
    text: str = Field(max_length=4_096)
    language: Language
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class PipelineStatePayload(StrictModel):
    state: PipelineState


class VoiceErrorPayload(StrictModel):
    code: ErrorCode
    state: PipelineState
    message: str = Field(min_length=1, max_length=1_024)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)


class SttPartialServerEvent(StrictModel):
    type: Literal["stt_partial"]
    version: Literal["1"] = "1"
    request_id: str = Field(max_length=128)
    payload: SttPartialPayload


class PipelineStateServerEvent(StrictModel):
    type: Literal["pipeline_state"]
    version: Literal["1"] = "1"
    request_id: str = Field(max_length=128)
    payload: PipelineStatePayload


class AnswerServerEvent(StrictModel):
    type: Literal["answer"]
    version: Literal["1"] = "1"
    request_id: str = Field(max_length=128)
    payload: QueryResponse


class ErrorServerEvent(StrictModel):
    type: Literal["error"]
    version: Literal["1"] = "1"
    request_id: str = Field(max_length=128)
    payload: VoiceErrorPayload


ServerEvent = Annotated[
    SttPartialServerEvent
    | PipelineStateServerEvent
    | AnswerServerEvent
    | ErrorServerEvent,
    Field(discriminator="type"),
]
server_event_adapter: TypeAdapter[ServerEvent] = TypeAdapter(ServerEvent)
