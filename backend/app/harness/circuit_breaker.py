from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

from app.core.errors import DependencyUnavailable

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        dependency: str,
        *,
        failure_threshold: int = 3,
        recovery_timeout_s: float = 10.0,
        should_count_failure: Callable[[Exception], bool] | None = None,
        reset_on_call_success: bool = True,
    ) -> None:
        self.dependency = dependency
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at = 0.0
        self.should_count_failure = should_count_failure or (lambda _exc: True)
        self.reset_on_call_success = reset_on_call_success
        self._lock = asyncio.Lock()

    async def _allow(self) -> None:
        async with self._lock:
            if self.state == CircuitState.OPEN:
                elapsed = time.monotonic() - self.opened_at
                if elapsed < self.recovery_timeout_s:
                    raise DependencyUnavailable(self.dependency)
                self.state = CircuitState.HALF_OPEN

    async def call(self, operation: Callable[[], Awaitable[T]]) -> T:
        await self._allow()
        try:
            result = await operation()
        except Exception as exc:
            await self.record_failure(exc)
            raise
        if self.reset_on_call_success:
            await self.record_success()
        return result

    async def record_success(self) -> None:
        """Reset the failure streak after the dependency's full success boundary."""

        async with self._lock:
            self.failure_count = 0
            self.state = CircuitState.CLOSED

    async def record_failure(self, exc: Exception) -> None:
        """Record a dependency failure observed outside a direct call wrapper."""

        if not self.should_count_failure(exc):
            return
        async with self._lock:
            self.failure_count += 1
            if (
                self.failure_count >= self.failure_threshold
                or self.state == CircuitState.HALF_OPEN
            ):
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()
