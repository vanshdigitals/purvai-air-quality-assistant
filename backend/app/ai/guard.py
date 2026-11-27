"""Deterministic post-validation AI safety guard (docs/AI_SAFETY.md)."""

import re
import unicodedata
from typing import cast

from pydantic import BaseModel

from app.ai.schemas.v1.models import (
    AIContext,
    ChatReply,
    DailyPlanWording,
    IndoorAdvice,
)
from app.rules.catalogue import Category

_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")


def normalise_guard_text(text: str) -> str:
    """Apply NFKC, strip zero-width chars, collapse whitespace, and lowercase for matching."""
    nfkc = unicodedata.normalize("NFKC", text)
    no_zw = _ZERO_WIDTH_RE.sub("", nfkc)
    collapsed = re.sub(r"\s+", " ", no_zw).strip()
    return collapsed.lower()


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
    "paracetamol",
    "antihistamine",
    "antibiotic",
    "steroid",
    "salbutamol",
    "montelukast",
    "cetirizine",
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
_BANNED_DOSE_UNIT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|ml|mcg|g\b|puffs?)\b",
    flags=re.IGNORECASE,
)
_MEDICINE_INSTRUCT_RE = re.compile(
    r"\b(?:take|give|use|start|increase|double)\b"
    r"(?:\s+[^.!?\s]+){0,4}?\s+"
    r"\b(?:medicine|medication|tablet|inhaler|dose|puff|syrup)s?\b",
    flags=re.IGNORECASE,
)

# Permissive patterns (A2)
_PERMISSIVE_SAFE_RE = re.compile(
    r"\b(?:safe|fine|ok|okay|alright)\s+(?:for\s+\w+\s+)?to\s+"
    r"(?:go|play|step|walk|run|exercise)\s+out(?:side|doors)?\b",
    flags=re.IGNORECASE,
)
_PERMISSIVE_MODAL_RE = re.compile(
    r"\b(?:can|may)\s+(?:go|play|walk|run|exercise)\s+out(?:side|doors)?\b",
    flags=re.IGNORECASE,
)
_PERMISSIVE_MODAL_QUALIFIERS_RE = re.compile(
    r"\b(?:if|only|must|need to|briefly|short|mask|n95|ffp2)\b",
    flags=re.IGNORECASE,
)
_PERMISSIVE_NO_MASK_RE = re.compile(
    r"\bno\s+(?:need\s+for\s+(?:a\s+)?mask|mask\s+(?:is\s+)?needed)\b",
    flags=re.IGNORECASE,
)

_NEGATION_WORDS: frozenset[str] = frozenset(
    {
        "not",
        "no",
        "never",
        "isn't",
        "aren't",
        "don't",
        "cannot",
        "can't",
        "avoid",
        "unsafe",
    }
)
_NEGATION_BIGRAMS: frozenset[tuple[str, str]] = frozenset({("is", "not"), ("do", "not")})

# GRAP stage references (checked against context.grap_stage before stripping)
_GRAP_STAGE_RE = re.compile(
    r"\b(?:grap(?:\s+stage)?|stage)\s+(I{1,3}|IV|[1-4])\b",
    flags=re.IGNORECASE,
)
_ARABIC_TO_ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV"}

# Pollutant / mask exempt tokens removed before checking numeric grounding
_EXEMPT_TOKENS_RE = re.compile(
    r"\b(?:PM2\.5|PM10|NO2|SO2|O3|CO2|CO|N95|FFP2)\b",
    flags=re.IGNORECASE,
)

# Time ranges and clock expressions (A5: accept am/pm/a.m./p.m.)
_MERIDIEM = r"(?:a\.?m\.?|p\.?m\.?)"
_TIME_12_RANGE_RE = re.compile(
    rf"\b(?:between\s+)?(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*({_MERIDIEM})?"
    rf"\s*(?:-|–|—|to|and)\s*"
    rf"(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*({_MERIDIEM})(?!\w)",
    flags=re.IGNORECASE,
)
_TIME_24_RANGE_RE = re.compile(
    rf"\b(?:between\s+)?([01]?\d|2[0-3])[:.]([0-5]\d)\s*(?:-|–|—|to|and)\s*"
    rf"([01]?\d|2[0-3])[:.]([0-5]\d)(?:\s*({_MERIDIEM})(?!\w))?"
    r"(?!\s*(?:mg|ug|µg|/\s*m|km|cm|kg|%))",
    flags=re.IGNORECASE,
)
_TIME_12_RE = re.compile(
    rf"\b(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*({_MERIDIEM})(?!\w)",
    flags=re.IGNORECASE,
)
_TIME_24_COLON_RE = re.compile(
    rf"\b([01]?\d|2[0-3]):([0-5]\d)(?:\s*({_MERIDIEM})(?!\w))?",
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

# Number extraction (A3: catches digits adjacent to letters like "AQI999")
_NUMBER_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?!\d)")

