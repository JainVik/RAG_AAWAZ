from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Span:
    name: str
    started_ns: int
    ended_ns: int

    @property
    def duration_ms(self) -> float:
        return (self.ended_ns - self.started_ns) / 1_000_000


@contextmanager
def measure_span(name: str) -> Iterator[list[Span]]:
    result: list[Span] = []
    started = time.perf_counter_ns()
    try:
        yield result
    finally:
        result.append(Span(name=name, started_ns=started, ended_ns=time.perf_counter_ns()))

