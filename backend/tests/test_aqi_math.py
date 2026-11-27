"""Unit tests for CPCB NAQI breakpoints, truncation, interpolation, and overall AQI."""

import math

import pytest
from app.aqi.breakpoints import CPCB_BREAKPOINTS, PollutantId
from app.aqi.calculator import category_for_aqi, compute_overall_aqi, compute_sub_index
from app.aqi.normalise import (
    map_cpcb_pollutant,
    normalise_cpcb_value,
    normalise_open_meteo_value,
    truncate_for_lookup,
)


@pytest.mark.parametrize("pollutant", list(CPCB_BREAKPOINTS.keys()))
def test_every_documented_band_lower_and_upper_bounds(pollutant: PollutantId) -> None:
    bands = CPCB_BREAKPOINTS[pollutant]
    for band in bands:
        if band.b_hi is None:
            above = band.b_lo + (0.1 if pollutant == "co" else 1.0)
            res = compute_sub_index(pollutant, above)
            assert res.sub_index == 401
            assert res.is_floor is True
            assert res.category == "severe"
        else:
            low_res = compute_sub_index(pollutant, band.b_lo)
            high_res = compute_sub_index(pollutant, band.b_hi)
            assert low_res.sub_index == band.i_lo
            assert low_res.is_floor is False
            assert low_res.category == band.category
            assert high_res.sub_index == band.i_hi
            assert high_res.is_floor is False
            assert high_res.category == band.category


def test_pm25_135_worked_interpolation_gives_312() -> None:
    # 301 + (135 - 121) * 99 / 129 = 311.744... -> 312
    res = compute_sub_index("pm25", 135.0)
    assert res.sub_index == 312
    assert res.category == "very_poor"
    assert res.is_floor is False


def test_truncation_to_table_precision_before_lookup() -> None:
    assert truncate_for_lookup("pm25", 30.9) == 30.0
    assert compute_sub_index("pm25", 30.9).sub_index == 50

    assert truncate_for_lookup("pm25", 250.9) == 250.0
    assert compute_sub_index("pm25", 250.9).sub_index == 400

    assert truncate_for_lookup("co", 1.09) == 1.0
    assert compute_sub_index("co", 1.09).sub_index == 50

    assert truncate_for_lookup("co", 2.09) == 2.0
    assert compute_sub_index("co", 2.09).sub_index == 100

    assert truncate_for_lookup("co", 17.09) == 17.0
    assert compute_sub_index("co", 17.09).sub_index == 300


def test_severe_floor_sets_401_and_flag() -> None:
    overall = compute_overall_aqi({"pm25": 290.0, "pm10": 320.0, "no2": 50.0})
    assert overall is not None
    assert overall.aqi == 401
    assert overall.aqi_is_floor is True
    assert overall.category == "severe"
    assert overall.dominant_pollutant == "pm25"


def test_overall_aqi_max_subindex_dominant_and_three_pollutant_rule() -> None:
    full = compute_overall_aqi({"pm25": 45.0, "pm10": 180.0, "no2": 30.0})
    assert full is not None
    assert full.dominant_pollutant == "pm10"
    assert full.aqi == compute_sub_index("pm10", 180.0).sub_index
    assert full.meets_three_pollutant_rule is True

    partial = compute_overall_aqi({"pm25": 75.0, "no2": 45.0})
    assert partial is not None
    assert partial.meets_three_pollutant_rule is False
    assert partial.dominant_pollutant == "pm25"

    no_pm = compute_overall_aqi({"no2": 90.0, "so2": 50.0, "co": 2.0})
    assert no_pm is None


def test_open_meteo_co_unit_conversion_and_category_mapping() -> None:
    co_mg = normalise_open_meteo_value("co", 3794.0)
    assert co_mg == pytest.approx(3.794)
    assert truncate_for_lookup("co", co_mg or 0.0) == 3.7

    assert category_for_aqi(0) == "good"
    assert category_for_aqi(51) == "satisfactory"
    assert category_for_aqi(101) == "moderate"
    assert category_for_aqi(201) == "poor"
    assert category_for_aqi(301) == "very_poor"
    assert category_for_aqi(401) == "severe"


def test_normalise_units_aliases_and_invalid_values() -> None:
    assert map_cpcb_pollutant("PM2.5") == "pm25"
    assert map_cpcb_pollutant("PM25") == "pm25"
    assert map_cpcb_pollutant("OZONE") == "o3"
    assert map_cpcb_pollutant("NH3") is None
    assert map_cpcb_pollutant("") is None
    assert map_cpcb_pollutant(None) is None

    # CO in ug/m3 via pollutant_unit -> converted to mg/m3
    assert normalise_cpcb_value("co", 2500.0, "µg/m³") == pytest.approx(2.5)
    assert normalise_cpcb_value("co", 1800.0, "ug/m3") == pytest.approx(1.8)
    assert normalise_cpcb_value("co", 2.1, "mg/m³") == pytest.approx(2.1)
    assert normalise_cpcb_value("pm25", -5.0, "µg/m³") is None
    assert normalise_cpcb_value("pm25", math.nan) is None
    assert normalise_open_meteo_value("pm25", -1.0) is None
    assert normalise_open_meteo_value("pm25", math.inf) is None

    with pytest.raises(ValueError):
        truncate_for_lookup("pm25", -0.1)
