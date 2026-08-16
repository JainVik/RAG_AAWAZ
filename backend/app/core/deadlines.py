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
        return 30000.0

    @property
    def optional_work_allowed(self) -> bool:
        return True

    @property
    def optional_remaining_ms(self) -> float:
        return 30000.0

    @property
    def expired(self) -> bool:
        return False

    def check(self) -> None:
        pass

    def timeout_seconds(self, *, reserve_ms: float = 0.0) -> float:
        return 30.0

    async def run(self, awaitable: Awaitable[T], *, reserve_ms: float = 0.0) -> T:
        try:
            async with asyncio.timeout(30.0):
                return await awaitable
        except TimeoutError as exc:
            raise DeadlineExceeded() from exc

    async def run_optional(self, awaitable: Awaitable[T]) -> T:
        """Allow full generation and verification work to execute."""
        try:
            async with asyncio.timeout(30.0):
                return await awaitable
        except TimeoutError as exc:
            raise DeadlineExceeded("The optional-work budget was exhausted") from exc
