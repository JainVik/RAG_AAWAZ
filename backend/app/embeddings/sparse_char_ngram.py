from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.domain.models import SparseVector
from app.ingestion.normalize import normalize_for_matching

_EXACT_TOKEN = re.compile(r"\b\d+(?:[./:-]\d+)*\b")


class SparseCharNgramEncoder:
    """Deterministic character 3–5 gram TF-IDF encoder for Qdrant sparse vectors."""

    def __init__(self, dimensions: int = 1 << 20, min_n: int = 3, max_n: int = 5) -> None:
        self.dimensions = dimensions
        self.min_n = min_n
        self.max_n = max_n
        self.document_count = 0
        self.document_frequency: Counter[int] = Counter()

    def _hash(self, feature: str) -> int:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self.dimensions

    def features(self, text: str) -> set[int]:
        normalized = normalize_for_matching(text)
        padded = f" {normalized} "
        result: set[int] = set()
        for size in range(self.min_n, self.max_n + 1):
            for index in range(max(0, len(padded) - size + 1)):
                gram = padded[index : index + size]
                if gram.strip():
                    result.add(self._hash(f"c{size}:{gram}"))
        for token in _EXACT_TOKEN.findall(normalized):
            result.add(self._hash(f"exact:{token}"))
        return result

    def fit(self, documents: Iterable[str]) -> SparseCharNgramEncoder:
        self.document_count = 0
        self.document_frequency.clear()
        for text in documents:
            self.document_count += 1
            self.document_frequency.update(self.features(text))
        return self

    def encode(self, text: str) -> SparseVector:
        normalized = normalize_for_matching(text)
        padded = f" {normalized} "
        counts: Counter[int] = Counter()
        for size in range(self.min_n, self.max_n + 1):
            for index in range(max(0, len(padded) - size + 1)):
                gram = padded[index : index + size]
                if gram.strip():
                    counts[self._hash(f"c{size}:{gram}")] += 1
        for token in _EXACT_TOKEN.findall(normalized):
            counts[self._hash(f"exact:{token}")] += 2

        weighted: dict[int, float] = {}
        for feature, count in counts.items():
            tf = 1.0 + math.log(count)
            df = self.document_frequency.get(feature, 0)
            idf = math.log((self.document_count + 1) / (df + 1)) + 1.0
            weighted[feature] = tf * idf
        norm = math.sqrt(sum(value * value for value in weighted.values())) or 1.0
        indices = sorted(weighted)
        return SparseVector(
            indices=indices,
            values=[weighted[index] / norm for index in indices],
        )

    def state_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "dimensions": self.dimensions,
            "min_n": self.min_n,
            "max_n": self.max_n,
            "document_count": self.document_count,
            "document_frequency": [
                [index, self.document_frequency[index]]
                for index in sorted(self.document_frequency)
            ],
        }

    @classmethod
    def from_state_dict(cls, state: dict[str, Any]) -> SparseCharNgramEncoder:
        if state.get("schema_version") != 1:
            raise ValueError("Unsupported sparse encoder schema version")
        encoder = cls(
            dimensions=int(state["dimensions"]),
            min_n=int(state["min_n"]),
            max_n=int(state["max_n"]),
        )
        encoder.document_count = int(state["document_count"])
        pairs = state.get("document_frequency", [])
        encoder.document_frequency = Counter(
            {int(index): int(count) for index, count in pairs}
        )
        return encoder

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            self.state_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    @classmethod
    def load(cls, path: Path) -> SparseCharNgramEncoder:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("Sparse encoder state must be a JSON object")
        return cls.from_state_dict(state)
