from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from app.core.deadlines import Deadline
from app.domain.enums import ErrorCode, PipelineState
from app.domain.models import StageTiming


@dataclass(slots=True)
class PipelineContext:
    request_id: str
    deadline: Deadline
    state: PipelineState
    history: list[PipelineState] = field(default_factory=list)
    stage_timings: list[StageTiming] = field(default_factory=list)
    _active_state: PipelineState | None = field(default=None, init=False, repr=False)
    _active_started_ns: int | None = field(default=None, init=False, repr=False)

    def transition(self, state: PipelineState) -> None:
        self.state = state
        self.history.append(state)

    @asynccontextmanager
    async def stage(self, state: PipelineState) -> AsyncIterator[None]:
        self.deadline.check()
        self.transition(state)
        started = time.perf_counter_ns()
        self._active_state = state
        self._active_started_ns = started
        try:
            yield
        except BaseException as exc:
            ended = time.perf_counter_ns()
            code = getattr(exc, "code", ErrorCode.INTERNAL_ERROR)
            self.stage_timings.append(
                StageTiming(
                    state=state,
                    started_ns=started,
                    ended_ns=ended,
                    duration_ms=(ended - started) / 1_000_000,
                    outcome="cancelled" if isinstance(exc, GeneratorExit) else "error",
                    error_code=code,
                )
            )
            raise
        else:
            ended = time.perf_counter_ns()
            self.stage_timings.append(
                StageTiming(
                    state=state,
                    started_ns=started,
                    ended_ns=ended,
                    duration_ms=(ended - started) / 1_000_000,
                )
            )
        finally:
            self._active_state = None
            self._active_started_ns = None

    def timing_map(self) -> dict[str, float]:
        result = {item.state.value.lower(): item.duration_ms for item in self.stage_timings}
        if self._active_state is not None and self._active_started_ns is not None:
            result[self._active_state.value.lower()] = (
                time.perf_counter_ns() - self._active_started_ns
            ) / 1_000_000
        result["total_after_final_audio"] = self.deadline.elapsed_ms
        return result
