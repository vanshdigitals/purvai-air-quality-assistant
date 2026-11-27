"""PDF report generation using fpdf2 (Latin-1 safe, no external fonts needed)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import ActivityLog, Household

try:
    from fpdf import FPDF

    _FPDF_AVAILABLE = True
except ModuleNotFoundError:
    _FPDF_AVAILABLE = False


def _fpdf_check() -> None:
    if not _FPDF_AVAILABLE:
        raise RuntimeError("fpdf2 is not installed. Add fpdf2 to requirements.txt.")


def _safe(text: str) -> str:
    """Replace non-Latin-1 characters with '?' to avoid FPDF encoding errors."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _utc_days_ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def build_pdf(
    household: Household,
    activities: list[ActivityLog],
    summary: dict[str, object],
    days: int = 7,
) -> bytes:
    """Build a simple 1-page PDF report and return raw bytes."""
    _fpdf_check()

    pdf = FPDF()
    pdf.set_margins(left=15, top=15, right=15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title
    pdf.set_font("Helvetica", style="B", size=18)
    pdf.cell(0, 10, _safe("Purvai Air Quality Report"), new_x="LMARGIN", new_y="NEXT")

    # Subtitle
    pdf.set_font("Helvetica", size=11)
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    subtitle = f"Generated: {now_str}  |  Period: last {days} days"
    pdf.cell(0, 7, _safe(subtitle), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Summary box
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(0, 8, _safe("CO2 Impact Summary"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    trips = summary.get("trips", 0)
    saved_kg = summary.get("co2_saved_kg", 0.0)
    dist = summary.get("distance_km", 0.0)
    pdf.cell(0, 7, _safe(f"  Trips logged: {trips}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, _safe(f"  CO2 saved: {saved_kg} kg"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, _safe(f"  Distance: {dist} km"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Bar chart (ASCII-style horizontal bars using filled cells)
    if activities:
        pdf.set_font("Helvetica", style="B", size=12)
        pdf.cell(0, 8, _safe("Activity Log"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=9)

        # Header row
        col_w = [22, 22, 22, 22, 25, 30, 37]
        headers = ["Date", "Kind", "Mode", "Replaced", "Dist (km)", "CO2 saved (g)", "Occurred at"]
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 6, _safe(h), border=1)
        pdf.ln()

        for act in activities[:30]:  # max 30 rows
            date_str = (act.occurred_at or "")[:10]
            mode_str = act.mode or "-"
            rep_str = act.replaced_mode or "-"
            dist_str = str(round(act.distance_km, 1)) if act.distance_km is not None else "-"
            co2_str = str(round(act.co2_saved_g, 0)) if act.co2_saved_g is not None else "-"
            occurred = (act.occurred_at or "")[:19]
            vals = [date_str, act.kind[:8], mode_str[:8], rep_str[:8], dist_str, co2_str, occurred]
            for i, val in enumerate(vals):
                pdf.cell(col_w[i], 6, _safe(val), border=1)
            pdf.ln()

    # Footer
    pdf.ln(6)
    pdf.set_font("Helvetica", size=8)
    footer = "Purvai v0.1.0 | docs/ARCHITECTURE.md | ITF-2023 lifecycle CO2e factors"
    pdf.cell(0, 5, _safe(footer), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
