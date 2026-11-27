"""Independent audit guard-bypass probes and fixes A1-A8."""

from datetime import UTC, datetime

import pytest
from app.ai.context import build_ai_context
from app.ai.gateway import generate_chat_reply
from app.ai.guard import validate_ai_reply
from app.ai.schemas.v1.models import ChatReply, Recommendation, StructuredReply
from app.ai.templates import has_symptom_keywords
from app.aqi.pipeline import (
    AirForecastResponse,
    AirQualityResponse,
    ForecastHourOut,
    ForecastLowestOut,
    PollutantReadingOut,
    SourceMeta,
)
from app.config import Settings
from app.rules.catalogue import Category
from app.rules.engine import compute_verdict
from app.rules.grap import GrapInfo


def _make_context(
    *,
    category: Category = "very_poor",
    aqi: int = 312,
    grap_stage: str | None = "II",
) -> object:
    verdict = compute_verdict(category, ["adult"])
    air = AirQualityResponse(
        aqi=aqi,
        aqi_is_floor=aqi >= 401,
        category=category,
        scale="CPCB_NAQI",
        source_label="Measured",
        source=SourceMeta(provider="CPCB", station="Sector-62", distance_km=3.1),
        observed_at="2026-11-27T02:30:00Z",  # 08:00 IST
        age_minutes=65,
        stale=False,
        indicative=True,
        served_from_cache=False,
        dominant_pollutant="pm25",
        pollutants={
            "pm25": PollutantReadingOut(value=135.0, unit="µg/m³", sub_index=312),
            "pm10": PollutantReadingOut(value=210.0, unit="µg/m³", sub_index=173),
        },
        verdict=verdict,
        grap=(
            GrapInfo(stage=grap_stage, order_date="2026-11-02", source_url="https://caqm.nic.in/")
            if grap_stage
            else None
        ),
        attribution=["CPCB", "data.gov.in"],
    )
    forecast = AirForecastResponse(
        generated_at="2026-11-27T02:30:00Z",
        scale="CPCB_NAQI",
        source_label="Modelled",
        attribution=["Open-Meteo"],
        hours=[
            ForecastHourOut(
                time="2026-11-27T04:00:00Z",  # 09:30 IST
                aqi=280,
                aqi_is_floor=False,
                category="poor",
                dominant_pollutant="pm25",
                pm25=115.0,
                pm10=180.0,
                o3=30.0,
                no2=25.0,
            )
        ],
        lowest=ForecastLowestOut(
            time="2026-11-27T04:00:00Z",
            aqi=280,
            category="poor",
        ),
    )
    return build_ai_context(
        air=air,
        forecast=forecast,
        member_kinds=["adult"],
        city="Noida",
        now_utc=datetime(2026, 11, 27, 3, 35, tzinfo=UTC),
    )


def _reply(
    answer: str,
    *,
    level: Category = "very_poor",
    action_id: str = "no_outdoor_exercise",
    tag: str = "ai_wording",
) -> ChatReply:
    return ChatReply(
        schema_version="1.0",
        verdict_level=level,
        answer=answer,
        data_cited=["aqi", "category", "source"],
        recommendations=[
            Recommendation(
                action_id=action_id,
                title="Stay indoors",
                why="Very poor air quality.",
                tag=tag,  # type: ignore[arg-type]
            )
        ],
        needs_doctor_note=False,
        out_of_scope=False,
    )


# A1: Normalisation probes
def test_a1_normalisation_probes() -> None:
    ctx = _make_context(category="very_poor")
    # Two spaces + zero-width space
    ok1, code1 = validate_ai_reply(_reply("It is safe  to go\u200b out now."), ctx)  # type: ignore[arg-type]
    assert not ok1 and code1 == "GUARD_PERMISSIVE"

    # Fullwidth / zero-width obfuscated "cure"
    ok2, code2 = validate_ai_reply(_reply("This will \uff43u\u200bre asthma."), ctx)  # type: ignore[arg-type]
    assert not ok2 and code2 == "GUARD_BANNED_CLAIM"


# A2: Permissive phrases + negation + qualifiers
@pytest.mark.parametrize(
    ("category", "aqi", "answer", "expected_ok", "expected_code"),
    [
        ("severe", 420, "It is safe to go outside now.", False, "GUARD_PERMISSIVE"),
        ("very_poor", 312, "Your son can play outside, it is fine.", False, "GUARD_PERMISSIVE"),
        ("very_poor", 312, "It is not safe to go outside.", True, None),
        ("very_poor", 312, "If he must go out, use a well-fitted N95.", True, None),
        ("very_poor", 312, "He can play indoors.", True, None),
        ("moderate", 150, "It is fine to go out.", True, None),
    ],
)
def test_a2_permissive_phrases(
    category: Category,
    aqi: int,
    answer: str,
    expected_ok: bool,
    expected_code: str | None,
) -> None:
    ctx = _make_context(category=category, aqi=aqi)
    action_id = ctx.verdict.action_ids[0]  # type: ignore[attr-defined]
    ok, code = validate_ai_reply(
        _reply(answer, level=category, action_id=action_id),
        ctx,  # type: ignore[arg-type]
    )
    assert ok is expected_ok
    assert code == expected_code


