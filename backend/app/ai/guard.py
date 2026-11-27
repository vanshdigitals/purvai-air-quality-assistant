"""Deterministic post-validation AI safety guard (docs/AI_SAFETY.md)."""

import re
from typing import cast

from pydantic import BaseModel

from app.ai.schemas.v1.models import (
    AIContext,
    ChatReply,
    DailyPlanWording,
    IndoorAdvice,
)
from app.rules.catalogue import Category

BANNED_SINGLE_WORDS: tuple[str, ...] = (
    "cure",
    "cures",
    "cured",
    "dosage",
    "dose",
    "mg",
    "prescribe",
    "prescription",
    "diagnose",
    "diagnosis",
)

BANNED_PHRASES: tuple[str, ...] = (
    "makes the air safe",
    "make the air safe",
    "air is safe",
    "completely safe",
    "100% safe",
    "fully protects",
    "guaranteed",
)

PERMISSIVE_PHRASES: tuple[str, ...] = (
    "safe to go out",
    "safe to play outside",
    "fine to go out",
    "okay to go out",
    "ok to go out",
    "no need for a mask",
    "no mask needed",
)

POOR_OR_WORSE: frozenset[Category] = frozenset({"poor", "very_poor", "severe"})

_BANNED_WORD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in BANNED_SINGLE_WORDS) + r")\b",
    flags=re.IGNORECASE,
)
_BANNED_PHRASE_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(p) for p in BANNED_PHRASES) + r")(?!\w)",
    flags=re.IGNORECASE,
)
_PERMISSIVE_PHRASE_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(p) for p in PERMISSIVE_PHRASES) + r")(?!\w)",
    flags=re.IGNORECASE,
)

# Pollutant / mask / GRAP stage exempt tokens removed before checking numeric grounding
_EXEMPT_TOKENS_RE = re.compile(
    r"\b(?:PM2\.5|PM10|NO2|SO2|O3|CO2|CO|N95|FFP2|GRAP(?:\s+Stage)?\s+(?:I{1,3}|IV|[1-4])|Stage\s+(?:I{1,3}|IV|[1-4]))\b",
    flags=re.IGNORECASE,
)

# 24h HH:MM (with optional am/pm) or H/HH(:MM)? am/pm
_TIME_24_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)(?:\s*(am|pm))?\b", flags=re.IGNORECASE)
_TIME_12_RE = re.compile(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(am|pm)\b", flags=re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")

_GRAP_ROMAN_TO_NUM = {"I": 1.0, "II": 2.0, "III": 3.0, "IV": 4.0}


def _normalise_hhmm(hour: int, minute: int, meridiem: str | None) -> str | None:
    if meridiem:
        mer = meridiem.lower()
        if not (1 <= hour <= 12):
            return None
        if mer == "am":
            hour = 0 if hour == 12 else hour
        elif mer == "pm":
            hour = 12 if hour == 12 else hour + 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def extract_time_expressions(text: str) -> tuple[set[str], str]:
    """Return normalized HH:MM expressions found in text and text with times stripped."""
    found: set[str] = set()

    def _replace_12(match: re.Match[str]) -> str:
        hh = int(match.group(1))
        mm = int(match.group(2) or 0)
        norm = _normalise_hhmm(hh, mm, match.group(3))
        if norm is not None:
            found.add(norm)
            return " "
        return match.group(0)

    def _replace_24(match: re.Match[str]) -> str:
        hh = int(match.group(1))
        mm = int(match.group(2))
        norm = _normalise_hhmm(hh, mm, match.group(3))
        if norm is not None:
            found.add(norm)
            return " "
        return match.group(0)

    # Run 12h first when am/pm is present, then 24h HH:MM
    stripped = _TIME_12_RE.sub(_replace_12, text)
    stripped = _TIME_24_RE.sub(_replace_24, stripped)
    return found, stripped


