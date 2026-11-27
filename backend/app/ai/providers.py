"""LLM providers (Gemini via google-genai, Groq via httpx, and local FakeLLMProvider)."""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Protocol

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.ai.schemas.v1.models import (
    AIContext,
    ChatReply,
    DailyPlanWording,
    IndoorAdvice,
    StructuredReply,
    build_provider_json_schema,
)
from app.ai.schemas.v1.prompts import (
    build_chat_prompt,
    build_indoor_prompt,
    build_plan_prompt,
)
from app.config import REPO_ROOT

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
AI_FIXTURES_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "ai"


class ProviderCallError(Exception):
    """Raised when an AI provider call fails or produces invalid schema output."""

    def __init__(self, reason_code: str, *, latency_ms: int = 0) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.latency_ms = latency_ms


class LLMProvider(Protocol):
    """Unified interface for Purvai LLM providers."""

    name: str

    async def generate(
        self,
        system: str,
        context: AIContext,
        user: str | None,
        schema: type[BaseModel],
        timeout_s: float = 15,
    ) -> StructuredReply: ...


def _render_user_contents(
    context: AIContext,
    user: str | None,
    schema: type[BaseModel],
    allowed_tip_ids: list[str] | None = None,
) -> str:
    if schema is ChatReply:
        return build_chat_prompt(context, user or "")
    if schema is DailyPlanWording:
        return build_plan_prompt(context)
    if schema is IndoorAdvice:
        return build_indoor_prompt(context, allowed_tip_ids or [])
    return build_plan_prompt(context)


class GeminiProvider:
    """Google Gemini provider via installed google-genai SDK."""

    name: str = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-3.5-flash-lite",
        allowed_tip_ids: list[str] | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._allowed_tip_ids = allowed_tip_ids

    async def generate(
        self,
        system: str,
        context: AIContext,
        user: str | None,
        schema: type[BaseModel],
        timeout_s: float = 15,
    ) -> StructuredReply:
        start = time.perf_counter()
        prompt = _render_user_contents(context, user, schema, self._allowed_tip_ids)
        provider_schema = build_provider_json_schema(schema)
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
            response_mime_type="application/json",
            response_json_schema=provider_schema,
        )
        timeout_ms = max(1000, int(timeout_s * 1000))
        client = genai.Client(
            api_key=self._api_key,
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                ),
                timeout=timeout_s,
            )
        except TimeoutError as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            raise ProviderCallError("GEMINI_TIMEOUT", latency_ms=elapsed) from exc
        except Exception as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            raise ProviderCallError(
                f"GEMINI_ERROR_{type(exc).__name__}", latency_ms=elapsed
            ) from exc

        elapsed = int((time.perf_counter() - start) * 1000)
        raw_text = getattr(response, "text", None)
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ProviderCallError("GEMINI_EMPTY_RESPONSE", latency_ms=elapsed)

        try:
            parsed = schema.model_validate_json(raw_text)
        except (ValidationError, ValueError) as exc:
            raise ProviderCallError("GEMINI_SCHEMA_ERROR", latency_ms=elapsed) from exc

        return StructuredReply(
            data=parsed,
            provider="gemini",
            model=self.model,
            latency_ms=elapsed,
        )


