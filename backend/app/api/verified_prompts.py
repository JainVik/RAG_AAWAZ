from __future__ import annotations

import csv
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0.0"
CATALOG_ID = "msmarco-xi-human-voice-v1"
PLAN_STATUS = "recording_plan"
EXPECTED_PROMPT_COUNT = 60
LIVE_VALIDATION_MARKER = "live_completed_allow_2_citations"
PROMPT_PLAN_PATH = (
    Path(__file__).resolve().parents[2]
    / "evaluation"
    / "fixtures"
    / "voice-recording-plan.csv"
)

EXPECTED_COLUMNS = (
    "sequence",
    "session_id",
    "position",
    "raw_session_file",
    "clip_id",
    "target_pcm_path",
    "expected_transcript",
    "language",
    "condition",
    "source_type",
    "length_class",
    "source_query_id",
    "text_validation",
)

PromptLanguage = Literal["hi", "en", "hi-en"]
PromptCondition = Literal["clean-short", "clean-long", "noisy-short", "noisy-long"]
PromptLength = Literal["short", "long"]
PromptSourceType = Literal["human"]

ALLOWED_LANGUAGES: tuple[PromptLanguage, ...] = ("hi", "en", "hi-en")
ALLOWED_CONDITIONS: tuple[PromptCondition, ...] = (
    "clean-short",
    "clean-long",
    "noisy-short",
    "noisy-long",
)
ALLOWED_LENGTHS: tuple[PromptLength, ...] = ("short", "long")
ALLOWED_SOURCE_TYPES: tuple[PromptSourceType, ...] = ("human",)


class PromptCatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VerifiedPrompt(PromptCatalogModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9-]+$")
    text: str = Field(min_length=1, max_length=4_096)
    language: PromptLanguage
    condition: PromptCondition
    length_class: PromptLength
    source_query_id: str = Field(min_length=1, max_length=64, pattern=r"^[1-9][0-9]*$")


class VerifiedPromptCoverage(PromptCatalogModel):
    languages: dict[PromptLanguage, int]
    conditions: dict[PromptCondition, int]
    lengths: dict[PromptLength, int]
    source_types: dict[PromptSourceType, int]


class VerifiedPromptCatalog(PromptCatalogModel):
    schema_version: Literal["1.0.0"]
    catalog_id: Literal["msmarco-xi-human-voice-v1"]
    status: Literal["recording_plan"]
    total: int = Field(ge=0)
    live_text_validated_count: int = Field(ge=0)
    coverage: VerifiedPromptCoverage
    prompts: list[VerifiedPrompt]


class VerifiedPromptCatalogError(PromptCatalogModel):
    schema_version: Literal["1.0.0"]
    catalog_id: Literal["msmarco-xi-human-voice-v1"]
    status: Literal["unavailable"]
    code: Literal["VERIFIED_PROMPT_CATALOG_INVALID"]
    message: str


class PromptCatalogValidationError(ValueError):
    """The checked-in prompt plan failed its public catalog contract."""


