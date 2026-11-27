"""CPCB NAQI sub-index interpolation and overall AQI calculation."""

from dataclasses import dataclass

from app.aqi.breakpoints import (
    CPCB_BREAKPOINTS,
    POLLUTANT_TIE_ORDER,
    POLLUTANT_UNITS,
    PollutantId,
)
from app.aqi.normalise import truncate_for_lookup
from app.rules.catalogue import Category


@dataclass(frozen=True)
class PollutantSubIndex:
    """Computed sub-index for a single pollutant."""

    pollutant: PollutantId
    value: float
    unit: str
    sub_index: int
    category: Category
    is_floor: bool


@dataclass(frozen=True)
class OverallAqiResult:
    """Computed overall CPCB NAQI result across available pollutants."""

    aqi: int
    aqi_is_floor: bool
    category: Category
    dominant_pollutant: PollutantId
    sub_indices: dict[PollutantId, PollutantSubIndex]
    meets_three_pollutant_rule: bool


def category_for_aqi(aqi: int) -> Category:
    """Map an integer CPCB AQI score to its category."""
    if aqi <= 50:
        return "good"
    if aqi <= 100:
        return "satisfactory"
    if aqi <= 200:
        return "moderate"
    if aqi <= 300:
        return "poor"
    if aqi <= 400:
        return "very_poor"
    return "severe"


def compute_sub_index(pollutant: PollutantId, raw_value: float) -> PollutantSubIndex:
    """Compute CPCB sub-index using P2-4 truncation and P2-5 Severe floor."""
    truncated = truncate_for_lookup(pollutant, raw_value)
    bands = CPCB_BREAKPOINTS[pollutant]

    for band in bands:
        if band.b_hi is None:
            # Severe band: unbounded upper limit -> floor 401 with aqi_is_floor=True.
            return PollutantSubIndex(
                pollutant=pollutant,
                value=truncated,
                unit=POLLUTANT_UNITS[pollutant],
                sub_index=401,
                category="severe",
                is_floor=True,
            )
        if band.b_lo <= truncated <= band.b_hi:
            if band.b_hi == band.b_lo:
                sub_index = band.i_lo
            else:
                interpolated = ((band.i_hi - band.i_lo) / (band.b_hi - band.b_lo)) * (
                    truncated - band.b_lo
                ) + band.i_lo
                sub_index = round(interpolated)
            return PollutantSubIndex(
                pollutant=pollutant,
                value=truncated,
                unit=POLLUTANT_UNITS[pollutant],
                sub_index=sub_index,
                category=band.category,
                is_floor=False,
            )

    raise ValueError(f"Concentration {truncated} did not match any band for {pollutant}")


def compute_overall_aqi(pollutants: dict[PollutantId, float]) -> OverallAqiResult | None:
    """Compute overall AQI from normalised concentrations.

    Returns None when neither PM2.5 nor PM10 is present (P2-6).
    """
    sub_indices: dict[PollutantId, PollutantSubIndex] = {}
    for pollutant in POLLUTANT_TIE_ORDER:
        raw = pollutants.get(pollutant)
        if raw is None:
            continue
        sub_indices[pollutant] = compute_sub_index(pollutant, raw)

    if "pm25" not in sub_indices and "pm10" not in sub_indices:
        return None

    dominant: PollutantId = max(
        POLLUTANT_TIE_ORDER,
        key=lambda p: sub_indices[p].sub_index if p in sub_indices else -1,
    )
    top = sub_indices[dominant]
    overall_aqi = top.sub_index

    return OverallAqiResult(
        aqi=overall_aqi,
        aqi_is_floor=top.is_floor,
        category=category_for_aqi(overall_aqi),
        dominant_pollutant=dominant,
        sub_indices=sub_indices,
        meets_three_pollutant_rule=len(sub_indices) >= 3,
    )
