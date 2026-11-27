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

_NEGATION_WORDS: frozenset[str] = frozenset(
    {"not", "no", "never", "isn't", "aren't", "don't", "avoid", "unsafe"}
)
_NEGATION_BIGRAMS: frozenset[tuple[str, str]] = frozenset({("is", "not"), ("do", "not")})

# Pollutant / mask / GRAP stage exempt tokens removed before checking numeric grounding
_EXEMPT_TOKENS_RE = re.compile(
    r"\b(?:PM2\.5|PM10|NO2|SO2|O3|CO2|CO|N95|FFP2|GRAP(?:\s+Stage)?\s+(?:I{1,3}|IV|[1-4])|Stage\s+(?:I{1,3}|IV|[1-4]))\b",
    flags=re.IGNORECASE,
)

# Time ranges and clock expressions:
# Ranges parsed before single times so "4 to 6 pm" checks both 16:00 and 18:00 without leaving "4"
_TIME_12_RANGE_RE = re.compile(
    r"\b(?:between\s+)?(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*(am|pm)?\s*(?:-|–|—|to|and)\s*"
    r"(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*(am|pm)\b",
    flags=re.IGNORECASE,
)
_TIME_24_RANGE_RE = re.compile(
    r"\b(?:between\s+)?([01]?\d|2[0-3])[:.]([0-5]\d)\s*(?:-|–|—|to|and)\s*"
    r"([01]?\d|2[0-3])[:.]([0-5]\d)(?:\s*(am|pm))?\b"
    r"(?!\s*(?:mg|ug|µg|/\s*m|km|cm|kg|%))",
    flags=re.IGNORECASE,
)
# 24h HH:MM (opt am/pm), 24h HH.MM (excl pollutant floats), or 12h H/HH([:.]MM)? am/pm
_TIME_12_RE = re.compile(
    r"\b(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*(am|pm)\b",
    flags=re.IGNORECASE,
)
_TIME_24_COLON_RE = re.compile(
    r"\b([01]?\d|2[0-3]):([0-5]\d)(?:\s*(am|pm))?\b",
    flags=re.IGNORECASE,
)
_TIME_24_DOT_RE = re.compile(
    r"(?<![.\d])([01]?\d|2[0-3])\.([0-5]\d)(?!(?:\.\d|\d))"
    r"(?!\s*(?:mg|ug|µg|/\s*m|km|m\b|cm|kg|g\b|%|aqi))",
    flags=re.IGNORECASE,
)

# Duration expressions: age durations ("30 minutes old", "2 hours ago") vs advice ("for 30 minutes")
_DURATION_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?)\b(?:\s+(old|ago)\b)?",
    flags=re.IGNORECASE,
)
_AGE_PREFIX_WORDS: frozenset[str] = frozenset(
    {"age", "aged", "data", "reading", "observation", "report", "updated", "stale"}
)

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


def _hhmm_to_minutes(hhmm: str) -> int:
    hh, mm = hhmm.split(":")
    return int(hh) * 60 + int(mm)


def _is_permissive_negated(text: str, match_start: int) -> bool:
    prefix = text[:match_start].replace("\u2019", "'").lower()
    words = [w.strip("'") for w in re.findall(r"[a-z0-9']+", prefix) if w.strip("'")]
    window = words[-4:]
    if any(w in _NEGATION_WORDS for w in window):
        return True
    return any((window[i], window[i + 1]) in _NEGATION_BIGRAMS for i in range(len(window) - 1))


def extract_time_expressions(
    text: str,
    *,
    ignore_dot_values: set[str] | None = None,
) -> tuple[set[str], str]:
    """Return normalized HH:MM expressions found in text and text with times stripped."""
    found: set[str] = set()

    def _replace_12_range(match: re.Match[str]) -> str:
        h1 = int(match.group(1))
        m1 = int(match.group(2) or 0)
        mer1 = match.group(3)
        h2 = int(match.group(4))
        m2 = int(match.group(5) or 0)
        mer2 = match.group(6)
        if mer1 is None:
            if mer2.lower() == "pm" and h1 > h2 and h1 != 12:
                mer1 = "am"
            elif mer2.lower() == "am" and h1 > h2 and h1 == 12:
                mer1 = "am"
            else:
                mer1 = mer2
        n1 = _normalise_hhmm(h1, m1, mer1)
        n2 = _normalise_hhmm(h2, m2, mer2)
        if n1 is not None and n2 is not None:
            found.add(n1)
            found.add(n2)
            return " "
        return match.group(0)

    def _replace_24_range(match: re.Match[str]) -> str:
        h1, m1 = int(match.group(1)), int(match.group(2))
        h2, m2 = int(match.group(3)), int(match.group(4))
        mer = match.group(5)
        n1 = _normalise_hhmm(h1, m1, mer if mer and h1 <= 12 else None)
        n2 = _normalise_hhmm(h2, m2, mer if mer and h2 <= 12 else None)
        if n1 is not None and n2 is not None:
            found.add(n1)
            found.add(n2)
            return " "
        return match.group(0)

    def _replace_12(match: re.Match[str]) -> str:
        hh = int(match.group(1))
        mm = int(match.group(2) or 0)
        norm = _normalise_hhmm(hh, mm, match.group(3))
        if norm is not None:
            found.add(norm)
            return " "
        return match.group(0)

    def _replace_24(match: re.Match[str]) -> str:
        if ignore_dot_values and match.group(0) in ignore_dot_values:
            return match.group(0)
        hh = int(match.group(1))
        mm = int(match.group(2))
        norm = _normalise_hhmm(
            hh, mm, match.group(3) if match.lastindex and match.lastindex >= 3 else None
        )
        if norm is not None:
            found.add(norm)
            return " "
        return match.group(0)

    stripped = _TIME_12_RANGE_RE.sub(_replace_12_range, text)
    stripped = _TIME_24_RANGE_RE.sub(_replace_24_range, stripped)
    stripped = _TIME_12_RE.sub(_replace_12, stripped)
    stripped = _TIME_24_COLON_RE.sub(_replace_24, stripped)
    stripped = _TIME_24_DOT_RE.sub(_replace_24, stripped)
    return found, stripped


