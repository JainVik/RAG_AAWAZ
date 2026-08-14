from __future__ import annotations

import hmac
import uuid
from typing import Protocol

from fastapi import APIRouter, Request, Response

from app.core.config import get_settings
from app.domain.enums import (
    AnswerMode,
    ErrorCode,
    GuardrailDecision,
    GuardrailReason,
    PipelineState,
)
from app.domain.models import (
    GuardrailResult,
    PipelineErrorResponse,
    QueryRequest,
    QueryResponse,
)
from app.harness.orchestrator import PipelineOrchestrator


class QueryServices(Protocol):
    orchestrator: PipelineOrchestrator | None


router = APIRouter(prefix="/v1/query", tags=["query"])


@router.post("/text", response_model=QueryResponse | PipelineErrorResponse)
async def text_query(
    body: QueryRequest, request: Request, response: Response
) -> QueryResponse | PipelineErrorResponse:
    services: QueryServices | None = getattr(request.app.state, "services", None)
    orchestrator = services.orchestrator if services is not None else None
    settings = orchestrator.settings if orchestrator is not None else get_settings()
    expected = settings.api_token_value
    if expected is not None:
        authorization = request.headers.get("authorization", "")
        scheme, _, provided = authorization.partition(" ")
        if scheme.casefold() != "bearer" or not hmac.compare_digest(provided, expected):
            response.status_code = 401
            return PipelineErrorResponse(
                request_id=body.request_id or f"req_{uuid.uuid4().hex}",
                code=ErrorCode.UNAUTHORIZED,
                state=PipelineState.FAILED,
                message="A valid bearer token is required.",
            )
    if orchestrator is None:
        return QueryResponse(
            request_id=body.request_id or f"req_{uuid.uuid4().hex}",
            transcript=body.query,
            language=body.language,
            answer=None,
            answer_mode=AnswerMode.ABSTENTION,
            guardrail=GuardrailResult(
                decision=GuardrailDecision.ABSTAIN,
                reason=GuardrailReason.DEPENDENCY_UNAVAILABLE,
                user_message="The retrieval index or embedding model is not ready.",
            ),
            state=PipelineState.DEPENDENCY_UNAVAILABLE,
        )
    return await orchestrator.process_text(
        body.query,
        language=body.language,
        request_id=body.request_id,
        deadline_ms=body.deadline_ms,
    )
