"""Tests for SQLite backup, restore (local only), and DELETE /data (FR-15, FR-16)."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _seed_household(
    client: TestClient,
    count: int = 2,
    headers: dict[str, str] | None = None,
) -> None:
    resp = client.put(
        "/api/v1/household",
        headers=headers or {},
        json={
            "members": [{"kind": "adult", "count": count}],
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


def test_backup_retention_and_restore_roundtrip_local(local_client: TestClient) -> None:
    """Create >7 backups (retains last 7), verify integrity, mutate, restore -> original."""
    _seed_household(local_client, count=2)

    filenames: list[str] = []
    for _ in range(9):
        b_resp = local_client.post("/api/v1/db/backup")
        assert b_resp.status_code == 200
        filenames.append(b_resp.json()["filename"])

    list_resp = local_client.get("/api/v1/db/backups")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 7

    target = filenames[-1]
    _seed_household(local_client, count=7)
    assert local_client.get("/api/v1/household").json()["members"][0]["count"] == 7

    r_resp = local_client.post("/api/v1/db/restore", json={"filename": target})
    assert r_resp.status_code == 200
    assert r_resp.json()["status"] == "ok"
    assert local_client.get("/api/v1/household").json()["members"][0]["count"] == 2


def test_restore_rejects_corrupted_and_wrong_alembic_version(local_client: TestClient) -> None:
    """Corrupted backup returns 422; wrong alembic_version returns 409."""
    _seed_household(local_client, count=2)
    db_path = Path(local_client.app.state.settings.resolved_database_path)  # type: ignore[union-attr]
    bdir = db_path.parent / "backups"
    bdir.mkdir(parents=True, exist_ok=True)

    # Corrupted file
    (bdir / "corrupt.db").write_bytes(b"not a sqlite database")
    assert (
        local_client.post("/api/v1/db/restore", json={"filename": "corrupt.db"}).status_code == 422
    )

    # Valid SQLite DB with wrong alembic_version
    wrong_ver = bdir / "wrong_ver.db"
    conn = sqlite3.connect(str(wrong_ver))
    conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
    conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0001_initial_schema')")
    conn.commit()
    conn.close()
    assert (
        local_client.post("/api/v1/db/restore", json={"filename": "wrong_ver.db"}).status_code
        == 409
    )


def test_backup_and_restore_blocked_in_demo_mode(demo_client: TestClient) -> None:
    """Backup and restore endpoints return 503 in demo mode."""
    assert demo_client.post("/api/v1/db/backup").status_code == 503
    assert demo_client.get("/api/v1/db/backups").status_code == 503
    assert (
        demo_client.post("/api/v1/db/restore", json={"filename": "purvai-x.db"}).status_code == 503
    )


@pytest.mark.parametrize(
    "bad_name",
    ["../evil.db", "C:\\Windows\\evil.db", "/etc/passwd.db", "bad name.txt"],
)
def test_restore_path_traversal_rejected(local_client: TestClient, bad_name: str) -> None:
    """Path traversal or invalid pattern in restore filename returns 400."""
    resp = local_client.post("/api/v1/db/restore", json={"filename": bad_name})
    assert resp.status_code == 400


def test_clear_data_confirm_and_other_household_untouched(
    local_client: TestClient,
    demo_client: TestClient,
) -> None:
    """DELETE /data requires {"confirm": "DELETE"} and leaves other demo households untouched."""
    _seed_household(local_client, count=2)
    assert local_client.request("DELETE", "/api/v1/data", json={"confirm": "no"}).status_code == 400
    ok = local_client.request("DELETE", "/api/v1/data", json={"confirm": "DELETE"})
    assert ok.status_code == 200 and ok.json()["deleted"] is True
    assert local_client.get("/api/v1/household").status_code in (404, 409)

    h_a = {"X-Purvai-Household": "11111111-1111-4111-8111-111111111111"}
    h_b = {"X-Purvai-Household": "22222222-2222-4222-8222-222222222222"}
    _seed_household(demo_client, count=2, headers=h_a)
    _seed_household(demo_client, count=4, headers=h_b)
    assert (
        demo_client.request(
            "DELETE", "/api/v1/data", headers=h_a, json={"confirm": "DELETE"}
        ).status_code
        == 200
    )
    assert demo_client.get("/api/v1/household", headers=h_b).json()["members"][0]["count"] == 4
