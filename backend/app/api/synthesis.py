from __future__ import annotations

import hmac
import logging
import time
from typing import Protocol

from fastapi import APIRouter, Request, Response

from app.core.config import Settings, get_settings
from app.domain.enums import (
    ErrorCode,
    GuardrailDecision,
    GuardrailReason,
    PipelineState,
    SynthesisStatus,
)
from app.domain.models import (
    GuardrailResult,
    PipelineErrorResponse,
    SynthesisRequest,
    SynthesisResponse,
)
from app.generation.groq_synthesizer import (
    GroqGroundedSynthesizer,
    GroqGroundingFailed,
    GroqProviderUnavailable,
    GroqRequestTimedOut,
)
from app.generation.synthesis_context import SynthesisContextStore
from app.telemetry.recorder import metrics_recorder


class SynthesisServices(Protocol):
    settings: Settings
    synthesis_contexts: SynthesisContextStore | None
    groq_synthesizer: GroqGroundedSynthesizer | None


router = APIRouter(prefix="/v1/query", tags=["query"])
logger = logging.getLogger(__name__)


def _terminal_response(
    body: SynthesisRequest,
    settings: Settings,
    *,
    status: SynthesisStatus,
    guardrail: GuardrailResult,
    started_ns: int,
) -> SynthesisResponse:
    total_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
    timings = {"total_synthesis": total_ms}
    result = SynthesisResponse(
        request_id=body.request_id,
        model=settings.groq_model,
        status=status,
        answer=None,
        guardrail=guardrail,
        timings_ms=timings,
    )
    metrics_recorder.record_synthesis(result)
    return result


@router.post("/synthesis", response_model=SynthesisResponse | PipelineErrorResponse)
async def synthesize_query(
    body: SynthesisRequest, request: Request, response: Response
) -> SynthesisResponse | PipelineErrorResponse:
    started_ns = time.perf_counter_ns()
    services: SynthesisServices | None = getattr(request.app.state, "services", None)
    settings = services.settings if services is not None else get_settings()
    expected = settings.api_token_value
    if expected is not None:
        authorization = request.headers.get("authorization", "")
        scheme, _, provided = authorization.partition(" ")
        if scheme.casefold() != "bearer" or not hmac.compare_digest(provided, expected):
            response.status_code = 401
            return PipelineErrorResponse(
                request_id=body.request_id,
                code=ErrorCode.UNAUTHORIZED,
                state=PipelineState.FAILED,
                message="A valid bearer token is required.",
            )

    contexts = getattr(services, "synthesis_contexts", None)
    synthesizer = getattr(services, "groq_synthesizer", None)
    if (
        not settings.rag_enable_groq_synthesis
        or contexts is None
        or synthesizer is None
    ):
        return _terminal_response(
            body,
            settings,
            status=SynthesisStatus.UNAVAILABLE,
            guardrail=GuardrailResult(
                decision=GuardrailDecision.ABSTAIN,
                reason=GuardrailReason.DEPENDENCY_UNAVAILABLE,
                user_message="Optional Groq synthesis is not configured.",
            ),
            started_ns=started_ns,
        )

    context = await contexts.take(body.token, request_id=body.request_id)
    if context is None:
        return _terminal_response(
            body,
            settings,
            status=SynthesisStatus.UNAVAILABLE,
            guardrail=GuardrailResult(
                decision=GuardrailDecision.ABSTAIN,
                reason=GuardrailReason.DEPENDENCY_UNAVAILABLE,
                user_message="The synthesis offer is invalid, expired, or already used.",
            ),
            started_ns=started_ns,
        )

    try:
        generated = await synthesizer.synthesize(context)
    except GroqRequestTimedOut:
        return _terminal_response(
            body,
            settings,
            status=SynthesisStatus.TIMED_OUT,
            guardrail=GuardrailResult(
                decision=GuardrailDecision.ABSTAIN,
                reason=GuardrailReason.DEADLINE_EXCEEDED,
                user_message=(
                    "The optional Groq response timed out; the extractive answer remains valid."
                ),
            ),
            started_ns=started_ns,
        )
    except GroqProviderUnavailable:
        return _terminal_response(
            body,
            settings,
            status=SynthesisStatus.UNAVAILABLE,
            guardrail=GuardrailResult(
                decision=GuardrailDecision.ABSTAIN,
                reason=GuardrailReason.DEPENDENCY_UNAVAILABLE,
                user_message=(
                    "Groq synthesis is temporarily unavailable; the extractive answer remains "
                    "valid."
                ),
            ),
            started_ns=started_ns,
        )
    except GroqGroundingFailed as exc:
        logger.warning("Groq grounding failed for %s: %s", body.request_id, exc)
        return _terminal_response(
            body,
            settings,
            status=SynthesisStatus.GROUNDING_FAILED,
            guardrail=GuardrailResult(
                decision=GuardrailDecision.ABSTAIN,
                reason=GuardrailReason.UNSUPPORTED_CLAIM,
                user_message=(
                    "The optional generated wording could not be grounded; the extractive answer "
                    "remains valid."
                ),
            ),
            started_ns=started_ns,
        )
    except Exception as exc:
        logger.error(
            "Unexpected optional synthesis failure",
            extra={
                "context": {
                    "request_id": body.request_id,
                    "error_type": type(exc).__name__,
                }
            },
        )
        return _terminal_response(
            body,
            settings,
            status=SynthesisStatus.UNAVAILABLE,
            guardrail=GuardrailResult(
                decision=GuardrailDecision.ABSTAIN,
                reason=GuardrailReason.DEPENDENCY_UNAVAILABLE,
                user_message=(
                    "Optional synthesis could not be completed; the extractive answer remains "
                    "valid."
                ),
            ),
            started_ns=started_ns,
        )

    total_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
    if generated.answer is None:
        result = SynthesisResponse(
            request_id=body.request_id,
            model=settings.groq_model,
            status=SynthesisStatus.ABSTAINED,
            answer=None,
            guardrail=GuardrailResult(
                decision=GuardrailDecision.ABSTAIN,
                reason=GuardrailReason.NO_RELEVANT_EVIDENCE,
                user_message=(
                    "Groq did not find enough support to synthesize beyond the extractive answer."
                ),
            ),
            timings_ms={
                "groq_synthesis": generated.provider_latency_ms,
                "total_synthesis": total_ms,
            },
        )
    else:
        result = SynthesisResponse(
            request_id=body.request_id,
            model=settings.groq_model,
            status=SynthesisStatus.COMPLETED,
            answer=generated.answer,
            claims=list(generated.claims),
            citations=list(generated.citations),
            guardrail=GuardrailResult(decision=GuardrailDecision.ALLOW),
            timings_ms={
                "groq_synthesis": generated.provider_latency_ms,
                "total_synthesis": total_ms,
            },
        )
    metrics_recorder.record_synthesis(result)
    return result
