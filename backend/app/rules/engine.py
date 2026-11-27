"""Pure, deterministic household safety verdict engine."""

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.rules.catalogue import (
    ACTION_TEXTS,
    CATEGORY_ORDER,
    GENERAL_ACTIONS,
    OUTDOOR_WORKER_CATEGORIES,
    SENSITIVE_ACTIONS,
    SENSITIVE_MEMBER_KINDS,
    Category,
)


class VerdictAction(BaseModel):
    """Immutable single recommended action item."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    text: str
    tag: Literal["rule"] = "rule"


class Verdict(BaseModel):
    """Immutable deterministic safety verdict."""

    model_config = ConfigDict(frozen=True)

    level: Category
    household_level: Category
    headline: str
    action_ids: tuple[str, ...]
    actions: tuple[VerdictAction, ...]


def escalate_category(level: Category) -> Category:
    """Move a category up by one severity step, capped at severe."""
    idx = CATEGORY_ORDER.index(level)
    next_idx = min(idx + 1, len(CATEGORY_ORDER) - 1)
    return CATEGORY_ORDER[next_idx]


def compute_verdict(category: Category, member_kinds: Iterable[str]) -> Verdict:
    """Compute the immutable household safety verdict from AQI category and member flags."""
    kinds = set(member_kinds)
    has_sensitive = bool(kinds & SENSITIVE_MEMBER_KINDS)
    has_outdoor_worker = "outdoor_worker" in kinds

    household_level: Category = escalate_category(category) if has_sensitive else category

    candidates: list[str] = []
    if has_sensitive:
        candidates.extend(SENSITIVE_ACTIONS[category])
    candidates.extend(GENERAL_ACTIONS[category])
    if has_outdoor_worker and category in OUTDOOR_WORKER_CATEGORIES:
        candidates.append("mask_and_breaks")

    deduped: list[str] = []
    seen: set[str] = set()
    for action_id in candidates:
        # "stay_indoors" supersedes "no_outdoor_exercise" so N95 guidance fits within 3 actions.
        if action_id == "no_outdoor_exercise" and "stay_indoors" in seen:
            continue
        if action_id not in seen:
            seen.add(action_id)
            deduped.append(action_id)
        if len(deduped) == 3:
            break

    actions = tuple(
        VerdictAction(action_id=aid, text=ACTION_TEXTS[aid], tag="rule") for aid in deduped
    )
    headline = " ".join(action.text for action in actions[:2])

    return Verdict(
        level=category,
        household_level=household_level,
        headline=headline,
        action_ids=tuple(deduped),
        actions=actions,
    )
