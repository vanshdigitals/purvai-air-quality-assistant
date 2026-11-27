"""Tests for PDF and CSV report generation (FR-13)."""

from app.db.models import Report
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _seed_household_and_activity(client: TestClient) -> None:
    resp = client.put(
        "/api/v1/household",
        json={
            "members": [{"kind": "adult", "count": 1}],
            "location": {
                "label": "Noida",
                "lat": 28.6271,
                "lon": 77.3716,
                "city": "Noida",
            },
            "settings": {
                "theme": "system",
                "commute_mode": "metro",
                "ai_enabled": False,
                "save_chat": False,
                "reduce_motion": False,
            },
        },
    )
    assert resp.status_code == 200
    act = client.post(
        "/api/v1/activities",
        json={
            "kind": "commute",
            "mode": "metro",
            "replaced_mode": "car_petrol",
            "distance_km": 8.0,
        },
    )
    assert act.status_code == 201


def test_post_report_pdf_and_metadata(local_client: TestClient) -> None:
    """POST /reports/pdf returns valid %PDF- bytes and records report metadata."""
    _seed_household_and_activity(local_client)

    resp = local_client.post("/api/v1/reports/pdf?days=7")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content.startswith(b"%PDF-")

    engine = local_client.app.state.engine  # type: ignore[union-attr]
    with Session(engine) as session:
        rows = session.exec(select(Report)).all()
    assert len(rows) == 1
    assert rows[0].format == "pdf"
    assert rows[0].days == 7
    assert rows[0].byte_size == len(resp.content)


def test_post_report_csv_bom_and_formula_guard(local_client: TestClient) -> None:
    """POST /reports/csv returns UTF-8 BOM CSV and neutralizes formula prefixes."""
    _seed_household_and_activity(local_client)
    # Log an activity with a formula-like kind to verify CSV injection guard
    inj = local_client.post(
        "/api/v1/activities",
        json={"kind": "=cmd|' /C calc'!A0", "hours": 1.0},
    )
    assert inj.status_code == 201

    resp = local_client.post("/api/v1/reports/csv?days=7")
    assert resp.status_code == 200
    assert resp.content.startswith(b"\xef\xbb\xbf")
    text = resp.content.decode("utf-8-sig")
    assert "Purvai Activity Log Export" in text
    assert "\t=cmd" in text


def test_reports_invalid_days_returns_400(local_client: TestClient) -> None:
    """days outside (1, 7) returns 400."""
    _seed_household_and_activity(local_client)
    resp = local_client.post("/api/v1/reports/pdf?days=30")
    assert resp.status_code == 400
