from __future__ import annotations

import hashlib

from app.ingestion.normalize import normalize_text


def canonical_document_id(english_passage: str) -> str:
    normalized = normalize_text(english_passage)
    if not normalized:
        raise ValueError("Cannot create a canonical ID for an empty passage")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def stable_id(*parts: str) -> str:
    material = "\x1f".join(parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()