def _collect_text_fields(reply: BaseModel) -> list[str]:
    if isinstance(reply, ChatReply):
        texts = [reply.answer]
        for rec in reply.recommendations:
            texts.extend((rec.title, rec.why))
        return texts
    if isinstance(reply, DailyPlanWording):
        texts = [reply.summary]
        for period in reply.periods:
            for item in period.items:
                texts.extend((item.title, item.why))
        return texts
    if isinstance(reply, IndoorAdvice):
        texts = [tip.text for tip in reply.tips]
        if reply.ach_explanation is not None:
            texts.append(reply.ach_explanation)
        return texts
    return []


def _collect_allowed_numbers(context: AIContext) -> list[float]:
    allowed: list[float] = [
        float(context.aqi),
        float(context.age_minutes),
        float(context.age_hours),
    ]
    for pol in context.pollutants.values():
        allowed.append(float(pol.value))
        allowed.append(float(pol.sub_index))
    for pt in context.forecast:
        allowed.append(float(pt.aqi))
    if context.plan_periods:
        for p in context.plan_periods:
            allowed.append(float(p.aqi))
    if context.grap_stage and context.grap_stage.upper() in _GRAP_ROMAN_TO_NUM:
        allowed.append(_GRAP_ROMAN_TO_NUM[context.grap_stage.upper()])
    return allowed


def _collect_allowed_times(context: AIContext, user_message: str | None) -> set[str]:
    allowed = {context.local_time, context.observed_time_ist}
    for pt in context.forecast:
        allowed.add(pt.time_ist)
    if user_message:
        user_times, _ = extract_time_expressions(user_message)
        allowed.update(user_times)
    return allowed


def validate_ai_reply(
    reply: BaseModel,
    context: AIContext,
    *,
    user_message: str | None = None,
    allowed_tip_ids: set[str] | None = None,
) -> tuple[bool, str | None]:
    """Check reply against SAF-01..05 guard rules; return (True, None) or (False, CODE)."""
    verdict_level = cast(Category | None, getattr(reply, "verdict_level", None))
    if verdict_level != context.verdict.level:
        return False, "GUARD_VERDICT"

    if isinstance(reply, ChatReply):
        allowed_actions = set(context.verdict.action_ids)
        for rec in reply.recommendations:
            if rec.action_id not in allowed_actions:
                return False, "GUARD_ACTION_ID"

    elif isinstance(reply, DailyPlanWording):
        if context.plan_periods is None:
            return False, "GUARD_PLAN_PERIODS"
        expected_map = {p.period: list(p.action_ids) for p in context.plan_periods}
        returned_periods = [p.period for p in reply.periods]
        if set(returned_periods) != set(expected_map.keys()) or len(returned_periods) != 4:
            return False, "GUARD_PLAN_PERIODS"
        for p in reply.periods:
            if [item.action_id for item in p.items] != expected_map[p.period]:
                return False, "GUARD_ACTION_ID"

    elif isinstance(reply, IndoorAdvice):
        if allowed_tip_ids is not None:
            for tip in reply.tips:
                if tip.tip_id not in allowed_tip_ids:
                    return False, "GUARD_TIP_ID"

    texts = _collect_text_fields(reply)
    allowed_numbers = _collect_allowed_numbers(context)
    allowed_times = _collect_allowed_times(context, user_message)

    for text in texts:
        if _BANNED_WORD_RE.search(text) or _BANNED_PHRASE_RE.search(text):
            return False, "GUARD_BANNED_CLAIM"

        if context.verdict.level in POOR_OR_WORSE and _PERMISSIVE_PHRASE_RE.search(text):
            return False, "GUARD_PERMISSIVE"

        found_times, text_without_times = extract_time_expressions(text)
        for tm in found_times:
            if tm not in allowed_times:
                return False, "GUARD_TIME"

        cleaned = _EXEMPT_TOKENS_RE.sub(" ", text_without_times)
        for num_str in _NUMBER_RE.findall(cleaned):
            num = float(num_str)
            if not any(abs(num - ctx_num) <= 1.0 + 1e-9 for ctx_num in allowed_numbers):
                return False, "GUARD_NUMBER"

    return True, None
