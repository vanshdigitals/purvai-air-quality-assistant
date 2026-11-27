"""Home Air ACH calculator and deterministic indoor tips catalogue."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from app.rules.catalogue import Category

TARGET_ACH = 5
IST_ZONE = ZoneInfo("Asia/Kolkata")


class HomeAirCalcRequest(BaseModel):
    """Input dimensions and purifier CADR for ACH calculation."""

    model_config = ConfigDict(extra="forbid")

    length_m: float = Field(ge=0.5, le=50.0)
    width_m: float = Field(ge=0.5, le=50.0)
    height_m: float = Field(ge=1.5, le=10.0)
    cadr_m3h: float = Field(ge=20.0, le=2000.0)


class HomeAirCalcResponse(BaseModel):
    """Output ACH evaluation against Purvai's target of 5 ACH."""

    model_config = ConfigDict(frozen=True)

    volume_m3: float
    ach: float
    target_ach: int = TARGET_ACH
    meets_target: bool
    cadr_needed_m3h: int


class HomeAirTip(BaseModel):
    """Single deterministic indoor air tip."""

    model_config = ConfigDict(frozen=True)

    tip_id: str
    text: str


class HomeAirTipsResponse(BaseModel):
    """Home Air tips response for current AQI category."""

    model_config = ConfigDict(frozen=True)

    level: Category
    tips: list[HomeAirTip]
    ventilation_hour: str | None


_ALL_LEVELS: frozenset[Category] = frozenset(
    {"good", "satisfactory", "moderate", "poor", "very_poor", "severe"}
)
_MODERATE_AND_WORSE: frozenset[Category] = frozenset({"moderate", "poor", "very_poor", "severe"})
_POOR_AND_WORSE: frozenset[Category] = frozenset({"poor", "very_poor", "severe"})

HOME_AIR_TIPS: tuple[tuple[str, str, frozenset[Category]], ...] = (
    (
        "purifier_closed_room",
        "Run the purifier with doors and windows closed.",
        _POOR_AND_WORSE,
    ),
    (
        "wet_mopping",
        "Wet-mop floors instead of dry sweeping.",
        _MODERATE_AND_WORSE,
    ),
    (
        "cooking_exhaust",
        "Use the kitchen exhaust or chimney while cooking.",
        _ALL_LEVELS,
    ),
    (
        "avoid_incense",
        "Avoid incense and mosquito coils on high-pollution days.",
        _POOR_AND_WORSE,
    ),
    (
        "mask_fit",
        "Outdoors, a well-fitted N95 or FFP2 works better than cloth or surgical masks.",
        _POOR_AND_WORSE,
    ),
    (
        "ventilate_low_hour",
        "Air the room briefly at the cleanest forecast hour, then close windows.",
        _ALL_LEVELS,
    ),
)


def calculate_home_air(req: HomeAirCalcRequest) -> HomeAirCalcResponse:
    """Compute room volume, ACH (1 decimal), target match, and required CADR."""
    raw_volume = req.length_m * req.width_m * req.height_m
    volume_m3 = round(raw_volume, 1)
    ach = round(req.cadr_m3h / raw_volume, 1)
    cadr_needed_m3h = round(raw_volume * TARGET_ACH)
    return HomeAirCalcResponse(
        volume_m3=volume_m3,
        ach=ach,
        target_ach=TARGET_ACH,
        meets_target=ach >= TARGET_ACH,
        cadr_needed_m3h=cadr_needed_m3h,
    )


def get_home_air_tips(level: Category, ventilation_hour: str | None = None) -> HomeAirTipsResponse:
    """Return deterministic indoor tips for the given AQI category."""
    tips: list[HomeAirTip] = []
    for tip_id, base_text, levels in HOME_AIR_TIPS:
        if level not in levels:
            continue
        text = base_text
        if tip_id == "ventilate_low_hour" and ventilation_hour is not None:
            dt = datetime.fromisoformat(ventilation_hour.replace("Z", "+00:00"))
            dt_ist = (dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt).astimezone(IST_ZONE)
            ist_label = f"{dt_ist.hour:02d}:{dt_ist.minute:02d} IST"
            text = (
                f"Air the room briefly at the cleanest forecast hour ({ist_label}), "
                "then close windows."
            )
        tips.append(HomeAirTip(tip_id=tip_id, text=text))

    return HomeAirTipsResponse(
        level=level,
        tips=tips,
        ventilation_hour=ventilation_hour,
    )
