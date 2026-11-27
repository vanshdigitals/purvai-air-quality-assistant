"""Deterministic rule-catalogue fallback templates and symptom detection (SAF-04)."""

import re
from typing import cast

from app.ai.schemas.v1.models import (
    AIContext,
    ChatReply,
    DailyPlanPeriodWording,
    DailyPlanWording,
    DataCitedLiteral,
    IndoorAdvice,
    IndoorAdviceTip,
    Recommendation,
    TipIdLiteral,
)
from app.rules.catalogue import ACTION_TEXTS
from app.rules.home_air import get_home_air_tips

AI_UNAVAILABLE_NOTE = "AI unavailable, showing standard advice"
AI_DISABLED_NOTE = "AI is off. Showing standard advice."

SYMPTOM_KEYWORDS: tuple[str, ...] = (
    "cough",
    "coughing",
    "wheeze",
    "wheezing",
    "breathless",
    "breathlessness",
    "short of breath",
    "shortness of breath",
    "chest pain",
    "chest tightness",
    "can't breathe",
    "cannot breathe",
    "difficulty breathing",
    "asthma attack",
    "saans",
)

_SYMPTOM_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(k) for k in SYMPTOM_KEYWORDS) + r")(?!\w)",
    flags=re.IGNORECASE,
)


def has_symptom_keywords(user_message: str) -> bool:
    """Return True when the user mentions respiratory or chest symptom keywords."""
    return bool(_SYMPTOM_RE.search(user_message))


def _why_for_action(action_id: str, context: AIContext) -> str:
    return (
        f"Rule guidance for {context.verdict.level.replace('_', ' ')} air "
        f"(AQI {context.aqi}, {context.source_label})."
    )[:200]


def build_chat_template(
    context: AIContext,
    *,
    user_message: str,
    ai_disabled: bool,
) -> ChatReply:
    """Build deterministic template ChatReply when AI is disabled or failed."""
    note = AI_DISABLED_NOTE if ai_disabled else AI_UNAVAILABLE_NOTE
    action_texts = [ACTION_TEXTS[aid] for aid in context.verdict.action_ids]
    headline = " ".join(action_texts[:2]) if action_texts else "Follow current air guidance."
    answer = f"{headline} ({note})"[:600]

    recommendations = [
        Recommendation(
            action_id=aid,
            title=ACTION_TEXTS[aid][:60],
            why=_why_for_action(aid, context),
            tag="rule",
        )
        for aid in context.verdict.action_ids[:3]
    ]
    cited: list[DataCitedLiteral] = ["aqi", "category", "source"]

    return ChatReply(
        schema_version="1.0",
        verdict_level=context.verdict.level,
        answer=answer,
        data_cited=cited,
        recommendations=recommendations,
        needs_doctor_note=has_symptom_keywords(user_message),
        out_of_scope=False,
    )


def build_plan_template(context: AIContext) -> DailyPlanWording:
    """Build deterministic rule-text DailyPlanWording fallback."""
    periods: list[DailyPlanPeriodWording] = []
    for p in context.plan_periods or []:
        items = [
            Recommendation(
                action_id=aid,
                title=ACTION_TEXTS[aid][:60],
                why=_why_for_action(aid, context),
                tag="rule",
            )
            for aid in p.action_ids[:4]
        ]
        periods.append(DailyPlanPeriodWording(period=p.period, items=items))

    return DailyPlanWording(
        schema_version="1.0",
        verdict_level=context.verdict.level,
        summary=f"Standard rule guidance for AQI {context.aqi}."[:160],
        periods=periods,
    )


def build_indoor_template(
    context: AIContext,
    *,
    ventilation_hour: str | None = None,
) -> IndoorAdvice:
    """Build deterministic Home Air template advice."""
    rules_res = get_home_air_tips(context.category, ventilation_hour=ventilation_hour)
    tips = [
        IndoorAdviceTip(
            tip_id=cast(TipIdLiteral, t.tip_id),
            text=t.text[:160],
        )
        for t in rules_res.tips[:5]
    ]
    return IndoorAdvice(
        schema_version="1.0",
        verdict_level=context.verdict.level,
        tips=tips,
        ach_explanation=None,
    )
