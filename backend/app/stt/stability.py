from __future__ import annotations

import asyncio
import time
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


def normalize_transcript(text: str) -> str:
    """Normalize Indic/Latin text for stability and edit comparisons."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    characters: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if character.isalnum() or category.startswith("M"):
            characters.append(character)
        else:
            characters.append(" ")
    return " ".join("".join(characters).split())


def normalized_edit_similarity(left: str, right: str) -> float:
    """Return 1 - normalized Levenshtein distance after text normalization."""

    left_normalized = normalize_transcript(left)
    right_normalized = normalize_transcript(right)
    if left_normalized == right_normalized:
        return 1.0
    if not left_normalized or not right_normalized:
        return 0.0
    if len(left_normalized) > len(right_normalized):
        left_normalized, right_normalized = right_normalized, left_normalized

    previous = list(range(len(left_normalized) + 1))
    for row, right_character in enumerate(right_normalized, start=1):
        current = [row]
        for column, left_character in enumerate(left_normalized, start=1):
            insertion = current[column - 1] + 1
            deletion = previous[column] + 1
            substitution = previous[column - 1] + (left_character != right_character)
            current.append(min(insertion, deletion, substitution))
        previous = current
    distance = previous[-1]
    return max(0.0, 1.0 - (distance / max(len(left_normalized), len(right_normalized))))


class TranscriptStabilityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stable_after_ms: int = Field(default=120, ge=0, le=5_000)
    consecutive_events: int = Field(default=2, ge=1, le=20)
    minimum_characters: int = Field(default=3, ge=1, le=1_000)


@dataclass(frozen=True, slots=True)
class StablePartial:
    generation_id: int
    text: str
    normalized_text: str
    first_seen_ns: int
    accepted_ns: int
    consecutive_events: int


class TranscriptStabilityDetector:
    """Debounces revisable provider partials into stable generations."""

    def __init__(self, config: TranscriptStabilityConfig | None = None) -> None:
        self.config = config or TranscriptStabilityConfig()
        self._candidate_text = ""
        self._candidate_normalized = ""
        self._candidate_first_seen_ns = 0
        self._candidate_count = 0
        self._last_emitted_normalized = ""
        self._generation_id = 0

    @property
    def generation_id(self) -> int:
        return self._generation_id

    def observe(self, text: str, *, received_ns: int | None = None) -> StablePartial | None:
        now_ns = received_ns if received_ns is not None else time.perf_counter_ns()
        normalized = normalize_transcript(text)
        if len(normalized) < self.config.minimum_characters:
            self._clear_candidate()
            return None

        if normalized != self._candidate_normalized:
            self._candidate_text = text.strip()
            self._candidate_normalized = normalized
            self._candidate_first_seen_ns = now_ns
            self._candidate_count = 1
        else:
            self._candidate_text = text.strip()
            self._candidate_count += 1

        stable_by_count = self._candidate_count >= self.config.consecutive_events
        elapsed_ns = max(0, now_ns - self._candidate_first_seen_ns)
        stable_by_time = elapsed_ns >= self.config.stable_after_ms * 1_000_000
        if not (stable_by_count or stable_by_time):
            return None
        if normalized == self._last_emitted_normalized:
            return None

        self._generation_id += 1
        self._last_emitted_normalized = normalized
        return StablePartial(
            generation_id=self._generation_id,
            text=self._candidate_text,
            normalized_text=normalized,
            first_seen_ns=self._candidate_first_seen_ns,
            accepted_ns=now_ns,
            consecutive_events=self._candidate_count,
        )

    def reset(self, *, reset_generation: bool = False) -> None:
        """Reset utterance state while keeping IDs monotonic by default."""

        self._clear_candidate()
        self._last_emitted_normalized = ""
        if reset_generation:
            self._generation_id = 0

    def _clear_candidate(self) -> None:
        self._candidate_text = ""
        self._candidate_normalized = ""
        self._candidate_first_seen_ns = 0
        self._candidate_count = 0


class SpeculativeRetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reuse_similarity_threshold: float = Field(default=0.82, ge=0.0, le=1.0)
    wait_for_speculative_ms: int = Field(default=0, ge=0, le=5_000)
    require_exact_normalized_match: bool = True


@dataclass(frozen=True, slots=True)
class RetrievalResolution(Generic[T]):
    final_transcript: str
    value: T
    reused_speculative: bool
    similarity: float
    speculative_generation_id: int | None


class SpeculativeRetrievalController(Generic[T]):
    """Owns one speculative search and prevents stale results from winning."""

    def __init__(self, config: SpeculativeRetrievalConfig | None = None) -> None:
        self.config = config or SpeculativeRetrievalConfig()
        self._lock = asyncio.Lock()
        self._active_generation_id = 0
        self._active_transcript = ""
        self._active_task: asyncio.Task[T] | None = None
        self._cancelled_generations: list[int] = []

    @property
    def active_generation_id(self) -> int:
        return self._active_generation_id

    @property
    def cancelled_generations(self) -> tuple[int, ...]:
        return tuple(self._cancelled_generations)

    async def launch(
        self,
        stable_partial: StablePartial,
        retrieve: Callable[[str], Awaitable[T]],
    ) -> int:
        """Start the newest generation and cancel any older in-flight search."""

        old_task: asyncio.Task[T] | None = None
        old_generation = 0
        async with self._lock:
            if stable_partial.generation_id <= self._active_generation_id:
                return self._active_generation_id
            old_task = self._active_task
            old_generation = self._active_generation_id
            self._active_generation_id = stable_partial.generation_id
            self._active_transcript = stable_partial.text
            self._active_task = asyncio.create_task(
                self._run_retrieval(retrieve, stable_partial.text),
                name=f"speculative-retrieval-{stable_partial.generation_id}",
            )

        if old_task is not None and not old_task.done():
            old_task.cancel()
            if old_generation:
                self._cancelled_generations.append(old_generation)
            old_task.add_done_callback(self._consume_task_result)
        return stable_partial.generation_id

    async def resolve_final(
        self,
        final_transcript: str,
        retrieve_final: Callable[[str], Awaitable[T]],
        *,
        wait_for_speculative_ms: int | None = None,
    ) -> RetrievalResolution[T]:
        """Reuse only a current, sufficiently similar speculative result.

        A partial transcript is never returned as the final query: even on
        reuse, ``final_transcript`` remains the authoritative transcript.
        """

        speculative = await self.resolve_speculative_only(
            final_transcript,
            wait_for_speculative_ms=wait_for_speculative_ms,
        )
        if speculative is not None:
            return speculative

        generation_id = self._active_generation_id
        speculative_text = self._active_transcript
        similarity = (
            normalized_edit_similarity(speculative_text, final_transcript)
            if speculative_text
            else 0.0
        )
        final_value = await retrieve_final(final_transcript)
        return RetrievalResolution(
            final_transcript=final_transcript,
            value=final_value,
            reused_speculative=False,
            similarity=similarity,
            speculative_generation_id=generation_id or None,
        )

    async def resolve_speculative_only(
        self,
        final_transcript: str,
        *,
        wait_for_speculative_ms: int | None = None,
    ) -> RetrievalResolution[T] | None:
        """Return a compatible speculative result without running final retrieval.

        This lets the typed orchestration harness remain the sole owner of final
        retrieval, retries, dependency fallbacks, and deadline handling.
        """

        async with self._lock:
            generation_id = self._active_generation_id
            speculative_text = self._active_transcript
            task = self._active_task

        similarity = (
            normalized_edit_similarity(speculative_text, final_transcript)
            if speculative_text
            else 0.0
        )
        # Character similarity alone is unsafe for factual retrieval: changing
        # one year, negation, or entity in a long question still scores near
        # one. Until a measured semantic compatibility guard is calibrated,
        # production reuse is limited to case/punctuation/spacing-equivalent
        # transcripts. Any lexical change runs retrieval on the final text.
        normalized_compatible = (
            normalize_transcript(speculative_text) == normalize_transcript(final_transcript)
            if self.config.require_exact_normalized_match
            else True
        )
        threshold_met = (
            similarity >= self.config.reuse_similarity_threshold and normalized_compatible
        )
        timeout_ms = (
            self.config.wait_for_speculative_ms
            if wait_for_speculative_ms is None
            else wait_for_speculative_ms
        )

        if threshold_met and task is not None:
            result = await self._result_if_ready(task, timeout_ms)
            async with self._lock:
                still_current = (
                    generation_id == self._active_generation_id and task is self._active_task
                )
                if result[0] and still_current:
                    self._active_task = None
                    self._active_transcript = ""
            if result[0] and still_current:
                return RetrievalResolution(
                    final_transcript=final_transcript,
                    value=cast(T, result[1]),
                    reused_speculative=True,
                    similarity=similarity,
                    speculative_generation_id=generation_id,
                )

        await self._cancel_active(generation_id)
        return None

    @staticmethod
    async def _run_retrieval(
        retrieve: Callable[[str], Awaitable[T]], transcript: str
    ) -> T:
        return await retrieve(transcript)

    async def _result_if_ready(
        self, task: asyncio.Task[T], timeout_ms: int
    ) -> tuple[bool, T | None]:
        if task.cancelled():
            return False, None
        try:
            if task.done():
                return True, task.result()
            if timeout_ms <= 0:
                return False, None
            value = await asyncio.wait_for(asyncio.shield(task), timeout=timeout_ms / 1_000)
            return True, value
        except asyncio.CancelledError:
            if task.cancelled():
                return False, None
            raise
        except (TimeoutError, Exception):
            return False, None

    async def _cancel_active(self, generation_id: int) -> None:
        task: asyncio.Task[T] | None = None
        async with self._lock:
            if generation_id != self._active_generation_id:
                return
            task = self._active_task
            self._active_task = None
        if task is not None and not task.done():
            task.cancel()
            if generation_id:
                self._cancelled_generations.append(generation_id)
            task.add_done_callback(self._consume_task_result)

    @staticmethod
    def _consume_task_result(task: asyncio.Task[T]) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            return

    async def close(self) -> None:
        await self._cancel_active(self._active_generation_id)
