from __future__ import annotations

from app.core.deadlines import Deadline
from app.domain.models import SearchHit
from app.generation.grounded_generator import GeneratedAnswer, GroundedAnswerGenerator


class OptionalLlamaGenerator:
    """Feature-flagged adapter placeholder; never enabled or benchmarked by default."""

    def __init__(self, delegate: GroundedAnswerGenerator, model_path: str) -> None:
        self.delegate = delegate
        self.model_path = model_path

    async def generate_with_fallback(
        self, query: str, evidence: list[SearchHit], deadline: Deadline
    ) -> GeneratedAnswer:
        # A local model is intentionally not loaded without an explicit measured configuration.
        # The required extractive path remains complete and grounded.
        deadline.check()
        return await self.delegate.generate(query, evidence)

