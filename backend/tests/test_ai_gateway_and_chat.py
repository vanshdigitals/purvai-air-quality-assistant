"""AI gateway fallbacks, symptom enforcement, /chat, FR-17 history, plan wording, and logging."""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from app.ai.gateway import generate_chat_reply
from app.ai.providers import (
    GROQ_CHAT_COMPLETIONS_URL,
    GeminiProvider,
    LLMProvider,
    ProviderCallError,
)
from app.ai.schemas.v1.models import (
    AIContext,
    AIContextPlanPeriod,
    ChatReply,
    DailyPlanWording,
    IndoorAdvice,
    StructuredReply,
)
from app.ai.templates import (
    AI_DISABLED_NOTE,
    AI_UNAVAILABLE_NOTE,
    SYMPTOM_KEYWORDS,
    build_indoor_template,
    build_plan_template,
)
from app.config import Settings
from app.db.models import Conversation, DailyPlan, Message, PlanItem
from app.main import create_app
from app.providers.cpcb import CPCB_RESOURCE_URL
from app.providers.open_meteo import OPEN_METEO_AIR_URL
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pydantic import BaseModel, SecretStr
from sqlmodel import Session, select

from tests.test_ai_schemas_context_guard import _sample_context

FIXTURES = Path(__file__).parent / "fixtures"
_STUB_SECRET = SecretStr("placeholder")


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _seed_household(
    client: TestClient,
    *,
    ai_enabled: bool = True,
    save_chat: bool = False,
    headers: dict[str, str] | None = None,
) -> None:
    resp = client.put(
        "/api/v1/household",
        headers=headers or {},
        json={
            "members": [{"kind": "adult", "count": 1}, {"kind": "child_u12", "count": 1}],
            "location": {
                "label": "Sector 62, Noida",
                "lat": 28.6271,
                "lon": 77.3716,
                "city": "Noida",
                "admin1": "Uttar Pradesh",
            },
            "settings": {
                "theme": "system",
                "commute_mode": "metro",
                "ai_enabled": ai_enabled,
                "save_chat": save_chat,
                "reduce_motion": False,
            },
        },
    )
    assert resp.status_code == 200


class _StubProvider:
    def __init__(
        self,
        name: str,
        *,
        reply: BaseModel | None = None,
        error: ProviderCallError | None = None,
    ) -> None:
        self.name = name
        self.reply = reply
        self.error = error
        self.calls = 0

    async def generate(
        self,
        system: str,
        context: AIContext,
        user: str | None,
        schema: type[BaseModel],
        timeout_s: float = 15,
    ) -> StructuredReply:
        _ = (system, context, user, schema, timeout_s)
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.reply is not None
        return StructuredReply(
            data=self.reply,
            provider="gemini" if self.name == "gemini" else "groq",
            model="stub",
            latency_ms=12,
        )


def _valid_chat_reply(ctx: AIContext, *, needs_doctor_note: bool = False) -> ChatReply:
    return ChatReply(
        schema_version="1.0",
        verdict_level=ctx.verdict.level,
        answer=f"AQI is {ctx.aqi}. Keep play indoors today.",
        data_cited=["aqi", "category", "source"],
        recommendations=[],
        needs_doctor_note=needs_doctor_note,
        out_of_scope=False,
    )


