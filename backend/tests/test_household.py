"""Tests for GET/PUT /api/v1/household, demo header scoping, and 24-hour purge."""

import uuid
from pathlib import Path

from app.config import Settings
from app.db.models import Household, Location
from app.main import create_app
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlmodel import Session, select


def _sample_payload(
    *,
    label: str = "Sector 62, Noida",
    lat: float = 28.6271,
    lon: float = 77.3716,
    city: str | None = "Noida",
    admin1: str | None = "Uttar Pradesh",
    theme: str = "system",
    commute: str = "metro",
) -> dict[str, object]:
    return {
        "members": [
            {"kind": "adult", "count": 2},
            {"kind": "child_u12", "count": 1},
            {"kind": "adult_65p", "count": 1},
        ],
        "location": {
            "label": label,
            "lat": lat,
            "lon": lon,
            "city": city,
            "admin1": admin1,
        },
        "settings": {
            "theme": theme,
            "commute_mode": commute,
            "ai_enabled": True,
            "save_chat": False,
            "reduce_motion": False,
        },
    }


def test_local_household_create_read_replace_and_primary_location_switch(tmp_path: Path) -> None:
    settings = Settings(
        purvai_mode="local",
        database_path=str(tmp_path / "hh_local.db"),
        rate_limit_per_minute=1000,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        missing = client.get("/api/v1/household")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "HOUSEHOLD_NOT_FOUND"

        created = client.put(
            "/api/v1/household",
            json=_sample_payload(lat=28.627123, lon=77.371698),
        )
        assert created.status_code == 200
        body = created.json()
        assert body["mode"] == "local"
        assert body["location"]["lat"] == 28.6271
        assert body["location"]["lon"] == 77.3717
        assert body["settings"]["theme"] == "system"

        fetched = client.get("/api/v1/household")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == body["id"]

        # Update location -> previous location kept as non-primary
        updated = client.put(
            "/api/v1/household",
            json=_sample_payload(
                label="Civil Lines, Prayagraj",
                lat=25.4489,
                lon=81.8333,
                city="Prayagraj",
                theme="dark",
                commute="none",
            ),
        )
        assert updated.status_code == 200
        assert updated.json()["id"] == body["id"]
        assert updated.json()["location"]["label"] == "Civil Lines, Prayagraj"
        assert updated.json()["settings"]["theme"] == "dark"
        assert updated.json()["settings"]["commute_mode"] == "none"

        with Session(app.state.engine) as session:
            locs = session.exec(select(Location).where(Location.household_id == body["id"])).all()
            assert len(locs) == 2
            assert sum(1 for loc in locs if loc.is_primary) == 1


def test_household_validation_errors(local_client: TestClient) -> None:
    # Extra field forbidden
    bad_extra = _sample_payload()
    bad_extra["extra_field"] = "nope"
    assert local_client.put("/api/v1/household", json=bad_extra).status_code == 422

    # Zero total members rejected
    zero_members = _sample_payload()
    zero_members["members"] = [{"kind": "adult", "count": 0}]
    assert local_client.put("/api/v1/household", json=zero_members).status_code == 422

    # Duplicate member kinds rejected
    dup_members = _sample_payload()
    dup_members["members"] = [{"kind": "adult", "count": 1}, {"kind": "adult", "count": 1}]
    assert local_client.put("/api/v1/household", json=dup_members).status_code == 422

    # Outside India rejected with UNSUPPORTED_REGION
    outside = _sample_payload(lat=51.5072, lon=-0.1276, city="London", admin1=None)
    resp = local_client.put("/api/v1/household", json=outside)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNSUPPORTED_REGION"


def test_demo_household_header_isolation_and_24h_purge(tmp_path: Path) -> None:
    db_file = tmp_path / "hh_demo.db"
    id_a = str(uuid.uuid4())
    id_b = str(uuid.uuid4())

    with freeze_time("2026-11-25T10:00:00Z"):
        app = create_app(
            Settings(
                purvai_mode="demo",
                database_path=str(db_file),
                rate_limit_per_minute=1000,
            )
        )
        with TestClient(app) as client:
            no_hdr = client.get("/api/v1/household")
            assert no_hdr.status_code == 400
            assert no_hdr.json()["error"]["code"] == "HOUSEHOLD_HEADER_REQUIRED"

            bad_hdr = client.get("/api/v1/household", headers={"X-Purvai-Household": "not-a-uuid"})
            assert bad_hdr.status_code == 400
            assert bad_hdr.json()["error"]["code"] == "HOUSEHOLD_HEADER_REQUIRED"

            assert (
                client.get("/api/v1/household", headers={"X-Purvai-Household": id_a}).status_code
                == 404
            )

            res_a = client.put(
                "/api/v1/household",
                headers={"X-Purvai-Household": id_a},
                json=_sample_payload(label="Noida Home", theme="dark"),
            )
            assert res_a.status_code == 200
            assert res_a.json()["id"] == id_a

            # Household B cannot see Household A
            assert (
                client.get("/api/v1/household", headers={"X-Purvai-Household": id_b}).status_code
                == 404
            )

            res_b = client.put(
                "/api/v1/household",
                headers={"X-Purvai-Household": id_b},
                json=_sample_payload(label="Delhi Home", theme="light"),
            )
            assert res_b.status_code == 200
            assert (
                client.get("/api/v1/household", headers={"X-Purvai-Household": id_a}).json()[
                    "location"
                ]["label"]
                == "Noida Home"
            )
            assert (
                client.get("/api/v1/household", headers={"X-Purvai-Household": id_b}).json()[
                    "location"
                ]["label"]
                == "Delhi Home"
            )

    # 25 hours later, restart purges expired demo households
    with freeze_time("2026-11-26T11:00:00Z"):
        app2 = create_app(
            Settings(
                purvai_mode="demo",
                database_path=str(db_file),
                rate_limit_per_minute=1000,
            )
        )
        with TestClient(app2) as client2:
            assert (
                client2.get("/api/v1/household", headers={"X-Purvai-Household": id_a}).status_code
                == 404
            )
            with Session(app2.state.engine) as session:
                assert session.exec(select(Household)).all() == []
