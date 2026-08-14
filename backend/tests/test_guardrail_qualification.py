from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from app.domain.enums import GuardrailDecision, GuardrailReason
from scripts import run_guardrail_eval
from scripts._common import load_records

BUNDLED_FIXTURE = (
    Path(__file__).resolve().parents[1] / "evaluation" / "fixtures" / "guardrail-cases.jsonl"
)


def _bound_readiness() -> dict[str, Any]:
    return {
        "index": {"ready": True},
        "qdrant": {"ready": True},
        "thresholds": {
            "ready": True,
            "retrieval_artifacts_bound": True,
        },
    }


def _synthetic_row(record: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    if record.get("kind") == "contradictory_pipeline":
        evidence = {
            "execution_scope": "synthetic_conflict_harness",
            "evidence_mode": "harness_evidence_conflict_gate",
        }
    return {
        "case_id": record["case_id"],
        "correct": True,
        "evidence": evidence,
    }


def _qualifying_cases() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = [
        {
            "case_id": f"required-{index}",
            "kind": "input",
            "category": "required-label-coverage",
            "expected": label,
        }
        for index, label in enumerate(sorted(run_guardrail_eval.REQUIRED_EXPECTED_LABELS))
    ]
    records.extend(
        [
            {
                "case_id": "synthetic-conflict-regression",
                "kind": "contradictory_pipeline",
                "category": "retrieval",
                "expected": GuardrailReason.RETRIEVAL_DISAGREEMENT.value,
            },
            {
                "case_id": "active-supported",
                "kind": "pipeline",
                "category": "supported",
                "expected": GuardrailDecision.ALLOW.value,
            },
            {
                "case_id": "active-unsupported",
                "kind": "pipeline",
                "category": "unsupported",
                "expected": GuardrailReason.NO_RELEVANT_EVIDENCE.value,
            },
            {
                "case_id": "active-contradictory",
                "kind": "pipeline",
                "category": "retrieval",
                "expected": GuardrailReason.RETRIEVAL_DISAGREEMENT.value,
            },
        ]
    )
    rows: list[dict[str, Any]] = []
    for record in records:
        evidence: dict[str, Any] = {}
        if record["case_id"] == "synthetic-conflict-regression":
            evidence = {
                "execution_scope": "synthetic_conflict_harness",
                "evidence_mode": "harness_evidence_conflict_gate",
            }
        elif record.get("kind") == "pipeline":
            evidence = {"execution_scope": "active_retrieval_pipeline"}
        rows.append(
            {
                "case_id": record["case_id"],
                "correct": True,
                "evidence": evidence,
            }
        )
    return records, rows


def test_bundled_synthetic_fixture_stays_nonqualifying_with_fake_readiness() -> None:
    records = load_records(BUNDLED_FIXTURE)
    rows = [_synthetic_row(record) for record in records]

    evidence = run_guardrail_eval._qualification_evidence(
        records,
        rows,
        offline=False,
        readiness_checks=_bound_readiness(),
    )

    assert evidence["qualifying"] is False
    assert evidence["checks"]["frozen_bound_thresholds_ready"] is True
    assert evidence["checks"]["active_index_ready"] is True
    assert evidence["checks"]["qdrant_ready"] is True
    assert evidence["checks"]["synthetic_conflict_gate_regression"] is True
    assert evidence["checks"]["active_pipeline_supported_case"] is False
    assert evidence["checks"]["active_pipeline_unsupported_case"] is False
    assert evidence["checks"]["active_pipeline_contradictory_case"] is False


def test_correct_active_pipeline_categories_with_bound_readiness_can_qualify() -> None:
    records, rows = _qualifying_cases()

    evidence = run_guardrail_eval._qualification_evidence(
        records,
        rows,
        offline=False,
        readiness_checks=_bound_readiness(),
    )

    assert evidence["qualifying"] is True
    assert evidence["status"] == "qualifying"
    assert all(evidence["checks"].values())


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    [
        ("supported_not_active", "active_pipeline_supported_case"),
        ("unsupported_incorrect", "active_pipeline_unsupported_case"),
        ("contradictory_wrong_category", "active_pipeline_contradictory_case"),
        ("thresholds_unbound", "frozen_bound_thresholds_ready"),
        ("index_not_ready", "active_index_ready"),
        ("qdrant_not_ready", "qdrant_ready"),
    ],
)
def test_qualification_requires_each_active_category_and_bound_readiness(
    mutation: str, failed_check: str
) -> None:
    records, rows = _qualifying_cases()
    readiness = _bound_readiness()
    if mutation == "supported_not_active":
        next(row for row in rows if row["case_id"] == "active-supported")["evidence"][
            "execution_scope"
        ] = "synthetic_answerability_gate"
    elif mutation == "unsupported_incorrect":
        next(row for row in rows if row["case_id"] == "active-unsupported")["correct"] = False
    elif mutation == "contradictory_wrong_category":
        next(record for record in records if record["case_id"] == "active-contradictory")[
            "category"
        ] = "unsupported"
    elif mutation == "thresholds_unbound":
        readiness["thresholds"]["retrieval_artifacts_bound"] = False
    elif mutation == "index_not_ready":
        readiness["index"]["ready"] = False
    elif mutation == "qdrant_not_ready":
        readiness["qdrant"]["ready"] = False
    else:  # pragma: no cover - the parameter list is exhaustive
        raise AssertionError(mutation)

    evidence = run_guardrail_eval._qualification_evidence(
        copy.deepcopy(records),
        copy.deepcopy(rows),
        offline=False,
        readiness_checks=readiness,
    )

    assert evidence["qualifying"] is False
    assert evidence["checks"][failed_check] is False
    assert failed_check in evidence["failed_checks"]
