from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import AnswerMode, ChunkStrategy, PipelineState
from app.domain.models import Citation, GuardrailResult, SearchHit, Transcript


class StageContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    absolute_deadline_ns: int = Field(gt=0)


class GuardStageInput(StageContract):
    transcript: Transcript


class GuardStageOutput(StageContract):
    result: GuardrailResult


class RetrievalStageInput(StageContract):
    query: str
    strategies: tuple[ChunkStrategy, ...]
    dense_limit: int = Field(gt=0)
    sparse_limit: int = Field(ge=0)


class RetrievalStageOutput(StageContract):
    dense_hits: tuple[SearchHit, ...]
    sparse_hits: tuple[SearchHit, ...]
    fused_hits: tuple[SearchHit, ...]
    evidence_agreement: float = Field(ge=0.0, le=1.0)
    sparse_failed: bool = False


class EvidenceStageInput(StageContract):
    query: str
    parent_hits: tuple[SearchHit, ...]
    evidence_limit: int = Field(gt=0)


class EvidenceStageOutput(StageContract):
    evidence: tuple[SearchHit, ...]


class GenerationStageInput(StageContract):
    query: str
    evidence: tuple[SearchHit, ...]


class GenerationStageOutput(StageContract):
    answer: str
    mode: AnswerMode
    citations: tuple[Citation, ...]


class VerificationStageInput(StageContract):
    answer: str
    mode: AnswerMode
    citations: tuple[Citation, ...]


class VerificationStageOutput(StageContract):
    result: GuardrailResult


class StagePolicy(BaseModel):
    """Explicit execution policy for each orchestrated stage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: PipelineState
    max_attempts: int = Field(ge=1, le=3)
    optional: bool = False
    fallback_state: PipelineState


STAGE_POLICIES: dict[PipelineState, StagePolicy] = {
    PipelineState.INPUT_GUARDED: StagePolicy(
        state=PipelineState.INPUT_GUARDED,
        max_attempts=1,
        fallback_state=PipelineState.ABSTAINED,
    ),
    PipelineState.RETRIEVED: StagePolicy(
        state=PipelineState.RETRIEVED,
        max_attempts=2,
        fallback_state=PipelineState.DEPENDENCY_UNAVAILABLE,
    ),
    PipelineState.EVIDENCE_SELECTED: StagePolicy(
        state=PipelineState.EVIDENCE_SELECTED,
        max_attempts=1,
        optional=True,
        fallback_state=PipelineState.DEADLINE_FALLBACK,
    ),
    PipelineState.ANSWERED: StagePolicy(
        state=PipelineState.ANSWERED,
        max_attempts=1,
        optional=True,
        fallback_state=PipelineState.DEADLINE_FALLBACK,
    ),
    PipelineState.VERIFIED: StagePolicy(
        state=PipelineState.VERIFIED,
        max_attempts=1,
        fallback_state=PipelineState.ABSTAINED,
    ),
}