def _required_text(row: dict[str | None, str | list[str] | None], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value or value != value.strip():
        raise PromptCatalogValidationError(f"invalid {field}")
    if any(ord(character) < 32 for character in value):
        raise PromptCatalogValidationError(f"control character in {field}")
    return value


def _positive_integer(
    row: dict[str | None, str | list[str] | None], field: str
) -> int:
    value = _required_text(row, field)
    try:
        parsed = int(value)
    except ValueError as exc:
        raise PromptCatalogValidationError(f"invalid integer in {field}") from exc
    if parsed <= 0 or str(parsed) != value:
        raise PromptCatalogValidationError(f"invalid positive integer in {field}")
    return parsed


def _unique(value: object, seen: set[object], field: str) -> None:
    if value in seen:
        raise PromptCatalogValidationError(f"duplicate {field}")
    seen.add(value)


def load_verified_prompt_catalog(path: Path | None = None) -> VerifiedPromptCatalog:
    plan_path = path if path is not None else PROMPT_PLAN_PATH
    with plan_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
            raise PromptCatalogValidationError("unexpected CSV columns")
        rows = list(reader)

    if len(rows) != EXPECTED_PROMPT_COUNT:
        raise PromptCatalogValidationError("unexpected prompt count")

    sequences: set[object] = set()
    prompt_ids: set[object] = set()
    session_positions: set[object] = set()
    target_paths: set[object] = set()
    transcripts: set[object] = set()
    prompts: list[VerifiedPrompt] = []
    language_counts: Counter[str] = Counter()
    condition_counts: Counter[str] = Counter()
    length_counts: Counter[str] = Counter()
    source_type_counts: Counter[str] = Counter()
    live_text_validated_count = 0

    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise PromptCatalogValidationError("malformed CSV row")

        sequence = _positive_integer(row, "sequence")
        position = _positive_integer(row, "position")
        source_query_id = _required_text(row, "source_query_id")
        _positive_integer(row, "source_query_id")
        session_id = _required_text(row, "session_id")
        prompt_id = _required_text(row, "clip_id")
        target_path = _required_text(row, "target_pcm_path")
        transcript = _required_text(row, "expected_transcript")
        language = _required_text(row, "language")
        condition = _required_text(row, "condition")
        length_class = _required_text(row, "length_class")
        source_type = _required_text(row, "source_type")
        validation_marker = _required_text(row, "text_validation")
        _required_text(row, "raw_session_file")

        if language not in ALLOWED_LANGUAGES:
            raise PromptCatalogValidationError("unsupported language")
        if condition not in ALLOWED_CONDITIONS:
            raise PromptCatalogValidationError("unsupported condition")
        if length_class not in ALLOWED_LENGTHS:
            raise PromptCatalogValidationError("unsupported length class")
        if source_type not in ALLOWED_SOURCE_TYPES:
            raise PromptCatalogValidationError("unsupported source type")
        if condition.rsplit("-", maxsplit=1)[-1] != length_class:
            raise PromptCatalogValidationError("condition and length class disagree")
        if validation_marker != LIVE_VALIDATION_MARKER:
            raise PromptCatalogValidationError("prompt lacks required live validation")
        if not re.fullmatch(r"[a-z0-9-]+", prompt_id):
            raise PromptCatalogValidationError("invalid prompt id")

        _unique(sequence, sequences, "sequence")
        _unique(prompt_id, prompt_ids, "prompt id")
        _unique((session_id, position), session_positions, "session position")
        _unique(target_path, target_paths, "target PCM path")
        _unique(transcript, transcripts, "expected transcript")

        language_counts[language] += 1
        condition_counts[condition] += 1
        length_counts[length_class] += 1
        source_type_counts[source_type] += 1
        live_text_validated_count += 1
        prompts.append(
            VerifiedPrompt(
                id=prompt_id,
                text=transcript,
                language=language,
                condition=condition,
                length_class=length_class,
                source_query_id=source_query_id,
            )
        )

    if sequences != set(range(1, EXPECTED_PROMPT_COUNT + 1)):
        raise PromptCatalogValidationError("prompt sequence is not contiguous")

    return VerifiedPromptCatalog(
        schema_version=SCHEMA_VERSION,
        catalog_id=CATALOG_ID,
        status=PLAN_STATUS,
        total=len(prompts),
        live_text_validated_count=live_text_validated_count,
        coverage=VerifiedPromptCoverage(
            languages={key: language_counts[key] for key in ALLOWED_LANGUAGES},
            conditions={key: condition_counts[key] for key in ALLOWED_CONDITIONS},
            lengths={key: length_counts[key] for key in ALLOWED_LENGTHS},
            source_types={key: source_type_counts[key] for key in ALLOWED_SOURCE_TYPES},
        ),
        prompts=prompts,
    )


router = APIRouter(prefix="/v1/prompts", tags=["prompts"])


@router.get(
    "/verified",
    response_model=VerifiedPromptCatalog,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": VerifiedPromptCatalogError}},
)
def verified_prompts() -> VerifiedPromptCatalog | JSONResponse:
    try:
        return load_verified_prompt_catalog()
    except (OSError, UnicodeError, csv.Error, PromptCatalogValidationError) as exc:
        logger.error("Verified prompt catalog is unavailable: %s", exc)
        error = VerifiedPromptCatalogError(
            schema_version=SCHEMA_VERSION,
            catalog_id=CATALOG_ID,
            status="unavailable",
            code="VERIFIED_PROMPT_CATALOG_INVALID",
            message="The verified prompt catalog is unavailable.",
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error.model_dump(mode="json"),
        )
