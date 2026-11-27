"""Unit tests for deterministic rules engine and GRAP loader."""

import json
import logging
from pathlib import Path

import pytest
from app.rules.catalogue import (
    ACTION_TEXTS,
    CATEGORY_ORDER,
    GENERAL_ACTIONS,
    SENSITIVE_ACTIONS,
    Category,
)
from app.rules.engine import compute_verdict
from app.rules.grap import resolve_grap
from pydantic import ValidationError


@pytest.mark.parametrize("category", CATEGORY_ORDER)
@pytest.mark.parametrize("sensitive", [None, "child_u12", "adult_65p", "heart_lung"])
@pytest.mark.parametrize("worker", [None, "outdoor_worker"])
def test_verdict_matrix_all_categories_and_member_flags(
    category: Category,
    sensitive: str | None,
    worker: str | None,
) -> None:
    members = ["adult"]
    if sensitive:
        members.append(sensitive)
    if worker:
        members.append(worker)

    verdict = compute_verdict(category, members)
    assert verdict.level == category

    idx = CATEGORY_ORDER.index(category)
    expected_household = (
        CATEGORY_ORDER[min(idx + 1, len(CATEGORY_ORDER) - 1)] if sensitive else category
    )
    assert verdict.household_level == expected_household
    assert 1 <= len(verdict.action_ids) <= 3
    assert len(verdict.action_ids) == len(set(verdict.action_ids))
    assert len(verdict.actions) == len(verdict.action_ids)

    expected_first = SENSITIVE_ACTIONS[category][0] if sensitive else GENERAL_ACTIONS[category][0]
    assert verdict.action_ids[0] == expected_first

    expected_headline = " ".join(ACTION_TEXTS[aid] for aid in verdict.action_ids[:2])
    assert verdict.headline == expected_headline

    if worker and category in {"poor", "very_poor", "severe"}:
        if not sensitive and category in {"poor", "very_poor", "severe"}:
            assert "mask_and_breaks" in verdict.action_ids


def test_documented_example_aqi_312_with_child() -> None:
    verdict = compute_verdict("very_poor", ["child_u12"])
    assert verdict.level == "very_poor"
    assert verdict.household_level == "severe"
    assert verdict.action_ids == ("stay_indoors", "purifier_on", "n95_if_out")
    assert verdict.headline == "Stay indoors today. Run the purifier."
    assert [a.model_dump() for a in verdict.actions] == [
        {"action_id": "stay_indoors", "text": "Stay indoors today.", "tag": "rule"},
        {"action_id": "purifier_on", "text": "Run the purifier.", "tag": "rule"},
        {
            "action_id": "n95_if_out",
            "text": "Wear a well-fitted N95 if you go out.",
            "tag": "rule",
        },
    ]


def test_verdict_is_immutable() -> None:
    verdict = compute_verdict("moderate", ["adult"])
    with pytest.raises(ValidationError):
        verdict.level = "good"  # type: ignore[misc]


def test_grap_resolution_and_invalid_config(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    noida = resolve_grap("Noida")
    assert noida is not None
    assert noida.stage == "II"
    assert noida.order_date == "2026-11-02"
    assert noida.source_url == "https://caqm.nic.in/"

    assert resolve_grap("Prayagraj") is None
    assert resolve_grap(None) is None

    bad_file = tmp_path / "grap.json"
    bad_file.write_text("{not-valid-json", encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="purvai"):
        assert resolve_grap("Noida", config_path=bad_file) is None
    assert any("grap_config_invalid" in rec.message for rec in caplog.records)

    missing_file = tmp_path / "missing_grap.json"
    assert resolve_grap("Noida", config_path=missing_file) is None

    # Valid custom file round-trip
    valid_file = tmp_path / "valid_grap.json"
    valid_file.write_text(
        json.dumps(
            {
                "region": "Delhi-NCR",
                "stage": "III",
                "order_date": "2026-11-06",
                "source_url": "https://caqm.nic.in/",
                "cities": ["Delhi", "Noida"],
            }
        ),
        encoding="utf-8",
    )
    custom = resolve_grap("delhi", config_path=valid_file)
    assert custom is not None and custom.stage == "III"