@pytest.mark.anyio
async def test_gateway_fallback_chains() -> None:
    ctx = _sample_context()
    settings = Settings(purvai_mode="local", gemini_api_key=_STUB_SECRET, groq_api_key=_STUB_SECRET)
    good_reply = _valid_chat_reply(ctx)

    # 1. Gemini timeout -> Groq succeeds
    res = await generate_chat_reply(
        settings=settings,
        context=ctx,
        user_message="Should we play outside?",
        ai_enabled=True,
        providers_override=[
            _StubProvider("gemini", error=ProviderCallError("GEMINI_TIMEOUT")),
            _StubProvider("groq", reply=good_reply),
        ],
    )
    assert res.generated_by == "groq"

    # 2. Gemini 429 -> Groq succeeds
    res2 = await generate_chat_reply(
        settings=settings,
        context=ctx,
        user_message="Should we play outside?",
        ai_enabled=True,
        providers_override=[
            _StubProvider("gemini", error=ProviderCallError("GEMINI_ERROR_429")),
            _StubProvider("groq", reply=good_reply),
        ],
    )
    assert res2.generated_by == "groq"

    # 3. Gemini invalid JSON -> Groq succeeds
    res3 = await generate_chat_reply(
        settings=settings,
        context=ctx,
        user_message="Should we play outside?",
        ai_enabled=True,
        providers_override=[
            _StubProvider("gemini", error=ProviderCallError("GEMINI_SCHEMA_ERROR")),
            _StubProvider("groq", reply=good_reply),
        ],
    )
    assert res3.generated_by == "groq"

    # 4. Gemini guard failure -> Groq succeeds
    bad_guard_reply = _valid_chat_reply(ctx).model_copy(update={"verdict_level": "good"})
    res4 = await generate_chat_reply(
        settings=settings,
        context=ctx,
        user_message="Should we play outside?",
        ai_enabled=True,
        providers_override=[
            _StubProvider("gemini", reply=bad_guard_reply),
            _StubProvider("groq", reply=good_reply),
        ],
    )
    assert res4.generated_by == "groq"

    # 5. Both fail -> template
    res5 = await generate_chat_reply(
        settings=settings,
        context=ctx,
        user_message="Should we play outside?",
        ai_enabled=True,
        providers_override=[
            _StubProvider("gemini", error=ProviderCallError("GEMINI_TIMEOUT")),
            _StubProvider("groq", error=ProviderCallError("GROQ_HTTP_500")),
        ],
    )
    assert res5.generated_by == "template"
    assert res5.note == AI_UNAVAILABLE_NOTE


@respx.mock
@pytest.mark.anyio
async def test_gateway_groq_400_json_validate_failed_and_no_keys_zero_http() -> None:
    ctx = _sample_context()

    # Groq 400 json_validate_failed falls back to template cleanly
    groq_route = respx.post(GROQ_CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            400,
            json={"error": {"code": "json_validate_failed", "message": "failed"}},
        )
    )
    settings_groq = Settings(purvai_mode="local", gemini_api_key=None, groq_api_key=_STUB_SECRET)
    res_400 = await generate_chat_reply(
        settings=settings_groq,
        context=ctx,
        user_message="Should we go out?",
        ai_enabled=True,
    )
    assert groq_route.call_count == 1
    assert res_400.generated_by == "template"
    assert res_400.note == AI_UNAVAILABLE_NOTE

    # No keys -> template with zero HTTP calls
    groq_route.reset()
    no_keys = Settings(purvai_mode="local", gemini_api_key=None, groq_api_key=None)
    res_none = await generate_chat_reply(
        settings=no_keys,
        context=ctx,
        user_message="Should we go out?",
        ai_enabled=True,
    )
    assert groq_route.call_count == 0
    assert res_none.generated_by == "template"

    # ai_enabled=False -> template with zero provider calls
    stub: list[LLMProvider] = [_StubProvider("gemini", reply=_valid_chat_reply(ctx))]
    res_off = await generate_chat_reply(
        settings=Settings(purvai_mode="local", gemini_api_key=_STUB_SECRET),
        context=ctx,
        user_message="Should we go out?",
        ai_enabled=False,
        providers_override=stub,
    )
    assert res_off.generated_by == "template"
    assert res_off.note == AI_DISABLED_NOTE
    assert stub[0].calls == 0  # type: ignore[attr-defined]


@pytest.mark.parametrize("keyword", SYMPTOM_KEYWORDS)
@pytest.mark.anyio
async def test_symptom_keywords_force_doctor_note_even_if_ai_false_and_on_template(
    keyword: str,
) -> None:
    ctx = _sample_context()
    settings = Settings(purvai_mode="local", gemini_api_key=_STUB_SECRET)

    res_ai = await generate_chat_reply(
        settings=settings,
        context=ctx,
        user_message=f"My family member has {keyword} today.",
        ai_enabled=True,
        providers_override=[
            _StubProvider("gemini", reply=_valid_chat_reply(ctx, needs_doctor_note=False))
        ],
    )
    assert isinstance(res_ai.data, ChatReply)
    assert res_ai.data.needs_doctor_note is True

    res_tpl = await generate_chat_reply(
        settings=Settings(purvai_mode="local"),
        context=ctx,
        user_message=f"Feeling {keyword}.",
        ai_enabled=True,
    )
    assert isinstance(res_tpl.data, ChatReply)
    assert res_tpl.data.needs_doctor_note is True


