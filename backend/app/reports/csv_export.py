"""RFC 4180 CSV export with UTF-8 BOM and formula-injection protection."""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import ActivityLog

# Prefixes that could trigger formula injection in spreadsheet applications
_FORMULA_PREFIXES = ("=", "+", "-", "@", "|", "%")


def _guard(value: str) -> str:
    """Prepend a tab if the value starts with a formula-injection prefix."""
    stripped = value.lstrip()
    if stripped and stripped[0] in _FORMULA_PREFIXES:
        return "\t" + value
    return value


def build_csv(activities: list[ActivityLog], days: int = 7) -> bytes:
    """Return RFC 4180 CSV bytes (UTF-8 BOM) for *activities*."""
    buf = io.StringIO()
    writer = csv.writer(buf, dialect="excel", lineterminator="\r\n")

    # Metadata header rows (commented)
    writer.writerow(["# Purvai Activity Log Export"])
    writer.writerow([f"# Period: last {days} days"])
    writer.writerow(["#"])

    # Column headers
    writer.writerow(
        [
            "id",
            "kind",
            "mode",
            "replaced_mode",
            "distance_km",
            "hours",
            "co2_saved_g",
            "occurred_at",
        ]
    )

    for act in activities:
        writer.writerow(
            [
                str(act.id or ""),
                _guard(act.kind),
                _guard(act.mode or ""),
                _guard(act.replaced_mode or ""),
                str(round(act.distance_km, 4)) if act.distance_km is not None else "",
                str(round(act.hours, 4)) if act.hours is not None else "",
                str(round(act.co2_saved_g, 2)) if act.co2_saved_g is not None else "",
                act.occurred_at or "",
            ]
        )

    # UTF-8 BOM + content
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
