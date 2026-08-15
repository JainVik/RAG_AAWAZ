from __future__ import annotations

import uuid
from typing import TypedDict

from app.core.config import Settings
from app.core.deadlines import Deadline
from app.core.errors import DeadlineExceeded, PipelineError
from app.domain.enums import (
    AnswerMode,
    GuardrailDecision,
    GuardrailReason,
    Language,
    PipelineState,
)
from app.domain.models import (
    GuardrailResult,
    QueryResponse,
    SearchHit,
    Transcript,
)
from app.generation.grounded_generator import (
    GroundedAnswerGenerator,
    citation_from_evidence,
    extract_first_evidence_sentence,
)
from app.guardrails.answerability_gate import check_answerability
from app.guardrails.evidence_agreement import check_evidence_agreement
from app.guardrails.evidence_conflict import check_evidence_conflict
from app.guardrails.freshness_gate import check_freshness
from app.guardrails.grounding_verifier import verify_extractive_grounding
from app.guardrails.injection_gate import check_prompt_injection
from app.guardrails.safety_gate import check_safety
from app.harness.context import PipelineContext
from app.harness.retry import RetryPolicy, with_retry
from app.harness.stages import (
    STAGE_POLICIES,
    EvidenceStageInput,
    EvidenceStageOutput,
    GenerationStageInput,
    GenerationStageOutput,
    GuardStageInput,
    GuardStageOutput,
    RetrievalStageInput,
    RetrievalStageOutput,
    VerificationStageInput,
    VerificationStageOutput,
)
from app.retrieval.hybrid import HybridRetriever, RetrievalResult
from app.retrieval.late_chunking import select_evidence_windows
from app.retrieval.router import TideRouter
from app.telemetry.recorder import MetricsRecorder, metrics_recorder


class _StageFields(TypedDict):
    request_id: str
    absolute_deadline_ns: int


class PipelineOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        retriever: HybridRetriever,
        generator: GroundedAnswerGenerator,
        router: TideRouter | None = None,
        recorder: MetricsRecorder = metrics_recorder,
    ) -> None:
        self.settings = settings
        self.retriever = retriever
        self.generator = generator
        base_router = router or TideRouter(
            settings.dense_candidate_limit,
            settings.sparse_candidate_limit,
        )
        self.router = TideRouter(
            base_router.dense_limit,
            base_router.sparse_limit,
            enabled_strategies=settings.enabled_chunk_strategies,
            enable_sparse=settings.rag_enable_sparse,
        )
        self.recorder = recorder

    async def process_text(
        self,
        query: str,
        *,
        language: Language = Language.UNKNOWN,
        request_id: str | None = None,
        deadline_ms: int | None = None,
    ) -> QueryResponse:
        effective_deadline = deadline_ms or self.settings.rag_deadline_ms
        fallback_at = min(self.settings.rag_fallback_at_ms, effective_deadline - 1)
        deadline = Deadline.after_ms(effective_deadline, fallback_at)
        transcript = Transcript(
            text=query,
            language=language,
            confidence=None,
            is_final=True,
            received_ns=deadline.started_ns,
        )
        return await self.process_transcript(transcript, deadline=deadline, request_id=request_id)

    async def process_transcript(
        self,
        transcript: Transcript,
        *,
        deadline: Deadline,
        request_id: str | None = None,
        retrieval_override: RetrievalResult | None = None,
        record_response: bool = True,
    ) -> QueryResponse:
        resolved_request_id = request_id or f"req_{uuid.uuid4().hex}"
        initial_state = (
            PipelineState.STT_FINAL if transcript.is_final else PipelineState.STT_PARTIAL
        )
        context = PipelineContext(
            request_id=resolved_request_id,
            deadline=deadline,
            state=initial_state,
            history=[initial_state],
        )
        evidence: list[SearchHit] = []
        agreement: float | None = None

        def finish(response: QueryResponse) -> QueryResponse:
            if record_response:
                self.recorder.record_response(response)
            return response

        if not transcript.is_final:
            response = self._guardrail_response(
                context,
                transcript,
                GuardrailResult(
                    decision=GuardrailDecision.NEEDS_REPEAT,
                    reason=GuardrailReason.LOW_STT_CONFIDENCE,
                    evidence={"is_final": False},
                    user_message=(
                        "A final transcript was not available. Please repeat the question."
                    ),
                ),
                PipelineState.NEEDS_REPEAT,
            )
            return finish(response)

        try:
            async with context.stage(PipelineState.INPUT_GUARDED):
                stage_fields: _StageFields = {
                    "request_id": resolved_request_id,
                    "absolute_deadline_ns": deadline.expires_ns,
                }
                guard_input = GuardStageInput(
                    **stage_fields,
                    transcript=transcript,
                )
                if transcript.confidence is not None and (
                    transcript.confidence < self.settings.min_stt_confidence
                ):
                    low_confidence = GuardrailResult(
                        decision=GuardrailDecision.NEEDS_REPEAT,
                        reason=GuardrailReason.LOW_STT_CONFIDENCE,
                        evidence={
                            "confidence": transcript.confidence,
                            "minimum": self.settings.min_stt_confidence,
                        },
                        user_message="The speech was unclear. Please repeat the question.",
                    )
                    guard_output = GuardStageOutput(
                        **stage_fields,
                        result=low_confidence,
                    )
                    return finish(
                        self._guardrail_response(
                            context,
                            guard_input.transcript,
                            guard_output.result,
                            PipelineState.NEEDS_REPEAT,
                        )
                    )
                for input_gate in (check_prompt_injection, check_safety, check_freshness):
                    decision = input_gate(guard_input.transcript.text)
                    guard_output = GuardStageOutput(
                        **stage_fields,
                        result=decision,
                    )
                    if guard_output.result.decision != GuardrailDecision.ALLOW:
                        terminal = (
                            PipelineState.UNSAFE
                            if guard_output.result.reason == GuardrailReason.UNSAFE_REQUEST
                            else PipelineState.ABSTAINED
                        )
                        return finish(
                            self._guardrail_response(
                                context,
                                guard_input.transcript,
                                guard_output.result,
                                terminal,
                            )
                        )

            plan = self.router.route(
                transcript.text,
                stt_confidence=transcript.confidence,
                language_hint=(
                    transcript.language
                    if transcript.language != Language.UNKNOWN
                    else None
                ),
            )
            if transcript.language == Language.UNKNOWN:
                transcript = transcript.model_copy(update={"language": plan.language})

            async with context.stage(PipelineState.RETRIEVED):
                retrieval_input = RetrievalStageInput(
                    **stage_fields,
                    query=transcript.text,
                    strategies=plan.strategies,
                    dense_limit=plan.dense_limit,
                    sparse_limit=plan.sparse_limit,
                )
                if retrieval_override is not None:
                    retrieval = retrieval_override
                else:

                    async def retrieve_once() -> RetrievalResult:
                        return await self.retriever.retrieve(retrieval_input.query, plan, deadline)

                    policy = STAGE_POLICIES[PipelineState.RETRIEVED]
                    retrieval = await with_retry(
                        retrieve_once,
                        deadline=deadline,
                        policy=RetryPolicy(
                            max_attempts=policy.max_attempts,
                            initial_backoff_ms=3.0,
                            minimum_remaining_ms=35.0,
                        ),
                        is_retryable=lambda exc: (isinstance(exc, PipelineError) and exc.retryable),
                    )
                retrieval_output = RetrievalStageOutput(
                    **stage_fields,
                    dense_hits=retrieval.dense_hits,
                    sparse_hits=retrieval.sparse_hits,
                    fused_hits=retrieval.fused_hits,
                    evidence_agreement=retrieval.agreement,
                    sparse_failed=retrieval.sparse_failed,
                )
                evidence = list(retrieval_output.fused_hits)
                agreement = retrieval_output.evidence_agreement

            retrieval_gate = self._retrieval_gate(
                retrieval,
                sparse_required=(plan.sparse_weight > 0.0 and plan.sparse_limit > 0),
            )
            if retrieval_gate.decision != GuardrailDecision.ALLOW:
                return finish(
                    self._guardrail_response(
                        context,
                        transcript,
                        retrieval_gate,
                        PipelineState.ABSTAINED,
                        agreement,
                    )
                )

            conflict_gate = check_evidence_conflict(evidence)
            if conflict_gate.decision != GuardrailDecision.ALLOW:
                return finish(
                    self._guardrail_response(
                        context,
                        transcript,
                        conflict_gate,
                        PipelineState.ABSTAINED,
                        agreement,
                    )
                )

            async with context.stage(PipelineState.EVIDENCE_SELECTED):
                evidence_input = EvidenceStageInput(
                    **stage_fields,
                    query=transcript.text,
                    parent_hits=tuple(evidence),
                    evidence_limit=self.settings.final_evidence_limit,
                )
                if self.settings.rag_enable_late_chunking and deadline.optional_work_allowed:
                    evidence = select_evidence_windows(
                        evidence_input.query,
                        evidence_input.parent_hits,
                        limit=evidence_input.evidence_limit,
                        preferred_language=transcript.language,
                    )
                    deadline.check()
                else:
                    evidence = list(evidence_input.parent_hits[: evidence_input.evidence_limit])
                evidence_output = EvidenceStageOutput(
                    **stage_fields,
                    evidence=tuple(evidence),
                )
                evidence = list(evidence_output.evidence)
                if not evidence:
                    return finish(
                        self._guardrail_response(
                            context,
                            transcript,
                            GuardrailResult(
                                decision=GuardrailDecision.ABSTAIN,
                                reason=GuardrailReason.NO_RELEVANT_EVIDENCE,
                                user_message="I could not select enough evidence to answer.",
                            ),
                            PipelineState.ABSTAINED,
                            agreement,
                        )
                    )

            if not deadline.optional_work_allowed:
                return finish(
                    self._evidence_fallback(context, transcript, evidence[0], agreement)
                )

            async with context.stage(PipelineState.ANSWERED):
                generation_input = GenerationStageInput(
                    **stage_fields,
                    query=transcript.text,
                    evidence=tuple(evidence),
                )
                generated = await deadline.run_optional(
                    self.generator.generate(generation_input.query, list(generation_input.evidence))
                )
                generation_output = GenerationStageOutput(
                    **stage_fields,
                    answer=generated.text,
                    mode=generated.mode,
                    citations=generated.citations,
                )

            async with context.stage(PipelineState.VERIFIED):
                verification_input = VerificationStageInput(
                    **stage_fields,
                    answer=generation_output.answer,
                    mode=generation_output.mode,
                    citations=generation_output.citations,
                )
                if verification_input.answer != generated.text:
                    raise ValueError("Generation stage contract changed the answer text")
                grounding = verify_extractive_grounding(generated, evidence)
                verification_output = VerificationStageOutput(
                    **stage_fields,
                    result=grounding,
                )
                if verification_output.result.decision != GuardrailDecision.ALLOW:
                    return finish(
                        self._guardrail_response(
                            context,
                            transcript,
                            verification_output.result,
                            PipelineState.ABSTAINED,
                            agreement,
                        )
                    )

            context.transition(PipelineState.COMPLETED)
            return finish(
                QueryResponse(
                    request_id=resolved_request_id,
                    transcript=transcript.text,
                    language=transcript.language,
                    answer=generation_output.answer,
                    answer_mode=generation_output.mode,
                    citations=list(generation_output.citations),
                    guardrail=GuardrailResult(decision=GuardrailDecision.ALLOW),
                    evidence_agreement=agreement,
                    state=PipelineState.COMPLETED,
                    timings_ms=context.timing_map(),
                )
            )
        except DeadlineExceeded:
            if evidence:
                response = self._evidence_fallback(context, transcript, evidence[0], agreement)
            else:
                response = self._guardrail_response(
                    context,
                    transcript,
                    GuardrailResult(
                        decision=GuardrailDecision.ABSTAIN,
                        reason=GuardrailReason.DEADLINE_EXCEEDED,
                        user_message="The deadline expired before reliable evidence was ready.",
                    ),
                    PipelineState.DEADLINE_FALLBACK,
                    agreement,
                )
            return finish(response)
        except PipelineError as exc:
            return finish(
                self._guardrail_response(
                    context,
                    transcript,
                    GuardrailResult(
                        decision=GuardrailDecision.ABSTAIN,
                        reason=GuardrailReason.DEPENDENCY_UNAVAILABLE,
                        evidence={"error_code": exc.code.value},
                        user_message="A required service is temporarily unavailable.",
                    ),
                    exc.state,
                    agreement,
                )
            )
        except Exception as exc:
            return finish(
                self._guardrail_response(
                    context,
                    transcript,
                    GuardrailResult(
                        decision=GuardrailDecision.ABSTAIN,
                        reason=GuardrailReason.DEPENDENCY_UNAVAILABLE,
                        evidence={"error_type": type(exc).__name__},
                        user_message="The request could not be completed reliably.",
                    ),
                    PipelineState.FAILED,
                    agreement,
                )
            )

    def _retrieval_gate(
        self, retrieval: RetrievalResult, *, sparse_required: bool
    ) -> GuardrailResult:
        answerability = check_answerability(
            retrieval.fused_hits,
            minimum_score=self.settings.min_answer_score,
            minimum_margin=self.settings.min_score_margin,
        )
        if answerability.decision != GuardrailDecision.ALLOW:
            return answerability
        if sparse_required and (retrieval.sparse_failed or not retrieval.sparse_hits):
            return GuardrailResult(
                decision=GuardrailDecision.ABSTAIN,
                reason=GuardrailReason.RETRIEVAL_DISAGREEMENT,
                evidence={
                    "sparse_required": True,
                    "sparse_failed": retrieval.sparse_failed,
                    "sparse_hit_count": len(retrieval.sparse_hits),
                },
                user_message=(
                    "The retrieval signals did not provide enough agreement to answer safely."
                ),
            )
        if sparse_required:
            return check_evidence_agreement(
                retrieval.agreement, self.settings.min_evidence_agreement
            )
        return GuardrailResult(decision=GuardrailDecision.ALLOW)

    def _evidence_fallback(
        self,
        context: PipelineContext,
        transcript: Transcript,
        hit: SearchHit,
        agreement: float | None,
    ) -> QueryResponse:
        context.transition(PipelineState.DEADLINE_FALLBACK)
        extracted = extract_first_evidence_sentence(hit)
        return QueryResponse(
            request_id=context.request_id,
            transcript=transcript.text,
            language=transcript.language,
            answer=extracted.text,
            answer_mode=AnswerMode.EVIDENCE_FALLBACK,
            citations=[citation_from_evidence(extracted)],
            guardrail=GuardrailResult(
                decision=GuardrailDecision.WARN,
                reason=GuardrailReason.DEADLINE_EXCEEDED,
                user_message="The deadline was reached; returning direct cited evidence.",
            ),
            evidence_agreement=agreement,
            state=PipelineState.DEADLINE_FALLBACK,
            timings_ms=context.timing_map(),
        )

    @staticmethod
    def _guardrail_response(
        context: PipelineContext,
        transcript: Transcript,
        guardrail: GuardrailResult,
        state: PipelineState,
        agreement: float | None = None,
    ) -> QueryResponse:
        context.transition(state)
        return QueryResponse(
            request_id=context.request_id,
            transcript=transcript.text,
            language=transcript.language,
            answer=None,
            answer_mode=AnswerMode.ABSTENTION,
            citations=[],
            guardrail=guardrail,
            evidence_agreement=agreement,
            state=state,
            timings_ms=context.timing_map(),
        )
