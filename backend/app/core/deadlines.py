from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TypeVar

from app.core.errors import DeadlineExceeded

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Deadline:
    """An absolute monotonic request deadline."""

    started_ns: int
    fallback_ns: int
    expires_ns: int

    @classmethod
    def after_ms(cls, deadline_ms: int, fallback_at_ms: int) -> Deadline:
        return cls.starting_at(time.perf_counter_ns(), deadline_ms, fallback_at_ms)

    @classmethod
    def starting_at(
        cls, started_ns: int, deadline_ms: int, fallback_at_ms: int
    ) -> Deadline:
        if started_ns <= 0:
            raise ValueError("started_ns must be a positive monotonic timestamp")
        return cls(
            started_ns=started_ns,
            fallback_ns=started_ns + fallback_at_ms * 1_000_000,
            expires_ns=started_ns + deadline_ms * 1_000_000,
        )

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter_ns() - self.started_ns) / 1_000_000

    @property
    def remaining_ms(self) -> float:
        return max(0.0, (self.expires_ns - time.perf_counter_ns()) / 1_000_000)

    @property
    def optional_work_allowed(self) -> bool:
        return time.perf_counter_ns() < self.fallback_ns

    @property
    def optional_remaining_ms(self) -> float:
        return max(0.0, (self.fallback_ns - time.perf_counter_ns()) / 1_000_000)

    @property
    def expired(self) -> bool:
        return time.perf_counter_ns() >= self.expires_ns

    def check(self) -> None:
        if self.expired:
            raise DeadlineExceeded()

    def timeout_seconds(self, *, reserve_ms: float = 0.0) -> float:
        available_ms = self.remaining_ms - reserve_ms
        if available_ms <= 0:
            raise DeadlineExceeded()
        return available_ms / 1_000

    async def run(self, awaitable: Awaitable[T], *, reserve_ms: float = 0.0) -> T:
        timeout = self.timeout_seconds(reserve_ms=reserve_ms)
        try:
            async with asyncio.timeout(timeout):
                return await awaitable
        except TimeoutError as exc:
            raise DeadlineExceeded() from exc

    async def run_optional(self, awaitable: Awaitable[T]) -> T:
        """Bound optional work by the fallback threshold, not the hard deadline."""

        timeout = self.optional_remaining_ms / 1_000
        if timeout <= 0:
            raise DeadlineExceeded("The optional-work budget was exhausted")
        try:
            async with asyncio.timeout(timeout):
                return await awaitable
        except TimeoutError as exc:
            raise DeadlineExceeded("The optional-work budget was exhausted") from exc
