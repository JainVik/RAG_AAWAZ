from __future__ import annotations

import math
import threading
from collections import Counter, deque
from collections.abc import Sequence
from typing import Any

from app.domain.models import QueryResponse, VoiceErrorPayload


def nearest_rank_percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        raise ValueError("Cannot calculate a percentile for an empty sequence")
    if not 0 < percentile <= 100:
        raise ValueError("percentile must be in (0, 100]")
    ordered = sorted(values)
    if percentile == 100:
        return ordered[-1]
    rank = max(1, math.ceil(percentile / 100 * len(ordered)))
    return ordered[rank - 1]


class MetricsRecorder:
    """Bounded process-local metrics. No query, transcript, audio, or secret is retained."""

    def __init__(self, max_latency_samples: int = 10_000) -> None:
        self._lock = threading.Lock()
        self._requests = 0
        self._states: Counter[str] = Counter()
        self._guardrail_reasons: Counter[str] = Counter()
        self._error_codes: Counter[str] = Counter()
        self._latencies: deque[float] = deque(maxlen=max_latency_samples)
        self._timings: dict[str, deque[float]] = {}
        self._max_latency_samples = max_latency_samples
        self._speculative_started = 0
        self._speculative_reused = 0

    def record_response(self, response: QueryResponse) -> None:
        with self._lock:
            self._requests += 1
            self._states[response.state.value] += 1
            if response.guardrail.reason is not None:
                self._guardrail_reasons[response.guardrail.reason.value] += 1
            self._record_timings(response.timings_ms)

    def record_error(self, error: VoiceErrorPayload) -> None:
        with self._lock:
            self._requests += 1
            self._states[error.state.value] += 1
            self._error_codes[error.code.value] += 1
            self._record_timings(error.timings_ms)

    def _record_timings(self, timings: dict[str, float]) -> None:
        total = timings.get("total_after_final_audio")
        if total is not None and math.isfinite(total) and total >= 0:
            self._latencies.append(total)
        for name, value in timings.items():
            if not math.isfinite(value) or value < 0:
                continue
            samples = self._timings.setdefault(
                name, deque(maxlen=self._max_latency_samples)
            )
            samples.append(value)

    def record_speculative(self, *, reused: bool) -> None:
        with self._lock:
            self._speculative_started += 1
            if reused:
                self._speculative_reused += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latencies = list(self._latencies)
            snapshot: dict[str, Any] = {
                "requests_total": self._requests,
                "states": dict(self._states),
                "guardrail_reasons": dict(self._guardrail_reasons),
                "error_codes": dict(self._error_codes),
                "latency_sample_count": len(latencies),
                "speculative_retrieval": {
                    "started": self._speculative_started,
                    "reused": self._speculative_reused,
                    "reuse_rate": (
                        self._speculative_reused / self._speculative_started
                        if self._speculative_started
                        else 0.0
                    ),
                },
            }
            if latencies:
                snapshot["latency_ms"] = {
                    "p50": nearest_rank_percentile(latencies, 50),
                    "p70": nearest_rank_percentile(latencies, 70),
                    "p95": nearest_rank_percentile(latencies, 95),
                    "p100": max(latencies),
                }
            snapshot["timings_ms"] = {
                name: {
                    "count": len(values),
                    "p50": nearest_rank_percentile(values, 50),
                    "p70": nearest_rank_percentile(values, 70),
                    "p95": nearest_rank_percentile(values, 95),
                    "p100": max(values),
                }
                for name, samples in sorted(self._timings.items())
                if (values := list(samples))
            }
            return snapshot


metrics_recorder = MetricsRecorder()
