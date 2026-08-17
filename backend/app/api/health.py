from __future__ import annotations

from typing import Any, Protocol

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app import __version__


class ReadinessProvider(Protocol):
    async def readiness(self) -> dict[str, Any]: ...


router = APIRouter(tags=["operations"])


@router.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "VANI RAG (Awaaz TideRAG) Backend API",
        "status": "online",
        "version": __version__,
        "frontend": "https://vani-rag.susdev.in",
        "documentation": "https://vani-rag.susdev.in/evidence",
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "version": __version__}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    services: ReadinessProvider | None = getattr(request.app.state, "services", None)
    if services is None:
        details: dict[str, Any] = {
            "status": "not_ready",
            "checks": {"services": {"ready": False, "reason": "not_initialized"}},
        }
    else:
        details = await services.readiness()
    runtime_settings = getattr(services, "settings", None)
    if runtime_settings is None:
        orchestrator = getattr(services, "orchestrator", None)
        runtime_settings = getattr(orchestrator, "settings", None)
    details["runtime"] = {
        "process_instance_id": getattr(request.app.state, "process_instance_id", None),
        "process_started_at": getattr(request.app.state, "process_started_at", None),
        "voice_requests_started": getattr(request.app.state, "voice_requests_started", None),
        "rag_deadline_ms": getattr(runtime_settings, "rag_deadline_ms", None),
        "rag_fallback_at_ms": getattr(runtime_settings, "rag_fallback_at_ms", None),
    }
    code = (
        status.HTTP_200_OK
        if details.get("status") == "ready"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=code, content=details)
