"""Pydantic v2 structured AI I/O contracts (v1.0 / Context v1.1) with S-1..S-5 helpers."""

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.rules.catalogue import Category

ActionIdLiteral = Literal[
    "normal_activity",
    "watch_symptoms",
    "reduce_long_exertion",
    "limit_outdoor_exertion",
    "exercise_indoors",
    "windows_closed_peaks",
    "mostly_indoors",
    "mask_outdoors",
    "no_outdoor_exercise",
    "n95_if_out",
    "stay_indoors",
    "purifier_on",
    "avoid_going_out",
    "doctor_if_symptoms",
    "mask_and_breaks",
]

TipIdLiteral = Literal[
    "purifier_closed_room",
    "wet_mopping",
    "cooking_exhaust",
    "avoid_incense",
    "mask_fit",
    "ventilate_low_hour",
]

DataCitedLiteral = Literal["aqi", "category", "pollutant", "forecast", "grap", "source"]
PeriodLiteral = Literal["morning", "afternoon", "evening", "night"]
ForecastTrendLiteral = Literal["worsening", "improving", "steady"]


class AIContextHousehold(BaseModel):
    """Derived household sensitivity flags without counts or names."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    has_child: bool
    has_older_adult: bool
    has_heart_lung: bool
    outdoor_worker: bool


class AIContextVerdict(BaseModel):
    """Immutable server rules verdict passed into AI prompts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: Category
    action_ids: list[ActionIdLiteral]


class AIContextPollutant(BaseModel):
    """Single pollutant value and NAQI sub-index for grounding."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float
    sub_index: int


class AIContextForecastPoint(BaseModel):
    """Hourly forecast summary in IST for context grounding."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    time_ist: str
    aqi: int
    category: Category


class AIContextPlanPeriod(BaseModel):
    """Rule-computed period summary used only when wording a Daily Protection Plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    period: PeriodLiteral
    level: Category
    aqi: int
    action_ids: list[ActionIdLiteral]


class AIContext(BaseModel):
    """Derived air & household context sent to AI providers (Context v1.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.1"] = "1.1"
    aqi: int
    category: Category
    source_label: Literal["Measured", "Modelled", "Estimated"]
    dominant_pollutant: str
    forecast_trend: ForecastTrendLiteral
    grap_stage: str | None
    household: AIContextHousehold
    verdict: AIContextVerdict
    local_time: str
    city: str | None
    stale: bool
    age_minutes: int
    age_hours: int
    observed_time_ist: str
    pollutants: dict[str, AIContextPollutant]
    forecast: list[AIContextForecastPoint]
    plan_periods: list[AIContextPlanPeriod] | None = None


class Recommendation(BaseModel):
    """Action recommendation reworded or copied from the fixed rules catalogue."""

    model_config = ConfigDict(extra="forbid")

    action_id: ActionIdLiteral
    title: str = Field(..., min_length=1, max_length=60)
    why: str = Field(..., min_length=1, max_length=200)
    tag: Literal["rule", "ai_wording"]


class DailyPlanPeriodWording(BaseModel):
    """Reworded recommendations for a single daily plan period."""

    model_config = ConfigDict(extra="forbid")

    period: PeriodLiteral
    items: list[Recommendation] = Field(..., min_length=1, max_length=4)


class DailyPlanWording(BaseModel):
    """Structured AI wording for the 4-period Daily Protection Plan (v1.0)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    verdict_level: Category
    summary: str = Field(..., min_length=1, max_length=160)
    periods: list[DailyPlanPeriodWording] = Field(..., min_length=4, max_length=4)


class ChatReply(BaseModel):
    """Structured Ask Purvai assistant reply (v1.0)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    verdict_level: Category
    answer: str = Field(..., min_length=1, max_length=600)
    data_cited: list[DataCitedLiteral] = Field(..., min_length=1, max_length=6)
    recommendations: list[Recommendation] = Field(..., max_length=3)
    needs_doctor_note: bool
    out_of_scope: bool


class IndoorAdviceTip(BaseModel):
    """Single reworded indoor air tip."""

    model_config = ConfigDict(extra="forbid")

    tip_id: TipIdLiteral
    text: str = Field(..., min_length=1, max_length=160)


class IndoorAdvice(BaseModel):
    """Structured AI wording for Home Air indoor tips (v1.0)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    verdict_level: Category
    tips: list[IndoorAdviceTip] = Field(..., min_length=1, max_length=5)
    ach_explanation: str | None = Field(..., max_length=200)


class ImpactExplanation(BaseModel):
    """Impact explanation contract v1.0 (defined in Phase 4, wired in Phase 5)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    sentence: str = Field(..., min_length=1, max_length=200)
    basis: Literal["ITF-2023-lifecycle"]
    label: Literal["Estimated"]


class StructuredReply(BaseModel):
    """Wrapper returned by LLMProvider implementations after schema validation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: BaseModel
    provider: Literal["gemini", "groq"]
    model: str
    latency_ms: int


def _normalise_schema_node(node: Any) -> Any:
    if isinstance(node, list):
        return [_normalise_schema_node(item) for item in node]
    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    for key, val in node.items():
        if key in {"pattern", "format", "default"}:
            continue
        out[key] = _normalise_schema_node(val)

    if out.get("type") == "object" or "properties" in out:
        props = out.get("properties")
        if isinstance(props, dict):
            out["required"] = list(props.keys())
        out["additionalProperties"] = False

    return out


def build_provider_json_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Generate a strict Gemini/Groq compatible JSON Schema obeying rules S-1 to S-4."""
    raw = deepcopy(schema.model_json_schema())
    normalised = _normalise_schema_node(raw)
    assert isinstance(normalised, dict)
    return normalised
