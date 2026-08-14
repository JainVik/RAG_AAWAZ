from __future__ import annotations

from fastapi import APIRouter

from app.telemetry.recorder import metrics_recorder

router = APIRouter(tags=["operations"])


@router.get("/metrics")
async def metrics() -> dict[str, object]:
    return metrics_recorder.snapshot()