@respx.mock
@freeze_time("2026-11-25T04:10:00Z")
def test_chat_endpoint_validation_409_rate_limit_and_history_logging(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )
    respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_forecast_noida.json"))
    )

    caplog.set_level(logging.INFO, logger="purvai")
    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "chat.db"),
            data_gov_in_api_key="key",  # type: ignore[arg-type]
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        # 409 without household
        assert client.post("/api/v1/chat", json={"message": "Hi"}).status_code == 409

        _seed_household(client, ai_enabled=True, save_chat=False)

        # Length & extra field validation
        assert client.post("/api/v1/chat", json={"message": "   "}).status_code == 422
        assert client.post("/api/v1/chat", json={"message": "x" * 501}).status_code == 422
        assert client.post("/api/v1/chat", json={"message": "a", "extra": 1}).status_code == 422

        # 1 char & 500 chars pass; save_chat=False stores 0 rows
        secret_question = "SecretUserMessageXyz " + ("a" * 479)
        r1 = client.post("/api/v1/chat", json={"message": "a"})
        assert r1.status_code == 200
        r500 = client.post("/api/v1/chat", json={"message": secret_question})
        assert r500.status_code == 200
        assert r500.json()["generated_by"] == "template"

        with Session(app.state.engine) as session:
            assert session.exec(select(Conversation)).all() == []
            assert session.exec(select(Message)).all() == []

        # Enable save_chat -> stores 2 rows per exchange & DELETE clears
        _seed_household(client, ai_enabled=True, save_chat=True)
        r_saved = client.post("/api/v1/chat", json={"message": "Should we go outside?"})
        assert r_saved.status_code == 200
        hist = client.get("/api/v1/conversations")
        assert hist.status_code == 200
        msgs = hist.json()["messages"]
        assert len(msgs) == 2
        assert [m["role"] for m in msgs] == ["user", "assistant"]

        # Verify logs never contain prompt/message/reply text or coordinates
        log_blob = "\n".join(caplog.messages)
        assert "SecretUserMessageXyz" not in log_blob
        assert "Should we go outside?" not in log_blob
        assert "28.6271" not in log_blob

        del_res = client.delete("/api/v1/conversations")
        assert del_res.status_code == 204
        assert client.get("/api/v1/conversations").json()["messages"] == []


