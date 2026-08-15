from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services import DefaultServices


@pytest.mark.asyncio
async def test_optional_groq_missing_key_does_not_disable_core_readiness() -> None:
    settings = Settings(
        rag_target_unique_passages=10,
        rag_development_passages=1,
        rag_enable_groq_synthesis=True,
        groq_api_key="",
    )
    services = DefaultServices(settings)
    services._configure_groq()
    services._checks.update(
        {
            name: {"ready": True}
            for name in ("index", "model", "qdrant", "sarvam", "thresholds")
        }
    )

    readiness = await services.readiness()

    assert readiness["status"] == "ready"
    assert readiness["checks"]["groq"] == {
        "ready": False,
        "required": False,
        "enabled": True,
        "reason": "GROQ_API_KEY_not_configured",
    }
