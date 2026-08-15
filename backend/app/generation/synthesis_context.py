from __future__ import annotations

import asyncio
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass

from app.domain.enums import Language
from app.domain.models import SearchHit


@dataclass(frozen=True, slots=True)
class SynthesisContext:
    request_id: str
    query: str
    language: Language
    evidence: tuple[SearchHit, ...]


@dataclass(frozen=True, slots=True)
class StoredSynthesisContext:
    context: SynthesisContext
    expires_ns: int


class SynthesisContextStore:
    """Bounded, volatile, one-use contexts for optional post-response synthesis."""

    def __init__(self, *, ttl_s: float = 60.0, max_entries: int = 256) -> None:
        if ttl_s <= 0:
            raise ValueError("ttl_s must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._entries: OrderedDict[str, StoredSynthesisContext] = OrderedDict()
        self._lock = asyncio.Lock()

    @property
    def expires_in_ms(self) -> int:
        return int(self.ttl_s * 1_000)

    async def put(self, context: SynthesisContext) -> str:
        now_ns = time.monotonic_ns()
        async with self._lock:
            self._purge_expired(now_ns)
            while len(self._entries) >= self.max_entries:
                self._entries.popitem(last=False)
            token = secrets.token_urlsafe(32)
            while token in self._entries:
                token = secrets.token_urlsafe(32)
            self._entries[token] = StoredSynthesisContext(
                context=context,
                expires_ns=now_ns + int(self.ttl_s * 1_000_000_000),
            )
            return token

    async def take(self, token: str, *, request_id: str) -> SynthesisContext | None:
        """Atomically consume a context so duplicate calls cannot double-bill the provider."""

        now_ns = time.monotonic_ns()
        async with self._lock:
            self._purge_expired(now_ns)
            stored = self._entries.get(token)
            if stored is None or stored.context.request_id != request_id:
                return None
            del self._entries[token]
            return stored.context

    def _purge_expired(self, now_ns: int) -> None:
        expired = [
            token for token, stored in self._entries.items() if stored.expires_ns <= now_ns
        ]
        for token in expired:
            del self._entries[token]