# A3: Numbers, dose units, adjacent digits, number words, GRAP stage
@pytest.mark.parametrize(
    ("answer", "expected_ok"),
    [
        ("Give him 500mg paracetamol.", False),
        ("AQI999 is the reading.", False),
        ("The AQI is nine hundred right now.", False),
        ("GRAP Stage IV is in force.", False),
        ("One more tip: keep windows shut.", True),
        ("PM2.5 is very high.", True),
        ("GRAP Stage II is in force.", True),
    ],
)
def test_a3_numbers_and_grap(answer: str, expected_ok: bool) -> None:
    ctx = _make_context(category="very_poor", grap_stage="II")
    ok, _ = validate_ai_reply(_reply(answer), ctx)  # type: ignore[arg-type]
    assert ok is expected_ok


# A4: Medicine advice
def test_a4_medicine_advice() -> None:
    ctx = _make_context(category="very_poor")
    ok_bad, code_bad = validate_ai_reply(
        _reply("Use the inhaler twice and take an antihistamine."),
        ctx,  # type: ignore[arg-type]
    )
    assert not ok_bad and code_bad == "GUARD_BANNED_CLAIM"

    ok_good, _ = validate_ai_reply(
        _reply("Please talk to a doctor about any medicine."),
        ctx,  # type: ignore[arg-type]
    )
    assert ok_good


# A5: Dotted meridiem times
def test_a5_dotted_meridiem_times() -> None:
    ctx = _make_context(category="very_poor")
    ok, code = validate_ai_reply(
        _reply("The air clears at 2 p.m. today."),
        ctx,  # type: ignore[arg-type]
    )
    assert not ok and code == "GUARD_TIME"

    # Grounded when user asked about 2 p.m.
    ok_user, _ = validate_ai_reply(
        _reply("At 2 p.m. keep windows closed."),
        ctx,  # type: ignore[arg-type]
        user_message="How is the air at 2 p.m.?",
    )
    assert ok_user


# A7: AI cannot claim tag="rule"
@pytest.mark.anyio
async def test_a7_ai_cannot_claim_rule_tag() -> None:
    ctx = _make_context(category="very_poor")

    class _RuleTagProvider:
        name = "gemini"

        async def generate(self, **kwargs: object) -> StructuredReply:
            return StructuredReply(
                data=_reply("AQI is 312. Stay indoors.", tag="rule"),
                provider="gemini",
                model="gemini-3.5-flash-lite",
                latency_ms=42,
            )

    res = await generate_chat_reply(
        settings=Settings(purvai_mode="local"),
        context=ctx,  # type: ignore[arg-type]
        user_message="Should I stay indoors?",
        ai_enabled=True,
        providers_override=[_RuleTagProvider()],  # type: ignore[list-item]
    )
    assert res.generated_by == "gemini"
    assert isinstance(res.data, ChatReply)
    assert all(r.tag == "ai_wording" for r in res.data.recommendations)


# A8: Symptom stems
@pytest.mark.parametrize(
    "msg",
    [
        "he coughs at night",
        "she is wheezy",
        "asthma",
        "chest hurts",
        "breathing problem",
        "khansi ho rahi hai",
        "he is short-of-breath",
    ],
)
def test_a8_symptom_stems(msg: str) -> None:
    assert has_symptom_keywords(msg) is True


# A6: Server grounding_note for Modelled and stale data
def test_a6_grounding_note_modelled_and_stale(
    local_client: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    client = local_client
    assert isinstance(client, TestClient)

    client.put(
        "/api/v1/household",
        json={
            "members": [{"kind": "adult", "count": 1}],
            "location": {"label": "Noida", "lat": 28.6271, "lon": 77.3716, "city": "Noida"},
            "settings": {
                "theme": "system",
                "commute_mode": "metro",
                "ai_enabled": True,
                "save_chat": False,
                "reduce_motion": False,
            },
        },
    )

    verdict = compute_verdict("very_poor", ["adult"])
    stale_modelled_air = AirQualityResponse(
        aqi=312,
        aqi_is_floor=False,
        category="very_poor",
        scale="CPCB_NAQI",
        source_label="Modelled",
        source=SourceMeta(provider="Open-Meteo", station=None, distance_km=None),
        observed_at="2026-11-27T01:00:00Z",
        age_minutes=180,
        stale=True,
        indicative=True,
        served_from_cache=True,
        dominant_pollutant="pm25",
        pollutants={"pm25": PollutantReadingOut(value=135.0, unit="µg/m³", sub_index=312)},
        verdict=verdict,
        grap=None,
        attribution=["Open-Meteo"],
    )

    async def _fake_air(*args: object, **kwargs: object) -> AirQualityResponse:
        return stale_modelled_air

    async def _fake_forecast(*args: object, **kwargs: object) -> None:
        return None

    async def _fake_gateway(**kwargs: object) -> object:
        from app.ai.gateway import GatewayResult

        return GatewayResult(
            data=_reply("AQI is 312. Stay indoors.", action_id=verdict.action_ids[0]),
            generated_by="gemini",
            guard_code=None,
            note=None,
            latency_ms=10,
        )

    import app.api.chat as chat_api

    monkeypatch.setattr(chat_api, "get_air_quality", _fake_air)
    monkeypatch.setattr(chat_api, "get_air_forecast", _fake_forecast)
    monkeypatch.setattr(chat_api, "generate_chat_reply", _fake_gateway)

    resp = client.post("/api/v1/chat", json={"message": "Should I go outside?"})
    assert resp.status_code == 200
    body = resp.json()
    assert "This is a modelled estimate." in (body.get("grounding_note") or "")
    assert "Data is 3 hours old." in (body.get("grounding_note") or "")