def test_chat_429_rate_limit_on_21st_request(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            purvai_mode="local",
            purvai_fake_providers=True,
            database_path=str(tmp_path / "chat_rl.db"),
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        _seed_household(client, ai_enabled=False, save_chat=False)
        for _ in range(20):
            assert client.post("/api/v1/chat", json={"message": "hi"}).status_code == 200
        limited = client.post("/api/v1/chat", json={"message": "hi"})
        assert limited.status_code == 429
        assert "Retry-After" in limited.headers
        assert limited.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


@respx.mock
@freeze_time("2026-11-25T04:10:00Z")
def test_chat_demo_mode_isolation_and_no_past_chat_in_ai_request(tmp_path: Path) -> None:
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )
    respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_forecast_noida.json"))
    )
    captured_prompts: list[str] = []

    def groq_inspect(req: httpx.Request) -> httpx.Response:
        captured_prompts.append(req.content.decode("utf-8"))
        body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "schema_version": "1.0",
                                "verdict_level": "severe",
                                "answer": "AQI is 312. Stay indoors.",
                                "data_cited": ["aqi", "source"],
                                "recommendations": [],
                                "needs_doctor_note": False,
                                "out_of_scope": False,
                            }
                        )
                    }
                }
            ]
        }
        return httpx.Response(200, json=body)

    respx.post(GROQ_CHAT_COMPLETIONS_URL).mock(side_effect=groq_inspect)

    app = create_app(
        Settings(
            purvai_mode="demo",
            database_path=str(tmp_path / "chat_demo.db"),
            data_gov_in_api_key="key",  # type: ignore[arg-type]
            groq_api_key=_STUB_SECRET,
            rate_limit_per_minute=1000,
        )
    )
    id_a = str(uuid.uuid4())
    id_b = str(uuid.uuid4())
    with TestClient(app) as client:
        _seed_household(client, save_chat=True, headers={"X-Purvai-Household": id_a})
        _seed_household(client, save_chat=True, headers={"X-Purvai-Household": id_b})

        assert (
            client.post(
                "/api/v1/chat",
                headers={"X-Purvai-Household": id_a},
                json={"message": "PRIVATE_EARLIER_SECRET_MSG"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/chat",
                headers={"X-Purvai-Household": id_a},
                json={"message": "Second question"},
            ).status_code
            == 200
        )

        # Past chat must NEVER be sent in second AI request
        assert len(captured_prompts) == 2
        assert "PRIVATE_EARLIER_SECRET_MSG" not in captured_prompts[1]

        # Cross-visitor isolation
        assert (
            len(
                client.get("/api/v1/conversations", headers={"X-Purvai-Household": id_a}).json()[
                    "messages"
                ]
            )
            == 2 * 2
        )
        assert (
            client.get("/api/v1/conversations", headers={"X-Purvai-Household": id_b}).json()[
                "messages"
            ]
            == []
        )


@respx.mock
@freeze_time("2026-11-25T04:10:00Z")
def test_plan_wording_tags_cache_reuse_rebuild_and_home_air_ai(tmp_path: Path) -> None:
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )
    respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_forecast_noida.json"))
    )

    app = create_app(
        Settings(
            purvai_mode="local",
            purvai_fake_providers=True,
            database_path=str(tmp_path / "plan_ai.db"),
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        _seed_household(client, ai_enabled=True)
        p1 = client.post("/api/v1/plan", json={"day": "today"})
        assert p1.status_code == 200
        b1 = p1.json()
        assert b1["generated_by"] == "gemini"
        assert b1["summary"]
        assert any(
            item["tag"] == "ai_wording" and item["why"]
            for p in b1["periods"]
            for item in p["items"]
        )

        # Second call within 30 min reuses stored plan without regeneration
        p2 = client.post("/api/v1/plan", json={"day": "today"})
        assert p2.status_code == 200
        assert p2.json()["generated_at"] == b1["generated_at"]

        # rebuild=True regenerates
        p3 = client.post("/api/v1/plan", json={"day": "today", "rebuild": True})
        assert p3.status_code == 200
        assert p3.json()["generated_by"] == "gemini"

        with Session(app.state.engine) as session:
            plans = session.exec(select(DailyPlan)).all()
            assert len(plans) == 1
            assert plans[0].generated_by == "gemini"
            assert any(r.tag == "ai_wording" for r in session.exec(select(PlanItem)).all())

        # Home Air tips also receive ai_wording from IndoorAdvice
        tips = client.get("/api/v1/home-air/tips?lat=28.6271&lon=77.3716").json()
        assert tips["generated_by"] == "gemini"
        assert any(t["tag"] == "ai_wording" for t in tips["tips"])


@pytest.mark.anyio
async def test_gemini_provider_with_mock_genai_client(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _sample_context()
    valid_json = _valid_chat_reply(ctx).model_dump_json()

    class _FakeResp:
        def __init__(self, text: str | None) -> None:
            self.text = text

    class _FakeAsyncModels:
        def __init__(self, outcome: object) -> None:
            self._outcome = outcome

        async def generate_content(self, **_kwargs: object) -> object:
            if isinstance(self._outcome, Exception):
                raise self._outcome
            return self._outcome

    class _FakeClient:
        def __init__(self, outcome: object) -> None:
            self.aio = type("_Aio", (), {"models": _FakeAsyncModels(outcome)})()

    provider = GeminiProvider(
        api_key=_STUB_SECRET.get_secret_value(),
        model="gemini-3.5-flash-lite",
    )

    # 1. Valid reply
    monkeypatch.setattr(
        "app.ai.providers.genai.Client",
        lambda **_kwargs: _FakeClient(_FakeResp(valid_json)),
    )
    ok_res = await provider.generate("sys", ctx, "Can we go out?", ChatReply, timeout_s=5)
    assert ok_res.provider == "gemini"
    assert isinstance(ok_res.data, ChatReply)

    # 2. Timeout
    monkeypatch.setattr(
        "app.ai.providers.genai.Client",
        lambda **_kwargs: _FakeClient(TimeoutError()),
    )
    with pytest.raises(ProviderCallError) as exc_to:
        await provider.generate("sys", ctx, "hi", ChatReply, timeout_s=5)
    assert exc_to.value.reason_code == "GEMINI_TIMEOUT"

    # 3. Empty text
    monkeypatch.setattr(
        "app.ai.providers.genai.Client",
        lambda **_kwargs: _FakeClient(_FakeResp("  ")),
    )
    with pytest.raises(ProviderCallError) as exc_empty:
        await provider.generate("sys", ctx, "hi", ChatReply, timeout_s=5)
    assert exc_empty.value.reason_code == "GEMINI_EMPTY_RESPONSE"

    # 4. Invalid JSON
    monkeypatch.setattr(
        "app.ai.providers.genai.Client",
        lambda **_kwargs: _FakeClient(_FakeResp("{not json")),
    )
    with pytest.raises(ProviderCallError) as exc_bad:
        await provider.generate("sys", ctx, "hi", ChatReply, timeout_s=5)
    assert exc_bad.value.reason_code == "GEMINI_SCHEMA_ERROR"

    # 5. SDK RuntimeError
    monkeypatch.setattr(
        "app.ai.providers.genai.Client",
        lambda **_kwargs: _FakeClient(RuntimeError("boom")),
    )
    with pytest.raises(ProviderCallError) as exc_rt:
        await provider.generate("sys", ctx, "hi", ChatReply, timeout_s=5)
    assert exc_rt.value.reason_code == "GEMINI_ERROR_RuntimeError"


@respx.mock
@freeze_time("2026-11-25T04:10:00Z")
def test_plan_and_indoor_templates_and_wrong_plan_fallback(tmp_path: Path) -> None:
    ctx = _sample_context().model_copy(
        update={
            "plan_periods": [
                AIContextPlanPeriod(
                    period="morning",
                    level="very_poor",
                    aqi=312,
                    action_ids=["stay_indoors"],
                ),
                AIContextPlanPeriod(
                    period="afternoon",
                    level="poor",
                    aqi=240,
                    action_ids=["mostly_indoors"],
                ),
                AIContextPlanPeriod(
                    period="evening",
                    level="moderate",
                    aqi=150,
                    action_ids=["limit_outdoor_exertion"],
                ),
                AIContextPlanPeriod(
                    period="night",
                    level="moderate",
                    aqi=150,
                    action_ids=["limit_outdoor_exertion"],
                ),
            ]
        }
    )
    plan_tpl = build_plan_template(ctx)
    assert isinstance(plan_tpl, DailyPlanWording)
    assert len(plan_tpl.periods) == 4
    indoor_tpl = build_indoor_template(ctx, ventilation_hour="2026-11-25T11:00:00Z")
    assert isinstance(indoor_tpl, IndoorAdvice)
    assert len(indoor_tpl.tips) >= 1

    # Groq returns wrong action set in plan -> falls back to template
    respx.get(CPCB_RESOURCE_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("cpcb_noida_synthetic.json"))
    )
    respx.get(OPEN_METEO_AIR_URL).mock(
        return_value=httpx.Response(200, json=_load_fixture("open_meteo_forecast_noida.json"))
    )
    bad_plan_json = json.dumps(
        {
            "schema_version": "1.0",
            "verdict_level": "severe",
            "summary": "Bad actions",
            "periods": [
                {
                    "period": p,
                    "items": [
                        {
                            "action_id": "normal_activity",
                            "title": "Walk",
                            "why": "AQI 312.",
                            "tag": "ai_wording",
                        }
                    ],
                }
                for p in ("morning", "afternoon", "evening", "night")
            ],
        }
    )
    respx.post(GROQ_CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": bad_plan_json}}]},
        )
    )
    app = create_app(
        Settings(
            purvai_mode="local",
            database_path=str(tmp_path / "plan_fb.db"),
            data_gov_in_api_key="key",  # type: ignore[arg-type]
            groq_api_key=_STUB_SECRET,
            rate_limit_per_minute=1000,
        )
    )
    with TestClient(app) as client:
        _seed_household(client, ai_enabled=True)
        res = client.post("/api/v1/plan", json={"day": "today"})
        assert res.status_code == 200
        body = res.json()
        assert body["generated_by"] == "template"
        assert body["note"] == AI_UNAVAILABLE_NOTE
