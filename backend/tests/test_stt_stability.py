from __future__ import annotations

import asyncio

import pytest

from app.stt.stability import (
    SpeculativeRetrievalConfig,
    SpeculativeRetrievalController,
    StablePartial,
    TranscriptStabilityConfig,
    TranscriptStabilityDetector,
    normalize_transcript,
    normalized_edit_similarity,
)


def stable(generation_id: int, text: str) -> StablePartial:
    return StablePartial(
        generation_id=generation_id,
        text=text,
        normalized_text=normalize_transcript(text),
        first_seen_ns=1,
        accepted_ns=2,
        consecutive_events=2,
    )


def test_detector_accepts_repeated_partial_and_assigns_generations() -> None:
    detector = TranscriptStabilityDetector(
        TranscriptStabilityConfig(
            stable_after_ms=120,
            consecutive_events=2,
            minimum_characters=3,
        )
    )

    assert detector.observe("गोवा कब", received_ns=0) is None
    first = detector.observe("गोवा कब", received_ns=10_000_000)
    assert first is not None
    assert first.generation_id == 1
    assert detector.observe("गोवा कब!", received_ns=20_000_000) is None

    assert detector.observe("गोवा राज्य कब", received_ns=30_000_000) is None
    second = detector.observe("गोवा राज्य कब", received_ns=40_000_000)
    assert second is not None
    assert second.generation_id == 2


def test_detector_accepts_unchanged_partial_after_interval() -> None:
    detector = TranscriptStabilityDetector(
        TranscriptStabilityConfig(
            stable_after_ms=100,
            consecutive_events=5,
            minimum_characters=1,
        )
    )
    assert detector.observe("hello", received_ns=1_000_000) is None
    result = detector.observe("hello", received_ns=101_000_000)
    assert result is not None
    assert result.consecutive_events == 2


def test_detector_reset_keeps_generation_monotonic() -> None:
    detector = TranscriptStabilityDetector(
        TranscriptStabilityConfig(stable_after_ms=0, consecutive_events=1)
    )
    first = detector.observe("first")
    assert first is not None and first.generation_id == 1
    detector.reset()
    second = detector.observe("second")
    assert second is not None and second.generation_id == 2


def test_normalized_edit_similarity_handles_case_spacing_and_indic_marks() -> None:
    assert normalized_edit_similarity("  GOA, state? ", "goa state") == pytest.approx(1.0)
    assert normalize_transcript("गोवा है") == "गोवा है"
    assert normalized_edit_similarity("गोवा राज्य कब", "मुंबई मौसम") < 0.5


@pytest.mark.asyncio
async def test_new_generation_cancels_older_search() -> None:
    controller: SpeculativeRetrievalController[str] = SpeculativeRetrievalController()
    first_started = asyncio.Event()
    first_cancelled = asyncio.Event()

    async def retrieve(text: str) -> str:
        if text == "first query":
            first_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                first_cancelled.set()
                raise
        return f"result:{text}"

    await controller.launch(stable(1, "first query"), retrieve)
    await first_started.wait()
    await controller.launch(stable(2, "second query"), retrieve)
    await asyncio.sleep(0)

    assert first_cancelled.is_set()
    assert controller.active_generation_id == 2
    assert controller.cancelled_generations == (1,)
    await controller.close()


@pytest.mark.asyncio
async def test_matching_final_reuses_current_speculative_result() -> None:
    controller: SpeculativeRetrievalController[str] = SpeculativeRetrievalController(
        SpeculativeRetrievalConfig(reuse_similarity_threshold=0.8)
    )
    final_calls: list[str] = []

    async def speculative(text: str) -> str:
        return f"candidates:{text}"

    async def final(text: str) -> str:
        final_calls.append(text)
        return f"final:{text}"

    await controller.launch(stable(1, "Goa state when"), speculative)
    await asyncio.sleep(0)
    resolution = await controller.resolve_final("Goa state when?", final)

    assert resolution.reused_speculative
    assert resolution.value == "candidates:Goa state when"
    assert resolution.final_transcript == "Goa state when?"
    assert resolution.similarity == pytest.approx(1.0)
    assert final_calls == []


