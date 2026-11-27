"""Ask Purvai chat and conversation history endpoints."""

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.ai.context import build_ai_context
from app.ai.gateway import generate_chat_reply
from app.ai.schemas.v1.models import ChatReply, DataCitedLiteral, Recommendation
from app.api.errors import ApiStatusError
from app.api.household import resolve_existing_household
from app.aqi.pipeline import (
    AirForecastResponse,
    get_air_forecast,
    get_air_quality,
    to_utc_iso,
    utc_now,
)
from app.db.models import Conversation, Message, SettingsRecord
from app.providers.base import ProviderError
from app.rules.catalogue import Category

router = APIRouter()


class ChatRequest(BaseModel):
    """Validated body for POST /api/v1/chat."""

    model_config = ConfigDict(extra="forbid")

    message: str

    @field_validator("message")
    @classmethod
    def _validate_message(cls, raw: str) -> str:
        trimmed = raw.strip()
        if not trimmed or len(trimmed) > 500:
            raise ValueError("message must be between 1 and 500 characters after trimming.")
        return trimmed


class ChatResponse(BaseModel):
    """Full POST /api/v1/chat response payload matching docs/API.md and docs/AI_SCHEMAS.md."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"]
    verdict_level: Category
    answer: str
    data_cited: list[DataCitedLiteral]
    recommendations: list[Recommendation]
    needs_doctor_note: bool
    out_of_scope: bool
    generated_by: Literal["gemini", "groq", "template"]
    note: str | None = None
    aqi: int
    category: str
    source_label: Literal["Measured", "Modelled", "Estimated"]
    observed_at: str
    age_minutes: int
    stale: bool
    grap_stage: str | None = None


class ConversationMessageOut(BaseModel):
    """Stored message row returned by GET /api/v1/conversations."""

    model_config = ConfigDict(frozen=True)

    id: int
    role: Literal["user", "assistant"]
    text: str
    generated_by: Literal["user", "gemini", "groq", "template"]
    created_at: str


class ConversationsResponse(BaseModel):
    """Response model for GET /api/v1/conversations."""

    model_config = ConfigDict(frozen=True)

    messages: list[ConversationMessageOut]


@router.post("/chat", response_model=ChatResponse)
async def post_chat(request: Request, body: ChatRequest) -> ChatResponse:
    """Answer an air-safety question using server context, guardrails, and fallback chain."""
    ai_limiter = getattr(request.app.state, "ai_limiter", None)
    if ai_limiter is not None:
        ai_limiter._check_request_limit(request, post_chat, False)

    settings = request.app.state.settings
    engine = request.app.state.engine
    household_header = request.headers.get("X-Purvai-Household")

    with Session(engine) as session:
        household, member_kinds, primary_loc = resolve_existing_household(request, session)

        try:
            air = await get_air_quality(
                session,
                settings=settings,
                lat=primary_loc.lat,
                lon=primary_loc.lon,
                household_header=household_header,
            )
        except ProviderError as exc:
            raise ApiStatusError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="PROVIDER_UNAVAILABLE",
                message="Air quality data is temporarily unavailable. Please try again shortly.",
            ) from exc

        forecast: AirForecastResponse | None = None
        try:
            forecast = await get_air_forecast(
                session,
                settings=settings,
                lat=primary_loc.lat,
                lon=primary_loc.lon,
                hours=12,
            )
        except ProviderError:
            forecast = None

        now = utc_now()
        context = build_ai_context(
            air=air,
            forecast=forecast,
            member_kinds=member_kinds,
            city=primary_loc.city,
            now_utc=now,
        )

        settings_row = session.get(SettingsRecord, household.id)
        ai_enabled = bool(settings_row.ai_enabled) if settings_row is not None else True
        save_chat = bool(settings_row.save_chat) if settings_row is not None else False

        gateway_res = await generate_chat_reply(
            settings=settings,
            context=context,
            user_message=body.message,
            ai_enabled=ai_enabled,
        )
        assert isinstance(gateway_res.data, ChatReply)
        reply = gateway_res.data

        if save_chat:
            convo = session.exec(
                select(Conversation)
                .where(Conversation.household_id == household.id)
                .order_by(col(Conversation.id).asc())
            ).first()
            if convo is None:
                convo = Conversation(
                    household_id=household.id,
                    started_at=to_utc_iso(now),
                )
                session.add(convo)
                session.flush()
            assert convo.id is not None
            ts_iso = to_utc_iso(now)
            session.add(
                Message(
                    conversation_id=convo.id,
                    role="user",
                    text=body.message[:500],
                    generated_by="user",
                    created_at=ts_iso,
                )
            )
            session.add(
                Message(
                    conversation_id=convo.id,
                    role="assistant",
                    text=reply.answer[:600],
                    generated_by=gateway_res.generated_by,
                    created_at=ts_iso,
                )
            )
            session.commit()

        return ChatResponse(
            schema_version=reply.schema_version,
            verdict_level=reply.verdict_level,
            answer=reply.answer,
            data_cited=reply.data_cited,
            recommendations=reply.recommendations,
            needs_doctor_note=reply.needs_doctor_note,
            out_of_scope=reply.out_of_scope,
            generated_by=gateway_res.generated_by,
            note=gateway_res.note,
            aqi=air.aqi,
            category=air.category,
            source_label=air.source_label,
            observed_at=air.observed_at,
            age_minutes=air.age_minutes,
            stale=air.stale,
            grap_stage=air.grap.stage if air.grap is not None else None,
        )


@router.get("/conversations", response_model=ConversationsResponse)
async def get_conversations(request: Request) -> ConversationsResponse:
    """Return the last 50 saved chat messages for the household, oldest first."""
    engine = request.app.state.engine
    with Session(engine) as session:
        household, _, _ = resolve_existing_household(request, session)
        rows = session.exec(
            select(Message)
            .join(Conversation, col(Message.conversation_id) == col(Conversation.id))
            .where(col(Conversation.household_id) == household.id)
            .order_by(col(Message.id).desc())
            .limit(50)
        ).all()

        ordered = list(reversed(rows))
        return ConversationsResponse(
            messages=[
                ConversationMessageOut(
                    id=row.id or 0,
                    role="user" if row.role == "user" else "assistant",
                    text=row.text,
                    generated_by=(
                        "user"
                        if row.generated_by == "user"
                        else "gemini"
                        if row.generated_by == "gemini"
                        else "groq"
                        if row.generated_by == "groq"
                        else "template"
                    ),
                    created_at=row.created_at,
                )
                for row in ordered
            ]
        )


@router.delete("/conversations", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversations(request: Request) -> Response:
    """Delete all saved conversations and messages for the household."""
    engine = request.app.state.engine
    with Session(engine) as session:
        household, _, _ = resolve_existing_household(request, session)
        session.exec(delete(Conversation).where(col(Conversation.household_id) == household.id))
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