# Number words (A3)
_LARGE_NUMBER_WORDS_RE = re.compile(r"\b(?:hundred|thousand)\b", flags=re.IGNORECASE)
_NUMBER_WORD_VALUES: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_AQ_METRIC_WORDS: frozenset[str] = frozenset(
    {"aqi", "pm", "pm2.5", "pm10", "level", "reading", "index", "ug", "µg", "micrograms"}
)

_GRAP_ROMAN_TO_NUM = {"I": 1.0, "II": 2.0, "III": 3.0, "IV": 4.0}


def _normalise_hhmm(hour: int, minute: int, meridiem: str | None) -> str | None:
    if meridiem:
        mer = meridiem.lower().replace(".", "")
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


def _sentence_around(text: str, start: int, end: int) -> str:
    seps = (".", "!", "?", ";", "\n")
    left = max(text.rfind(sep, 0, start) for sep in seps)
    right_candidates = [idx for sep in seps if (idx := text.find(sep, end)) != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left + 1 : right]


def _has_permissive_claim(text: str) -> bool:
    for pattern in (_PERMISSIVE_SAFE_RE, _PERMISSIVE_NO_MASK_RE):
        for match in pattern.finditer(text):
            if not _is_permissive_negated(text, match.start()):
                return True
    for match in _PERMISSIVE_MODAL_RE.finditer(text):
        if _is_permissive_negated(text, match.start()):
            continue
        sentence = _sentence_around(text, match.start(), match.end())
        if not _PERMISSIVE_MODAL_QUALIFIERS_RE.search(sentence):
            return True
    return False


def _has_ungrounded_number_word(text: str, allowed_numbers: list[float]) -> bool:
    if _LARGE_NUMBER_WORDS_RE.search(text):
        return True
    tokens = re.findall(r"pm2\.5|pm10|[a-zµ]+", text.lower())
    for idx, tok in enumerate(tokens):
        val = _NUMBER_WORD_VALUES.get(tok)
        if val is None:
            continue
        window = tokens[max(0, idx - 3) : idx + 4]
        if any(w in _AQ_METRIC_WORDS for w in window):
            if not any(abs(float(val) - ctx_num) <= 1.0 + 1e-9 for ctx_num in allowed_numbers):
                return True
    return False


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
            mer2_clean = mer2.lower().replace(".", "")
            if mer2_clean == "pm" and h1 > h2 and h1 != 12:
                mer1 = "am"
            elif mer2_clean == "am" and h1 > h2 and h1 == 12:
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
        user_times, _ = extract_time_expressions(normalise_guard_text(user_message))
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
    ctx_grap = context.grap_stage.upper() if context.grap_stage else None

    for raw_text in texts:
        text = normalise_guard_text(raw_text)

        if (
            _BANNED_WORD_RE.search(text)
            or _BANNED_PHRASE_RE.search(text)
            or _BANNED_DOSE_UNIT_RE.search(text)
            or _MEDICINE_INSTRUCT_RE.search(text)
        ):
            return False, "GUARD_BANNED_CLAIM"

        if context.verdict.level in POOR_OR_WORSE and _has_permissive_claim(text):
            return False, "GUARD_PERMISSIVE"

        # Check GRAP stage references: exempt only if equal to context.grap_stage
        for gmatch in _GRAP_STAGE_RE.finditer(text):
            stage_raw = gmatch.group(1).upper()
            stage_roman = _ARABIC_TO_ROMAN.get(stage_raw, stage_raw)
            if ctx_grap is None or stage_roman != ctx_grap:
                return False, "GUARD_NUMBER"
        without_grap = _GRAP_STAGE_RE.sub(" ", text)

        # Strip exempt tokens (PM2.5, PM10, N95, etc.) before checking times & numbers
        without_exempt = _EXEMPT_TOKENS_RE.sub(" ", without_grap)

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

        if _has_ungrounded_number_word(cleaned, allowed_numbers):
            return False, "GUARD_NUMBER"

        for num_str in _NUMBER_RE.findall(cleaned):
            num = float(num_str)
            if not any(abs(num - ctx_num) <= 1.0 + 1e-9 for ctx_num in allowed_numbers):
                return False, "GUARD_NUMBER"

    return True, None
