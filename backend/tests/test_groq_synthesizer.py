from __future__ import annotations

import json

import httpx
import pytest

from app.domain.enums import ChunkStrategy, Language
from app.domain.models import SearchHit
from app.generation.groq_synthesizer import (
    GroqGroundedSynthesizer,
    GroqGroundingFailed,
    GroqProviderUnavailable,
    GroqRequestTimedOut,
)
from app.generation.synthesis_context import SynthesisContext


def _context(
    language: Language = Language.ENGLISH,
    query: str = "When did Goa become a state?",
) -> SynthesisContext:
    text = "Goa became a state in 1987. It is on India's west coast."
    return SynthesisContext(
        request_id="req-groq",
        query=query,
        language=language,
        evidence=(
            SearchHit(
                canonical_doc_id="doc",
                parent_id="doc",
                chunk_id="chunk",
                text=text,
                parent_text=text,
                language=language,
                strategy=ChunkStrategy.SENTENCE_WINDOW,
                span_start=0,
                span_end=len(text),
                score=0.9,
                dense_score=0.8,
                sparse_score=0.7,
            ),
        ),
    )


def _completion(content: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(content)}}]},
    )


def _synthesizer(transport: httpx.AsyncBaseTransport, *, timeout_s: float = 1) -> tuple[
    GroqGroundedSynthesizer, httpx.AsyncClient
]:
    client = httpx.AsyncClient(
        base_url="https://api.groq.com/openai/v1/",
        transport=transport,
    )
    return (
        GroqGroundedSynthesizer(
            client,
            model="openai/gpt-oss-20b",
            timeout_s=timeout_s,
            max_completion_tokens=384,
            max_concurrency=1,
        ),
        client,
    )


@pytest.mark.asyncio
async def test_groq_synthesis_uses_strict_schema_and_exact_support() -> None:
    observed: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(request.content))
        return _completion(
            {
                "status": "answered",
                "answer": "Goa became a state in 1987.",
                "claims": [
                    {
                        "sentence": "Goa became a state in 1987.",
                        "evidence_ids": ["E1"],
                        "support_quotes": [
                            {
                                "evidence_id": "E1",
                                "quote": "Goa became a state in 1987.",
                            }
                        ],
                    }
                ],
            }
        )

    synthesizer, client = _synthesizer(httpx.MockTransport(handler))
    try:
        result = await synthesizer.synthesize(_context())
    finally:
        await client.aclose()

    assert result.answer == "Goa became a state in 1987."
    assert result.claims[0].citation_indices == [0]
    assert result.citations[0].text.startswith("Goa became")
    assert observed["model"] == "openai/gpt-oss-20b"
    assert observed["temperature"] == 0.0
    assert observed["include_reasoning"] is False
    assert "tools" not in observed
    response_format = observed["response_format"]
    assert isinstance(response_format, dict)
    json_schema = response_format["json_schema"]
    assert isinstance(json_schema, dict)
    assert json_schema["strict"] is True


@pytest.mark.asyncio
async def test_groq_can_truthfully_abstain() -> None:
    synthesizer, client = _synthesizer(
        httpx.MockTransport(
            lambda _request: _completion(
                {"status": "insufficient_evidence", "answer": None, "claims": []}
            )
        )
    )
    try:
        result = await synthesizer.synthesize(_context())
    finally:
        await client.aclose()

    assert result.answer is None
    assert result.claims == ()
    assert result.citations == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        {
            "status": "answered",
            "answer": "Goa became a state in 1987.",
            "claims": [
                {
                    "sentence": "Goa became a state in 1987.",
                    "evidence_ids": ["E9"],
                    "support_quotes": [{"evidence_id": "E9", "quote": "invented secret"}],
                }
            ],
        },
        {
            "status": "answered",
            "answer": "Goa became a state in 1987.",
            "claims": [
                {
                    "sentence": "Goa became a state in 1987.",
                    "evidence_ids": ["E1"],
                    "support_quotes": [{"evidence_id": "E1", "quote": "invented secret"}],
                }
            ],
        },
        {
            "status": "answered",
            "answer": "Goa became a state in 1961.",
            "claims": [
                {
                    "sentence": "Goa became a state in 1961.",
                    "evidence_ids": ["E1"],
                    "support_quotes": [
                        {"evidence_id": "E1", "quote": "Goa became a state in 1987."}
                    ],
                }
            ],
        },
    ],
)
async def test_groq_withholds_unknown_or_unsupported_claims(
    content: dict[str, object],
) -> None:
    synthesizer, client = _synthesizer(
        httpx.MockTransport(lambda _request: _completion(content))
    )
    try:
        with pytest.raises(GroqGroundingFailed) as exc_info:
            await synthesizer.synthesize(_context())
    finally:
        await client.aclose()

    assert "invented secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_groq_timeout_is_bounded() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        await __import__("asyncio").sleep(0.1)
        return _completion({"status": "insufficient_evidence", "answer": None, "claims": []})

    synthesizer, client = _synthesizer(httpx.MockTransport(handler), timeout_s=0.01)
    try:
        with pytest.raises(GroqRequestTimedOut):
            await synthesizer.synthesize(_context())
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,retryable", [(401, False), (429, True), (503, True)])
async def test_groq_http_failures_are_classified(status: int, retryable: bool) -> None:
    synthesizer, client = _synthesizer(
        httpx.MockTransport(lambda _request: httpx.Response(status, json={"error": "secret"}))
    )
    try:
        with pytest.raises(GroqProviderUnavailable) as exc_info:
            await synthesizer.synthesize(_context())
    finally:
        await client.aclose()

    assert exc_info.value.retryable is retryable
    assert "secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_hinglish_prompt_requires_devanagari_with_english_terms() -> None:
    prompt = ""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal prompt
        payload = json.loads(request.content)
        prompt = payload["messages"][0]["content"]
        return _completion({"status": "insufficient_evidence", "answer": None, "claims": []})

    synthesizer, client = _synthesizer(httpx.MockTransport(handler))
    try:
        await synthesizer.synthesize(
            _context(Language.CODE_MIXED, "गोवा state कब बना था?")
        )
    finally:
        await client.aclose()

    assert "Hindi in Devanagari" in prompt
    assert "English terms in Latin script" in prompt


@pytest.mark.asyncio
async def test_roman_hinglish_prompt_preserves_latin_script() -> None:
    prompt = ""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal prompt
        payload = json.loads(request.content)
        prompt = payload["messages"][0]["content"]
        return _completion({"status": "insufficient_evidence", "answer": None, "claims": []})

    synthesizer, client = _synthesizer(httpx.MockTransport(handler))
    try:
        await synthesizer.synthesize(
            _context(Language.CODE_MIXED, "Goa state kab bana tha?")
        )
    finally:
        await client.aclose()

    assert "Roman Hinglish" in prompt
    assert "Latin script" in prompt
