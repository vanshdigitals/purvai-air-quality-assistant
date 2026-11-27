"""AI gateway implementing Gemini -> Groq -> deterministic template fallback chain."""

import json
import logging
import time
from typing import Literal, cast

import httpx
from pydantic import BaseModel, ConfigDict

from app.ai.guard import validate_ai_reply
from app.ai.providers import (
    FakeLLMProvider,
    GeminiProvider,
    GroqProvider,
    LLMProvider,
    ProviderCallError,
)
from app.ai.schemas.v1.models import (
    AIContext,
    ChatReply,
    DailyPlanWording,
    IndoorAdvice,
)
from app.ai.schemas.v1.prompts import (
    CHAT_SYSTEM_INSTRUCTION,
    INDOOR_SYSTEM_INSTRUCTION,
    PLAN_SYSTEM_INSTRUCTION,
)
from app.ai.templates import (
    AI_DISABLED_NOTE,
    AI_UNAVAILABLE_NOTE,
    build_chat_template,
    build_indoor_template,
    build_plan_template,
    has_symptom_keywords,
)
from app.config import Settings

logger = logging.getLogger("purvai")


class GatewayResult(BaseModel):
    """Guarded AI or fallback template result with source metadata."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: BaseModel
    generated_by: Literal["gemini", "groq", "template"]
    guard_code: str | None = None
    note: str | None = None
    latency_ms: int = 0
    primary_provider_ms: int = 0
    fallback_provider_ms: int = 0
    guard_ms: int = 0


def _log_ai_event(*, provider: str, latency_ms: int, outcome: str) -> None:
    """Emit structured AI telemetry without prompts, user text, reply text, flags, or keys."""
    logger.info(
        json.dumps(
            {
                "event": "ai_gateway",
                "provider": provider,
                "latency_ms": latency_ms,
                "outcome": outcome,
            }
        )
    )


def _select_providers(
    settings: Settings,
    *,
    allowed_tip_ids: list[str] | None = None,
    groq_http_client: httpx.AsyncClient | None = None,
) -> list[LLMProvider]:
    if settings.purvai_fake_providers:
        return [FakeLLMProvider()]

    providers: list[LLMProvider] = []
    if settings.gemini_api_key is not None:
        providers.append(
            GeminiProvider(
                api_key=settings.gemini_api_key.get_secret_value(),
                model=settings.ai_model,
                allowed_tip_ids=allowed_tip_ids,
            )
        )
    if settings.groq_api_key is not None:
        providers.append(
            GroqProvider(
                api_key=settings.groq_api_key.get_secret_value(),
                model=settings.ai_fallback_model,
                allowed_tip_ids=allowed_tip_ids,
                client=groq_http_client,
            )
        )
    return providers


async def _run_chain[TModel: (ChatReply, DailyPlanWording, IndoorAdvice)](
    *,
    settings: Settings,
    system: str,
    context: AIContext,
    user: str | None,
    schema: type[TModel],
    ai_enabled: bool,
    allowed_tip_ids: set[str] | None = None,
    providers_override: list[LLMProvider] | None = None,
    groq_http_client: httpx.AsyncClient | None = None,
) -> tuple[
    TModel | None,
    Literal["gemini", "groq", "template"],
    str | None,
    int,
    dict[str, int],
]:
    stage_ms: dict[str, int] = {
        "primary_provider_ms": 0,
        "fallback_provider_ms": 0,
        "guard_ms": 0,
    }
    if not ai_enabled:
        _log_ai_event(provider="none", latency_ms=0, outcome="ai_disabled")
        return None, "template", None, 0, stage_ms

    tip_list = sorted(allowed_tip_ids) if allowed_tip_ids else None
    providers = (
        providers_override
        if providers_override is not None
        else _select_providers(
            settings,
            allowed_tip_ids=tip_list,
            groq_http_client=groq_http_client,
        )
    )

    if not providers:
        _log_ai_event(provider="none", latency_ms=0, outcome="no_keys")
        return None, "template", None, 0, stage_ms

    last_guard_code: str | None = None
    for idx, provider in enumerate(providers):
        timing_key = "primary_provider_ms" if idx == 0 else "fallback_provider_ms"
        try:
            structured = await provider.generate(
                system=system,
                context=context,
                user=user,
                schema=schema,
                timeout_s=settings.ai_timeout_s,
            )
            stage_ms[timing_key] += structured.latency_ms
        except ProviderCallError as exc:
            stage_ms[timing_key] += exc.latency_ms
            _log_ai_event(
                provider=provider.name,
                latency_ms=exc.latency_ms,
                outcome=exc.reason_code,
            )
            continue

        guard_start = time.perf_counter()
        ok, guard_code = validate_ai_reply(
            structured.data,
            context,
            user_message=user,
            allowed_tip_ids=allowed_tip_ids,
        )
        stage_ms["guard_ms"] += int((time.perf_counter() - guard_start) * 1000)
        if not ok:
            last_guard_code = guard_code
            _log_ai_event(
                provider=provider.name,
                latency_ms=structured.latency_ms,
                outcome=guard_code or "GUARD_FAILED",
            )
            continue

        _log_ai_event(
            provider=provider.name,
            latency_ms=structured.latency_ms,
            outcome="ok",
        )
        return (
            cast(TModel, structured.data),
            structured.provider,
            None,
            structured.latency_ms,
            stage_ms,
        )

    return None, "template", last_guard_code, 0, stage_ms


async def generate_chat_reply(
    *,
    settings: Settings,
    context: AIContext,
    user_message: str,
    ai_enabled: bool,
    providers_override: list[LLMProvider] | None = None,
    groq_http_client: httpx.AsyncClient | None = None,
) -> GatewayResult:
    """Run Ask Purvai gateway and enforce SAF-04 symptom note post-guard."""
    ai_data, generated_by, guard_code, latency_ms, stage_ms = await _run_chain(
        settings=settings,
        system=CHAT_SYSTEM_INSTRUCTION,
        context=context,
        user=user_message,
        schema=ChatReply,
        ai_enabled=ai_enabled,
        providers_override=providers_override,
        groq_http_client=groq_http_client,
    )

    if ai_data is None:
        tpl = build_chat_template(context, user_message=user_message, ai_disabled=not ai_enabled)
        return GatewayResult(
            data=tpl,
            generated_by="template",
            guard_code=guard_code,
            note=AI_DISABLED_NOTE if not ai_enabled else AI_UNAVAILABLE_NOTE,
            latency_ms=0,
            **stage_ms,
        )

    # SAF-04: symptoms are in scope; server enforces needs_doctor_note and clears out_of_scope
    if has_symptom_keywords(user_message) or ai_data.needs_doctor_note:
        if not ai_data.needs_doctor_note or ai_data.out_of_scope:
            ai_data = ai_data.model_copy(update={"needs_doctor_note": True, "out_of_scope": False})

    return GatewayResult(
        data=ai_data,
        generated_by=generated_by,
        guard_code=None,
        note=None,
        latency_ms=latency_ms,
        **stage_ms,
    )


async def generate_plan_wording(
    *,
    settings: Settings,
    context: AIContext,
    ai_enabled: bool,
    providers_override: list[LLMProvider] | None = None,
    groq_http_client: httpx.AsyncClient | None = None,
) -> GatewayResult:
    """Run Daily Protection Plan AI wording gateway with fallback to template/rules."""
    ai_data, generated_by, guard_code, latency_ms, stage_ms = await _run_chain(
        settings=settings,
        system=PLAN_SYSTEM_INSTRUCTION,
        context=context,
        user=None,
        schema=DailyPlanWording,
        ai_enabled=ai_enabled,
        providers_override=providers_override,
        groq_http_client=groq_http_client,
    )

    if ai_data is None:
        tpl = build_plan_template(context)
        return GatewayResult(
            data=tpl,
            generated_by="template",
            guard_code=guard_code,
            note=AI_DISABLED_NOTE if not ai_enabled else AI_UNAVAILABLE_NOTE,
            latency_ms=0,
            **stage_ms,
        )

    return GatewayResult(
        data=ai_data,
        generated_by=generated_by,
        guard_code=None,
        note=None,
        latency_ms=latency_ms,
        **stage_ms,
    )


async def generate_indoor_advice(
    *,
    settings: Settings,
    context: AIContext,
    allowed_tip_ids: set[str],
    ventilation_hour: str | None,
    ai_enabled: bool,
    providers_override: list[LLMProvider] | None = None,
    groq_http_client: httpx.AsyncClient | None = None,
) -> GatewayResult:
    """Run optional Home Air IndoorAdvice wording gateway."""
    ai_data, generated_by, guard_code, latency_ms, stage_ms = await _run_chain(
        settings=settings,
        system=INDOOR_SYSTEM_INSTRUCTION,
        context=context,
        user=None,
        schema=IndoorAdvice,
        ai_enabled=ai_enabled,
        allowed_tip_ids=allowed_tip_ids,
        providers_override=providers_override,
        groq_http_client=groq_http_client,
    )

    if ai_data is None:
        tpl = build_indoor_template(context, ventilation_hour=ventilation_hour)
        return GatewayResult(
            data=tpl,
            generated_by="template",
            guard_code=guard_code,
            note=AI_DISABLED_NOTE if not ai_enabled else AI_UNAVAILABLE_NOTE,
            latency_ms=0,
            **stage_ms,
        )

    return GatewayResult(
        data=ai_data,
        generated_by=generated_by,
        guard_code=None,
        note=None,
        latency_ms=latency_ms,
        **stage_ms,
    )
