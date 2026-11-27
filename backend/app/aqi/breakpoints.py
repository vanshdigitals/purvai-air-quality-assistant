"""CPCB 2014 NAQI pollutant breakpoint table from docs/ARCHITECTURE.md."""

from dataclasses import dataclass
from typing import Literal

from app.rules.catalogue import Category

PollutantId = Literal["pm25", "pm10", "no2", "o3", "co", "so2"]


@dataclass(frozen=True)
class BreakpointBand:
    """Single CPCB NAQI concentration-to-subindex band."""

    category: Category
    i_lo: int
    i_hi: int
    b_lo: float
    b_hi: float | None  # None represents unbounded Severe ("+") upper range.


# PM2.5 and PM10 rows are baseline-verified.
# Gas rows (no2, o3, co, so2) come from the CPCB 2014 NAQI table and are marked
# "re-check in Phase 2" in docs/ARCHITECTURE.md (verified against CPCB 2014 NAQI).
CPCB_BREAKPOINTS: dict[PollutantId, tuple[BreakpointBand, ...]] = {
    "pm25": (
        BreakpointBand("good", 0, 50, 0, 30),
        BreakpointBand("satisfactory", 51, 100, 31, 60),
        BreakpointBand("moderate", 101, 200, 61, 90),
        BreakpointBand("poor", 201, 300, 91, 120),
        BreakpointBand("very_poor", 301, 400, 121, 250),
        BreakpointBand("severe", 401, 500, 250, None),
    ),
    "pm10": (
        BreakpointBand("good", 0, 50, 0, 50),
        BreakpointBand("satisfactory", 51, 100, 51, 100),
        BreakpointBand("moderate", 101, 200, 101, 250),
        BreakpointBand("poor", 201, 300, 251, 350),
        BreakpointBand("very_poor", 301, 400, 351, 430),
        BreakpointBand("severe", 401, 500, 430, None),
    ),
    "no2": (
        BreakpointBand("good", 0, 50, 0, 40),
        BreakpointBand("satisfactory", 51, 100, 41, 80),
        BreakpointBand("moderate", 101, 200, 81, 180),
        BreakpointBand("poor", 201, 300, 181, 280),
        BreakpointBand("very_poor", 301, 400, 281, 400),
        BreakpointBand("severe", 401, 500, 400, None),
    ),
    "o3": (
        BreakpointBand("good", 0, 50, 0, 50),
        BreakpointBand("satisfactory", 51, 100, 51, 100),
        BreakpointBand("moderate", 101, 200, 101, 168),
        BreakpointBand("poor", 201, 300, 169, 208),
        BreakpointBand("very_poor", 301, 400, 209, 748),
        BreakpointBand("severe", 401, 500, 748, None),
    ),
    "co": (
        BreakpointBand("good", 0, 50, 0.0, 1.0),
        BreakpointBand("satisfactory", 51, 100, 1.1, 2.0),
        BreakpointBand("moderate", 101, 200, 2.1, 10.0),
        BreakpointBand("poor", 201, 300, 10.1, 17.0),
        BreakpointBand("very_poor", 301, 400, 17.1, 34.0),
        BreakpointBand("severe", 401, 500, 34.0, None),
    ),
    "so2": (
        BreakpointBand("good", 0, 50, 0, 40),
        BreakpointBand("satisfactory", 51, 100, 41, 80),
        BreakpointBand("moderate", 101, 200, 81, 380),
        BreakpointBand("poor", 201, 300, 381, 800),
        BreakpointBand("very_poor", 301, 400, 801, 1600),
        BreakpointBand("severe", 401, 500, 1600, None),
    ),
}

POLLUTANT_UNITS: dict[PollutantId, str] = {
    "pm25": "µg/m³",
    "pm10": "µg/m³",
    "no2": "µg/m³",
    "o3": "µg/m³",
    "co": "mg/m³",
    "so2": "µg/m³",
}

POLLUTANT_TIE_ORDER: tuple[PollutantId, ...] = ("pm25", "pm10", "no2", "o3", "co", "so2")
