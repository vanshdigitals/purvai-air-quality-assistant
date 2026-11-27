"""Tests for PDF and CSV report generation (FR-13)."""

import pytest
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


@pytest.mark.parametrize("days", [1, 7])
def test_post_report_pdf_variants_and_metadata(local_client: TestClient, days: int) -> None:
    """POST /reports/pdf returns valid %PDF- bytes, page count, and records metadata."""
    _seed_household_and_activity(local_client)

    resp = local_client.post(f"/api/v1/reports/pdf?days={days}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content.startswith(b"%PDF-")
    # fpdf2 writes /Count 1 for 1 page and FlateDecode-compresses content streams
    assert b"/Type /Page" in resp.content
    assert b"/Count 1" in resp.content
    import re
    import zlib

    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", resp.content, flags=re.DOTALL)
    decompressed = b"".join(zlib.decompress(s) for s in streams)
    assert b"Purvai Air Quality Report" in decompressed
    assert f"last {days} days".encode() in decompressed

    engine = local_client.app.state.engine  # type: ignore[union-attr]
    with Session(engine) as session:
        rows = session.exec(select(Report)).all()
    assert len(rows) == 1
    assert rows[0].format == "pdf"
    assert rows[0].days == days
    assert rows[0].byte_size == len(resp.content)


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_post_report_csv_quoting_bom_and_formula_guard(
    local_client: TestClient,
    prefix: str,
) -> None:
    """POST /reports/csv returns UTF-8 BOM RFC 4180 CSV, quotes commas, and guards formulas."""
    _seed_household_and_activity(local_client)
    inj = local_client.post(
        "/api/v1/activities",
        json={"kind": f"{prefix}SUM(A1),test", "hours": 1.0},
    )
    assert inj.status_code == 201

    resp = local_client.post("/api/v1/reports/csv?days=7")
    assert resp.status_code == 200
    assert resp.content.startswith(b"\xef\xbb\xbf")
    text = resp.content.decode("utf-8-sig")
    assert "Purvai Activity Log Export" in text
    assert f'"\t{prefix}SUM(A1),test"' in text


def test_reports_invalid_days_returns_400(local_client: TestClient) -> None:
    """days outside (1, 7) returns 400."""
    _seed_household_and_activity(local_client)
    resp = local_client.post("/api/v1/reports/pdf?days=30")
    assert resp.status_code == 400
