from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.enums import ErrorCode, PipelineState


@dataclass(slots=True)
class PipelineError(Exception):
    code: ErrorCode
    message: str
    state: PipelineState = PipelineState.FAILED
    retryable: bool = False
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"


class DeadlineExceeded(PipelineError):
    def __init__(self, message: str = "The request deadline was exceeded") -> None:
        super().__init__(
            code=ErrorCode.DEADLINE_EXCEEDED,
            message=message,
            state=PipelineState.DEADLINE_FALLBACK,
            retryable=False,
        )


class DependencyUnavailable(PipelineError):
    def __init__(self, dependency: str, *, retryable: bool = True) -> None:
        super().__init__(
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            message=f"Required dependency is unavailable: {dependency}",
            state=PipelineState.DEPENDENCY_UNAVAILABLE,
            retryable=retryable,
            details={"dependency": dependency},
        )

