from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.evidence import router as evidence_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.text_query import router as text_router
from app.api.voice_ws import router as voice_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.domain.enums import ErrorCode, PipelineState
from app.domain.models import PipelineErrorResponse


def create_app(services: Any | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.process_instance_id = uuid4().hex
        application.state.process_started_at = datetime.now(UTC).isoformat()
        application.state.voice_requests_started = 0
        resolved_services = services
        if resolved_services is None:
            from app.services import DefaultServices

            resolved_services = DefaultServices(settings)
        application.state.services = resolved_services
        initialize = getattr(resolved_services, "initialize", None)
        if initialize is not None:
            await initialize()
        try:
            yield
        finally:
            close = getattr(resolved_services, "close", None)
            if close is not None:
                await close()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        response = PipelineErrorResponse(
            request_id=f"req_{uuid4().hex}",
            code=ErrorCode.VALIDATION_ERROR,
            state=PipelineState.FAILED,
            message="The request payload did not match the versioned API schema.",
            details={"error_count": len(exc.errors())},
        )
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(text_router)
    application.include_router(voice_router)
    application.include_router(metrics_router)
    application.include_router(evidence_router)
    return application


app = create_app()