class GroqProvider:
    """Groq OpenAI-compatible strict JSON schema HTTP provider via httpx."""

    name: str = "groq"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "openai/gpt-oss-20b",
        allowed_tip_ids: list[str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._allowed_tip_ids = allowed_tip_ids
        self._client = client

    async def generate(
        self,
        system: str,
        context: AIContext,
        user: str | None,
        schema: type[BaseModel],
        timeout_s: float = 15,
    ) -> StructuredReply:
        start = time.perf_counter()
        prompt = _render_user_contents(context, user, schema, self._allowed_tip_ids)
        provider_schema = build_provider_json_schema(schema)
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": provider_schema,
                },
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async def _post(http: httpx.AsyncClient) -> httpx.Response:
            return await http.post(
                GROQ_CHAT_COMPLETIONS_URL,
                headers=headers,
                json=payload,
                timeout=timeout_s,
            )

        try:
            if self._client is not None:
                resp = await _post(self._client)
            else:
                async with httpx.AsyncClient(timeout=timeout_s) as owned_client:
                    resp = await _post(owned_client)
        except httpx.TimeoutException as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            raise ProviderCallError("GROQ_TIMEOUT", latency_ms=elapsed) from exc
        except httpx.HTTPError as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            raise ProviderCallError("GROQ_HTTP_ERROR", latency_ms=elapsed) from exc

        elapsed = int((time.perf_counter() - start) * 1000)
        if resp.status_code != 200:
            raise ProviderCallError(f"GROQ_HTTP_{resp.status_code}", latency_ms=elapsed)

        try:
            data = resp.json()
            choices = data.get("choices") or []
            message_obj = choices[0]["message"]
            content = message_obj["content"]
            if not isinstance(content, str):
                raise ValueError("Missing message content string")
            parsed = schema.model_validate_json(content)
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            ValidationError,
            json.JSONDecodeError,
        ) as exc:
            raise ProviderCallError("GROQ_SCHEMA_ERROR", latency_ms=elapsed) from exc

        return StructuredReply(
            data=parsed,
            provider="groq",
            model=self.model,
            latency_ms=elapsed,
        )


class FakeLLMProvider:
    """Offline recorded-fixture AI provider used only when PURVAI_FAKE_PROVIDERS=true."""

    name: str = "gemini"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._dir = fixtures_dir or AI_FIXTURES_DIR
        self.model = "fake-gemini-fixture"

    async def generate(
        self,
        system: str,
        context: AIContext,
        user: str | None,
        schema: type[BaseModel],
        timeout_s: float = 15,
    ) -> StructuredReply:
        _ = (system, timeout_s)
        if schema is ChatReply:
            lower = (user or "").lower()
            if "template" in lower or "fallback" in lower:
                raw = json.loads((self._dir / "chat_guard_fail.json").read_text(encoding="utf-8"))
            else:
                raw = json.loads((self._dir / "chat_valid.json").read_text(encoding="utf-8"))
                # Align top-level verdict_level & action_ids if test fixture is for Noida 312
                if raw.get("verdict_level") != context.verdict.level:
                    raw["verdict_level"] = context.verdict.level
                    raw["recommendations"] = [
                        {
                            "action_id": aid,
                            "title": rec.get("title", "Follow rule guidance"),
                            "why": rec.get("why", f"AQI is {context.aqi}."),
                            "tag": "ai_wording",
                        }
                        for aid, rec in zip(
                            context.verdict.action_ids,
                            raw.get("recommendations", [])
                            or [{"title": "Follow rule guidance", "why": f"AQI is {context.aqi}."}],
                            strict=False,
                        )
                    ]
        elif schema is DailyPlanWording:
            raw = json.loads((self._dir / "plan_valid.json").read_text(encoding="utf-8"))
            raw["verdict_level"] = context.verdict.level
            if context.plan_periods:
                raw["periods"] = [
                    {
                        "period": p.period,
                        "items": [
                            {
                                "action_id": aid,
                                "title": f"Rule action ({p.period})",
                                "why": f"Peak forecast AQI {p.aqi}.",
                                "tag": "ai_wording",
                            }
                            for aid in p.action_ids
                        ],
                    }
                    for p in context.plan_periods
                ]
        elif schema is IndoorAdvice:
            raw = json.loads((self._dir / "indoor_valid.json").read_text(encoding="utf-8"))
            raw["verdict_level"] = context.verdict.level
        else:
            raise ProviderCallError("FAKE_UNSUPPORTED_SCHEMA")

        parsed = schema.model_validate(raw)
        return StructuredReply(
            data=parsed,
            provider="gemini",
            model=self.model,
            latency_ms=1,
        )
