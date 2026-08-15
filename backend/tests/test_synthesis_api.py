from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.domain.enums import (
    ChunkStrategy,
    GuardrailDecision,
    Language,
    SynthesisStatus,
)
from app.domain.models import (
    GuardrailResult,
    SearchHit,
    SynthesisClaim,
    SynthesisResponse,
)
from app.generation.groq_synthesizer import (
    GroqGroundingFailed,
    GroqProviderUnavailable,
    GroqRequestTimedOut,
    GroqSynthesisResult,
    _citation_for_hit,
)
from app.generation.synthesis_context import SynthesisContext, SynthesisContextStore
from app.main import create_app


def _context() -> SynthesisContext:
    text = "Goa became a state in 1987."
    return SynthesisContext(
        request_id="req-synthesis",
        query="When did Goa become a state?",
        language=Language.ENGLISH,
        evidence=(
            SearchHit(
                canonical_doc_id="doc",
                parent_id="doc",
                chunk_id="chunk",
                text=text,
                parent_text=text,
                language=Language.ENGLISH,
                strategy=ChunkStrategy.ATOMIC,
                span_start=0,
                span_end=len(text),
                score=1.0,
            ),
        ),
    )


class _FakeSynthesizer:
    def __init__(self, outcome: GroqSynthesisResult | Exception) -> None:
        self.outcome = outcome

    async def synthesize(self, _context: SynthesisContext) -> GroqSynthesisResult:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _Services:
    def __init__(
        self,
        outcome: GroqSynthesisResult | Exception,
        *,
        api_token: str | None = None,
    ) -> None:
        self.settings = Settings(
            rag_target_unique_passages=10,
            rag_development_passages=1,
            rag_enable_groq_synthesis=True,
            groq_api_key=SecretStr("groq-test-key"),
            rag_api_token=SecretStr(api_token) if api_token is not None else None,
        )
        self.synthesis_contexts = SynthesisContextStore(ttl_s=60, max_entries=4)
        self.groq_synthesizer: Any = _FakeSynthesizer(outcome)
        self.token = ""

    async def initialize(self) -> None:
        self.token = await self.synthesis_contexts.put(_context())

    async def close(self) -> None:
        return None


def _completed_result() -> GroqSynthesisResult:
    hit = _context().evidence[0]
    return GroqSynthesisResult(
        answer="Goa became a state in 1987.",
        claims=(SynthesisClaim(text="Goa became a state in 1987.", citation_indices=[0]),),
        citations=(_citation_for_hit(hit),),
        provider_latency_ms=12.5,
    )


def _post(client: TestClient, services: _Services, **kwargs: Any) -> Any:
    return client.post(
        "/v1/query/synthesis",
        json={"request_id": "req-synthesis", "token": services.token},
        **kwargs,
    )


def test_synthesis_endpoint_returns_separate_grounded_result_and_consumes_offer() -> None:
    services = _Services(_completed_result())
    with TestClient(create_app(services)) as client:
        response = _post(client, services)
        repeated = _post(client, services)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["answer"] == "Goa became a state in 1987."
    assert payload["claims"] == [
        {"text": "Goa became a state in 1987.", "citation_indices": [0]}
    ]
    assert payload["citations"]
    assert payload["timings_ms"]["groq_synthesis"] == 12.5
    assert payload["timings_ms"]["total_synthesis"] >= 0
    assert payload["retryable"] is False
    assert repeated.json()["status"] == "unavailable"
    assert repeated.json()["answer"] is None


def test_synthesis_auth_is_checked_before_consuming_offer() -> None:
    services = _Services(_completed_result(), api_token="shared-secret")
    with TestClient(create_app(services)) as client:
        denied = _post(client, services)
        allowed = _post(
            client,
            services,
            headers={"Authorization": "Bearer shared-secret"},
        )

    assert denied.status_code == 401
    assert denied.json()["code"] == "UNAUTHORIZED"
    assert allowed.json()["status"] == "completed"


def test_synthesis_endpoint_maps_provider_failures_without_retrying_one_use_token() -> None:
    cases: list[tuple[Exception, str, str]] = [
        (GroqRequestTimedOut(), "timed_out", "DEADLINE_EXCEEDED"),
        (
            GroqProviderUnavailable(retryable=True),
            "unavailable",
            "DEPENDENCY_UNAVAILABLE",
        ),
        (GroqGroundingFailed("private model text"), "grounding_failed", "UNSUPPORTED_CLAIM"),
        (RuntimeError("private model text"), "unavailable", "DEPENDENCY_UNAVAILABLE"),
    ]
    for error, expected_status, expected_reason in cases:
        services = _Services(error)
        with TestClient(create_app(services)) as client:
            response = _post(client, services)
        payload = response.json()
        assert response.status_code == 200
        assert payload["status"] == expected_status
        assert payload["guardrail"]["reason"] == expected_reason
        assert payload["answer"] is None
        assert payload["claims"] == []
        assert payload["citations"] == []
        assert payload["retryable"] is False
        assert "private model text" not in response.text


def test_invalid_synthesis_offer_is_typed_json() -> None:
    services = _Services(_completed_result())
    with TestClient(create_app(services)) as client:
        response = client.post(
            "/v1/query/synthesis",
            json={"request_id": "req-synthesis", "token": "x" * 43},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["status"] == "unavailable"
    assert response.json()["retryable"] is False


def test_synthesis_contract_rejects_invalid_claim_indices_and_mismatched_answer() -> None:
    for indices in ([-1], [0, 0]):
        with pytest.raises(ValidationError):
            SynthesisClaim(text="claim", citation_indices=indices)

    completed = _completed_result()
    with pytest.raises(ValidationError):
        SynthesisResponse(
            request_id="req",
            status=SynthesisStatus.COMPLETED,
            answer="Different wording.",
            claims=list(completed.claims),
            citations=list(completed.citations),
            guardrail=GuardrailResult(decision=GuardrailDecision.ALLOW),
        )
