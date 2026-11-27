"""PDF and CSV report generation endpoints (FR-13)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from sqlmodel import Session

from app.api.errors import ApiStatusError
from app.api.household import resolve_existing_household
from app.api.rate_limit import limiter
from app.db.models import Report
from app.impact import service as impact_svc
from app.reports.csv_export import build_csv
from app.reports.pdf import build_pdf

router = APIRouter()


def _validate_days(days: int) -> int:
    if days not in (1, 7):
        raise ApiStatusError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message="days must be 1 or 7.",
        )
    return days


@router.post("/reports/pdf")
@limiter.limit("10/minute")
async def post_report_pdf(request: Request, days: int = 7) -> Response:
    """Generate a PDF air-quality & CO2 impact report and persist metadata."""
    _validate_days(days)
    engine = request.app.state.engine
    with Session(engine) as session:
        household, _, _ = resolve_existing_household(request, session)
        activities = impact_svc.get_activities(session, household, days=days)
        summary = impact_svc.get_summary(session, household, days=days)
        payload = build_pdf(household, activities, summary, days=days)
        session.add(
            Report(
                household_id=household.id,
                format="pdf",
                days=days,
                byte_size=len(payload),
            )
        )
        session.commit()
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="purvai-report-{days}d.pdf"'},
    )


@router.post("/reports/csv")
@limiter.limit("10/minute")
async def post_report_csv(request: Request, days: int = 7) -> Response:
    """Generate an RFC 4180 CSV activity export with UTF-8 BOM and persist metadata."""
    _validate_days(days)
    engine = request.app.state.engine
    with Session(engine) as session:
        household, _, _ = resolve_existing_household(request, session)
        activities = impact_svc.get_activities(session, household, days=days)
        payload = build_csv(activities, days=days)
        session.add(
            Report(
                household_id=household.id,
                format="csv",
                days=days,
                byte_size=len(payload),
            )
        )
        session.commit()
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="purvai-report-{days}d.csv"'},
    )
