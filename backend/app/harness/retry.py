from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from app.core.deadlines import Deadline

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 2
    initial_backoff_ms: float = 5.0
    backoff_multiplier: float = 2.0
    minimum_remaining_ms: float = 30.0


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    deadline: Deadline,
    policy: RetryPolicy,
    is_retryable: Callable[[Exception], bool],
) -> T:
    backoff = policy.initial_backoff_ms
    last_error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        deadline.check()
        try:
            return await operation()
        except Exception as exc:
            last_error = exc
            if (
                attempt >= policy.max_attempts
                or not is_retryable(exc)
                or deadline.remaining_ms < policy.minimum_remaining_ms + backoff
            ):
                raise
            await asyncio.sleep(backoff / 1_000)
            backoff *= policy.backoff_multiplier
    assert last_error is not None
    raise last_error

