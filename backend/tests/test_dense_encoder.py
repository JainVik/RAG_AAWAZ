from __future__ import annotations

import asyncio
import threading
from collections.abc import Sequence

import pytest

from app.embeddings.dense import SentenceTransformerDenseEncoder


@pytest.mark.asyncio
async def test_cancelled_threaded_inference_drains_before_replacement_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoder = object.__new__(SentenceTransformerDenseEncoder)
    encoder._inference_lock = asyncio.Lock()
    first_started = threading.Event()
    release_first = threading.Event()
    counts_lock = threading.Lock()
    calls = 0
    active = 0
    maximum_active = 0

    def blocking_encode(texts: Sequence[str], prefix: str) -> list[list[float]]:
        nonlocal calls, active, maximum_active
        del texts, prefix
        with counts_lock:
            calls += 1
            call_number = calls
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            if call_number == 1:
                first_started.set()
                assert release_first.wait(timeout=2.0)
            return [[1.0]]
        finally:
            with counts_lock:
                active -= 1

    monkeypatch.setattr(encoder, "_encode", blocking_encode)
    first = asyncio.create_task(encoder.encode_queries(["partial one"]))
    replacement: asyncio.Task[list[list[float]]] | None = None
    try:
        for _ in range(100):
            if first_started.is_set():
                break
            await asyncio.sleep(0.005)
        assert first_started.is_set()
        first.cancel()
        replacement = asyncio.create_task(encoder.encode_queries(["partial two"]))
        await asyncio.sleep(0.02)

        with counts_lock:
            assert calls == 1
            assert maximum_active == 1
    finally:
        release_first.set()

    with pytest.raises(asyncio.CancelledError):
        await first
    assert replacement is not None
    assert await replacement == [[1.0]]
    with counts_lock:
        assert calls == 2
        assert maximum_active == 1
