from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import verified_prompts
from app.main import create_app


class MinimalServices:
    orchestrator = None
    stt_factory = None
    settings = SimpleNamespace(rag_deadline_ms=500, rag_fallback_at_ms=450)

    async def readiness(self) -> dict[str, Any]:
        return {"status": "not_ready", "checks": {}}

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None


def _read_plan() -> tuple[list[str], list[dict[str, str]]]:
    with verified_prompts.PROMPT_PLAN_PATH.open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def _write_plan(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_verified_prompt_endpoint_exposes_only_public_recording_plan_fields() -> None:
    with TestClient(create_app(MinimalServices())) as client:
        response = client.get("/v1/prompts/verified")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "schema_version",
        "catalog_id",
        "status",
        "total",
        "live_text_validated_count",
        "coverage",
        "prompts",
    }
    assert payload["schema_version"] == "1.0.0"
    assert payload["catalog_id"] == "msmarco-xi-human-voice-v1"
    assert payload["status"] == "recording_plan"
    assert payload["total"] == 60
    assert payload["live_text_validated_count"] == 60
    assert payload["coverage"] == {
        "languages": {"hi": 20, "en": 20, "hi-en": 20},
        "conditions": {
            "clean-short": 15,
            "clean-long": 15,
            "noisy-short": 15,
            "noisy-long": 15,
        },
        "lengths": {"short": 30, "long": 30},
        "source_types": {"human": 60},
    }
    assert len(payload["prompts"]) == 60
    assert set(payload["prompts"][0]) == {
        "id",
        "text",
        "language",
        "condition",
        "length_class",
        "source_query_id",
    }
    assert isinstance(payload["prompts"][0]["source_query_id"], str)
    serialized = response.text
    for private_field in (
        "sequence",
        "session_id",
        "raw_session_file",
        "target_pcm_path",
        "text_validation",
    ):
        assert private_field not in serialized


Mutation = Callable[[list[str], list[dict[str, str]]], None]


def _remove_column(headers: list[str], rows: list[dict[str, str]]) -> None:
    headers.remove("text_validation")
    for row in rows:
        row.pop("text_validation")


def _duplicate_id(_headers: list[str], rows: list[dict[str, str]]) -> None:
    rows[1]["clip_id"] = rows[0]["clip_id"]


def _unsupported_language(_headers: list[str], rows: list[dict[str, str]]) -> None:
    rows[0]["language"] = "fr"


def _remove_live_marker(_headers: list[str], rows: list[dict[str, str]]) -> None:
    rows[0]["text_validation"] = "not_live_validated"


@pytest.mark.parametrize(
    "mutation",
    [_remove_column, _duplicate_id, _unsupported_language, _remove_live_marker],
    ids=["exact-columns", "unique-ids", "allowed-values", "live-validation"],
)
def test_verified_prompt_loader_rejects_invalid_plans(
    tmp_path: Path, mutation: Mutation
) -> None:
    headers, rows = _read_plan()
    mutation(headers, rows)
    path = tmp_path / "invalid-plan.csv"
    _write_plan(path, headers, rows)

    with pytest.raises(verified_prompts.PromptCatalogValidationError):
        verified_prompts.load_verified_prompt_catalog(path)


def test_verified_prompt_endpoint_fails_closed_without_leaking_plan_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    invalid_path = tmp_path / "missing-plan.csv"
    monkeypatch.setattr(verified_prompts, "PROMPT_PLAN_PATH", invalid_path)

    with TestClient(create_app(MinimalServices())) as client:
        response = client.get("/v1/prompts/verified")

    assert response.status_code == 503
    assert response.json() == {
        "schema_version": "1.0.0",
        "catalog_id": "msmarco-xi-human-voice-v1",
        "status": "unavailable",
        "code": "VERIFIED_PROMPT_CATALOG_INVALID",
        "message": "The verified prompt catalog is unavailable.",
    }
