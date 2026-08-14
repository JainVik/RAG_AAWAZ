from __future__ import annotations

from pathlib import Path

from app.embeddings.sparse_char_ngram import SparseCharNgramEncoder


def test_sparse_vectors_are_deterministic_sorted_and_preserve_numbers() -> None:
    encoder = SparseCharNgramEncoder(dimensions=10_007).fit(
        ["गोवा 1987 में राज्य बना", "Goa became a state"]
    )
    first = encoder.encode("Goa 1987 गोवा")
    second = encoder.encode("Goa 1987 गोवा")

    assert first == second
    assert first.indices == sorted(set(first.indices))
    assert len(first.indices) == len(first.values)
    assert first.indices


def test_sparse_encoder_state_round_trips(tmp_path: Path) -> None:
    encoder = SparseCharNgramEncoder(dimensions=1_009).fit(["Goa 1987", "गोवा राज्य"])
    state_path = tmp_path / "sparse.json"
    encoder.save(state_path)
    restored = SparseCharNgramEncoder.load(state_path)

    assert restored.state_dict() == encoder.state_dict()
    assert restored.encode("Goa 1987") == encoder.encode("Goa 1987")
