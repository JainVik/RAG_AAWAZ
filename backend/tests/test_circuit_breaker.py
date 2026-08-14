from __future__ import annotations

import pytest

from app.core.errors import DependencyUnavailable
from app.harness.circuit_breaker import CircuitBreaker, CircuitState


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_bounded_failures() -> None:
    breaker = CircuitBreaker("qdrant", failure_threshold=2, recovery_timeout_s=100)

    async def fail() -> None:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await breaker.call(fail)
    with pytest.raises(RuntimeError):
        await breaker.call(fail)
    assert breaker.state == CircuitState.OPEN
    with pytest.raises(DependencyUnavailable):
        await breaker.call(fail)


@pytest.mark.asyncio
async def test_circuit_breaker_ignores_non_dependency_failures() -> None:
    breaker = CircuitBreaker(
        "sarvam",
        failure_threshold=1,
        should_count_failure=lambda exc: not isinstance(exc, ValueError),
    )

    async def invalid_client_input() -> None:
        raise ValueError("empty audio")

    with pytest.raises(ValueError):
        await breaker.call(invalid_client_input)

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_session_scoped_breaker_is_not_reset_by_intermediate_successes() -> None:
    breaker = CircuitBreaker(
        "sarvam",
        failure_threshold=3,
        reset_on_call_success=False,
    )

    async def succeed() -> None:
        return None

    async def fail() -> None:
        raise RuntimeError("session finalization failed")

    for expected_count in (1, 2):
        with pytest.raises(RuntimeError):
            await breaker.call(fail)
        await breaker.call(succeed)
        assert breaker.failure_count == expected_count
        assert breaker.state == CircuitState.CLOSED
    with pytest.raises(RuntimeError):
        await breaker.call(fail)
    assert breaker.state == CircuitState.OPEN

    await breaker.record_success()
    assert breaker.failure_count == 0
    assert breaker.state == CircuitState.CLOSED