@pytest.mark.asyncio
async def test_changed_final_cancels_speculation_and_runs_final_retrieval() -> None:
    controller: SpeculativeRetrievalController[str] = SpeculativeRetrievalController(
        SpeculativeRetrievalConfig(reuse_similarity_threshold=0.9)
    )
    speculative_cancelled = asyncio.Event()
    final_calls: list[str] = []

    async def speculative(_: str) -> str:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            speculative_cancelled.set()
            raise

    async def final(text: str) -> str:
        final_calls.append(text)
        return "fresh candidates"

    await controller.launch(stable(1, "Goa population"), speculative)
    await asyncio.sleep(0)
    resolution = await controller.resolve_final("Mumbai weather", final)
    await asyncio.sleep(0)

    assert not resolution.reused_speculative
    assert resolution.value == "fresh candidates"
    assert final_calls == ["Mumbai weather"]
    assert speculative_cancelled.is_set()
    assert controller.cancelled_generations == (1,)


@pytest.mark.asyncio
async def test_high_similarity_year_change_never_reuses_wrong_fact_candidates() -> None:
    controller: SpeculativeRetrievalController[str] = SpeculativeRetrievalController(
        SpeculativeRetrievalConfig(reuse_similarity_threshold=0.8)
    )
    final_calls: list[str] = []

    async def speculative(_: str) -> str:
        return "candidates for 1987"

    async def final(text: str) -> str:
        final_calls.append(text)
        return "candidates for 1967"

    partial = "Which Goa event happened in 1987 according to the passage"
    corrected = "Which Goa event happened in 1967 according to the passage"
    assert normalized_edit_similarity(partial, corrected) > 0.95
    await controller.launch(stable(1, partial), speculative)
    await asyncio.sleep(0)
    resolution = await controller.resolve_final(corrected, final)

    assert resolution.reused_speculative is False
    assert resolution.value == "candidates for 1967"
    assert final_calls == [corrected]


@pytest.mark.asyncio
async def test_pending_matching_speculation_has_bounded_wait_then_falls_back() -> None:
    controller: SpeculativeRetrievalController[str] = SpeculativeRetrievalController(
        SpeculativeRetrievalConfig(reuse_similarity_threshold=0.8, wait_for_speculative_ms=1)
    )

    async def speculative(_: str) -> str:
        await asyncio.Future()
        return "unreachable"

    async def final(_: str) -> str:
        return "final candidates"

    await controller.launch(stable(1, "same query"), speculative)
    resolution = await controller.resolve_final("same query", final)
    assert not resolution.reused_speculative
    assert resolution.value == "final candidates"


@pytest.mark.asyncio
async def test_result_from_cancelled_stale_generation_cannot_win() -> None:
    controller: SpeculativeRetrievalController[str] = SpeculativeRetrievalController(
        SpeculativeRetrievalConfig(reuse_similarity_threshold=0.8, wait_for_speculative_ms=20)
    )
    stale_started = asyncio.Event()
    release_stale = asyncio.Event()

    async def retrieve(text: str) -> str:
        if text == "old query":
            stale_started.set()
            try:
                await release_stale.wait()
            except asyncio.CancelledError:
                # Simulate a dependency that cannot actually cancel its request.
                await release_stale.wait()
            return "stale candidates"
        return "current candidates"

    async def final(_: str) -> str:
        return "unexpected final retrieval"

    await controller.launch(stable(1, "old query"), retrieve)
    await stale_started.wait()
    await controller.launch(stable(2, "current query"), retrieve)
    release_stale.set()
    await asyncio.sleep(0)
    resolution = await controller.resolve_final("current query", final)

    assert resolution.reused_speculative
    assert resolution.speculative_generation_id == 2
    assert resolution.value == "current candidates"
