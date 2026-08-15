from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.domain.enums import AnswerMode, GuardrailDecision, Language, PipelineState
from app.domain.models import GuardrailResult, QueryResponse, server_event_adapter
from app.main import create_app


class UnreadyServices:
    orchestrator = None
    stt_factory = None
    settings = SimpleNamespace(rag_deadline_ms=200, rag_fallback_at_ms=170)

    async def readiness(self) -> dict[str, Any]:
        return {
            "status": "not_ready",
            "checks": {"index": {"ready": False, "reason": "not_built"}},
        }

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None


class ProtectedOrchestrator:
    settings = Settings(rag_api_token=SecretStr("shared-secret"))

    async def process_text(self, query: str, **_kwargs: Any) -> QueryResponse:
        return QueryResponse(
            request_id="req_protected",
            transcript=query,
            language=Language.ENGLISH,
            answer=None,
            answer_mode=AnswerMode.ABSTENTION,
            guardrail=GuardrailResult(decision=GuardrailDecision.ABSTAIN),
            state=PipelineState.ABSTAINED,
        )


class ProtectedServices(UnreadyServices):
    orchestrator = ProtectedOrchestrator()


def test_health_and_readiness_are_distinct() -> None:
    with TestClient(create_app(UnreadyServices())) as client:
        assert client.get("/health").status_code == 200
        readiness = client.get("/ready")
        assert readiness.status_code == 503
        payload = readiness.json()
        assert payload["status"] == "not_ready"
        assert payload["runtime"]["rag_deadline_ms"] == 200
        assert payload["runtime"]["rag_fallback_at_ms"] == 170


def test_text_contract_validates_and_dependency_failure_is_structured() -> None:
    with TestClient(create_app(UnreadyServices())) as client:
        invalid = client.post("/v1/query/text", json={"query": ""})
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "VALIDATION_ERROR"
        assert invalid.json()["state"] == "FAILED"
        assert client.post("/v1/query/text", json={"query": "x" * 4_097}).status_code == 422
        response = client.post("/v1/query/text", json={"query": "When was Goa formed?"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "DEPENDENCY_UNAVAILABLE"
        assert payload["guardrail"]["reason"] == "DEPENDENCY_UNAVAILABLE"


def test_text_endpoint_uses_shared_bearer_auth_when_configured() -> None:
    with TestClient(create_app(ProtectedServices())) as client:
        denied = client.post("/v1/query/text", json={"query": "question"})
        allowed = client.post(
            "/v1/query/text",
            json={"query": "question"},
            headers={"authorization": "Bearer shared-secret"},
        )

    assert denied.status_code == 401
    assert denied.json()["code"] == "UNAUTHORIZED"
    assert allowed.status_code == 200


def test_outbound_websocket_payloads_use_event_specific_schemas() -> None:
    with pytest.raises(ValidationError):
        server_event_adapter.validate_python(
            {
                "type": "pipeline_state",
                "version": "1",
                "request_id": "req",
                "payload": {"text": "wrong payload for this event"},
            }
        )


def test_evidence_summary_endpoint() -> None:
    with TestClient(create_app(UnreadyServices())) as client:
        response = client.get("/v1/evidence/summary")
        assert response.status_code == 200
        payload = response.json()
        assert "retrieval" in payload
        assert "corpus" in payload
        assert "chunk_representations" in payload
        assert "dataset_audit" in payload
        assert "corpus_scaling" in payload
        assert "guardrails" in payload
        assert "voice_latency" in payload
        assert "provenance" in payload

