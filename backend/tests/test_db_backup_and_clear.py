"""Tests for SQLite backup, restore (local only), and DELETE /data (FR-15, FR-16)."""

from fastapi.testclient import TestClient


def _seed_household(client: TestClient, count: int = 2) -> None:
    resp = client.put(
        "/api/v1/household",
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


def test_backup_and_restore_roundtrip_local(local_client: TestClient) -> None:
    """Create backup with count=2, mutate to count=7, restore -> count=2."""
    _seed_household(local_client, count=2)

    b_resp = local_client.post("/api/v1/db/backup")
    assert b_resp.status_code == 200
    filename = b_resp.json()["filename"]

    list_resp = local_client.get("/api/v1/db/backups")
    assert list_resp.status_code == 200
    assert any(item["filename"] == filename for item in list_resp.json())

    # Mutate household
    _seed_household(local_client, count=7)
    assert local_client.get("/api/v1/household").json()["members"][0]["count"] == 7

    # Restore backup
    r_resp = local_client.post("/api/v1/db/restore", json={"filename": filename})
    assert r_resp.status_code == 200
    assert r_resp.json()["status"] == "ok"

    assert local_client.get("/api/v1/household").json()["members"][0]["count"] == 2


def test_backup_and_restore_blocked_in_demo_mode(demo_client: TestClient) -> None:
    """Backup and restore endpoints return 503 in demo mode."""
    assert demo_client.post("/api/v1/db/backup").status_code == 503
    assert demo_client.get("/api/v1/db/backups").status_code == 503
    assert (
        demo_client.post("/api/v1/db/restore", json={"filename": "purvai-x.db"}).status_code == 503
    )


def test_restore_path_traversal_rejected(local_client: TestClient) -> None:
    """Path traversal attempts in restore filename return 400."""
    resp = local_client.post("/api/v1/db/restore", json={"filename": "../evil.db"})
    assert resp.status_code == 400


def test_clear_data_requires_confirm_and_deletes_household(local_client: TestClient) -> None:
    """DELETE /data requires {"confirm": "DELETE"} and removes household."""
    _seed_household(local_client, count=2)

    bad = local_client.request("DELETE", "/api/v1/data", json={"confirm": "no"})
    assert bad.status_code == 400

    ok = local_client.request("DELETE", "/api/v1/data", json={"confirm": "DELETE"})
    assert ok.status_code == 200
    assert ok.json()["deleted"] is True

    # Subsequent household fetch returns 404/409 (no household)
    hh = local_client.get("/api/v1/household")
    assert hh.status_code in (404, 409)