def _strip_general_advice_durations(text: str, context: AIContext) -> tuple[bool, str]:
    """Check age durations against context.age_* and strip general advice durations."""
    age_mismatch = False

    def _replace_duration(match: re.Match[str]) -> str:
        nonlocal age_mismatch
        val = float(match.group(1))
        unit = match.group(2).lower()
        age_suffix = match.group(3)
        clause_prefix = re.split(r"[,;.!?]", text[: match.start()])[-1]
        prefix_words = re.findall(r"[a-z]+", clause_prefix.lower())[-4:]
        is_age_ref = bool(age_suffix) or any(w in _AGE_PREFIX_WORDS for w in prefix_words)

        if is_age_ref:
            expected = (
                float(context.age_hours)
                if unit.startswith(("h", "hr"))
                else float(context.age_minutes)
            )
            if abs(val - expected) > 1.0 + 1e-9:
                age_mismatch = True
            return " "

        # General advice duration (e.g. "for 30 minutes", "every 2 hours")
        return " "

    cleaned = _DURATION_RE.sub(_replace_duration, text)
    return (not age_mismatch), cleaned


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


def _collect_allowed_times(
    context: AIContext, user_message: str | None
) -> tuple[set[str], list[int]]:
    exact_allowed = {context.local_time, context.observed_time_ist}
    forecast_minutes: list[int] = []
    for pt in context.forecast:
        exact_allowed.add(pt.time_ist)
        forecast_minutes.append(_hhmm_to_minutes(pt.time_ist))
    if user_message:
        user_times, _ = extract_time_expressions(user_message)
        exact_allowed.update(user_times)
    return exact_allowed, forecast_minutes


def _is_time_grounded(
    hhmm: str,
    *,
    exact_allowed: set[str],
    forecast_minutes: list[int],
) -> bool:
    if hhmm in exact_allowed:
        return True
    t_min = _hhmm_to_minutes(hhmm)
    for f_min in forecast_minutes:
        diff = abs(t_min - f_min)
        if min(diff, 1440 - diff) <= 30:
            return True
    return False


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
    ignore_dot_values = {f"{pol.value:.2f}" for pol in context.pollutants.values()}
    exact_allowed_times, forecast_minutes = _collect_allowed_times(context, user_message)

    for text in texts:
        if _BANNED_WORD_RE.search(text) or _BANNED_PHRASE_RE.search(text):
            return False, "GUARD_BANNED_CLAIM"

        if context.verdict.level in POOR_OR_WORSE:
            for match in _PERMISSIVE_PHRASE_RE.finditer(text):
                if not _is_permissive_negated(text, match.start()):
                    return False, "GUARD_PERMISSIVE"

        # Strip exempt tokens first (e.g. PM2.5) and extract grounded clock times/ranges
        without_exempt = _EXEMPT_TOKENS_RE.sub(" ", text)
        found_times, text_without_times = extract_time_expressions(
            without_exempt,
            ignore_dot_values=ignore_dot_values,
        )
        for tm in found_times:
            if not _is_time_grounded(
                tm,
                exact_allowed=exact_allowed_times,
                forecast_minutes=forecast_minutes,
            ):
                return False, "GUARD_TIME"

        durations_ok, cleaned = _strip_general_advice_durations(text_without_times, context)
        if not durations_ok:
            return False, "GUARD_NUMBER"

        for num_str in _NUMBER_RE.findall(cleaned):
            num = float(num_str)
            if not any(abs(num - ctx_num) <= 1.0 + 1e-9 for ctx_num in allowed_numbers):
                return False, "GUARD_NUMBER"

    return True, None
