from __future__ import annotations

import asyncio
import re

import pytest

from app.domain.enums import ChunkStrategy, Language
from app.domain.models import SearchHit
from app.generation.synthesis_context import SynthesisContext, SynthesisContextStore


def _context(request_id: str) -> SynthesisContext:
    text = "Goa became a state in 1987."
    return SynthesisContext(
        request_id=request_id,
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


@pytest.mark.asyncio
async def test_synthesis_context_is_opaque_bound_and_one_use() -> None:
    store = SynthesisContextStore(ttl_s=60, max_entries=2)
    token = await store.put(_context("req-1"))

    assert 32 <= len(token) <= 128
    assert re.fullmatch(r"[A-Za-z0-9_-]+", token)
    assert await store.take(token, request_id="wrong-request") is None
    assert (await store.take(token, request_id="req-1")) is not None
    assert await store.take(token, request_id="req-1") is None


@pytest.mark.asyncio
async def test_synthesis_context_evicts_oldest_and_expires() -> None:
    store = SynthesisContextStore(ttl_s=0.01, max_entries=1)
    first = await store.put(_context("req-1"))
    second = await store.put(_context("req-2"))

    assert await store.take(first, request_id="req-1") is None
    assert (await store.take(second, request_id="req-2")) is not None

    expiring = await store.put(_context("req-3"))
    await asyncio.sleep(0.02)
    assert await store.take(expiring, request_id="req-3") is None


@pytest.mark.asyncio
async def test_synthesis_context_allows_only_one_concurrent_consumer() -> None:
    store = SynthesisContextStore(ttl_s=60, max_entries=2)
    token = await store.put(_context("req"))

    results = await asyncio.gather(
        store.take(token, request_id="req"),
        store.take(token, request_id="req"),
    )

    assert sum(result is not None for result in results) == 1
