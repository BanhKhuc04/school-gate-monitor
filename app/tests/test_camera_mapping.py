"""
Tests cho Đợt 1 — Multi-camera mapping (1 gate ↔ nhiều camera).
Verify:
- upsert_camera: idempotent, role validation, ON CONFLICT cập nhật đúng field.
- list_cameras_for_gate: sắp theo role front→rear→aux, only_enabled filter.
- delete_camera: trả về True/False.
- Endpoint: POST tạo mới (201), POST cập nhật (upsert), DELETE 200, source
  được che credentials qua display_source.
"""
import pytest


def _seed_cameras(client):
    """Trả về danh sách camera_id đã tạo qua API."""
    headers = {"Authorization": f"Bearer "}
    from app.tests.conftest import auth_headers
    h = auth_headers(client, "admin")
    # Front
    r1 = client.post(
        "/api/camera/main/cameras",
        json={
            "camera_id": "main-front",
            "role": "front",
            "source": "0",  # webcam index — không cần che credentials
            "enabled": 1,
        },
        headers=h,
    )
    assert r1.status_code == 201, r1.text
    # Rear
    r2 = client.post(
        "/api/camera/main/cameras",
        json={
            "camera_id": "main-rear",
            "role": "rear",
            "source": "rtsp://user:secret@10.0.0.5:554/stream1",
            "enabled": 1,
        },
        headers=h,
    )
    assert r2.status_code == 201, r2.text
    # Aux (sẽ tắt)
    r3 = client.post(
        "/api/camera/main/cameras",
        json={
            "camera_id": "main-aux",
            "role": "aux",
            "source": "2",
            "enabled": 0,
        },
        headers=h,
    )
    assert r3.status_code == 201, r3.text
    return ["main-front", "main-rear", "main-aux"]


def test_upsert_camera_idempotent(client):
    """Gọi upsert 2 lần với cùng camera_id → không tạo row trùng, có cập nhật."""
    import app.db as db_module
    db_module.upsert_camera("cam-test", "main", "front", "0", 1)
    db_module.upsert_camera("cam-test", "main", "rear", "1", 0)  # đổi role + source + enabled
    cam = db_module.get_camera("cam-test")
    assert cam is not None
    assert cam["role"] == "rear"
    assert cam["source"] == "1"
    assert cam["enabled"] == 0


def test_upsert_camera_invalid_role_raises(client):
    import app.db as db_module
    with pytest.raises(ValueError):
        db_module.upsert_camera("cam-bad", "main", "side", "0", 1)


def test_list_cameras_for_gate_orders_by_role(client):
    import app.db as db_module
    db_module.upsert_camera("cam-front-z", "main", "front", "0", 1)
    db_module.upsert_camera("cam-aux-z", "main", "aux", "3", 1)
    db_module.upsert_camera("cam-rear-z", "main", "rear", "1", 1)
    cams = db_module.list_cameras_for_gate("main")
    # Lọc chỉ 3 camera ta vừa insert (tránh ảnh hưởng data test khác)
    ids_in_test = [c["camera_id"] for c in cams if c["camera_id"].endswith("-z")]
    assert ids_in_test == ["cam-front-z", "cam-rear-z", "cam-aux-z"]


def test_list_cameras_only_enabled_filter(client):
    import app.db as db_module
    db_module.upsert_camera("cam-on-x", "main", "front", "0", 1)
    db_module.upsert_camera("cam-off-x", "main", "rear", "1", 0)
    only_enabled = db_module.list_cameras_for_gate("main", only_enabled=True)
    all_cams = db_module.list_cameras_for_gate("main", only_enabled=False)
    on_ids = {c["camera_id"] for c in only_enabled}
    all_ids = {c["camera_id"] for c in all_cams}
    assert {"cam-on-x"}.issubset(on_ids)
    assert "cam-off-x" not in on_ids
    assert {"cam-on-x", "cam-off-x"}.issubset(all_ids)


def test_delete_camera_returns_true_then_false(client):
    import app.db as db_module
    db_module.upsert_camera("cam-del", "main", "front", "0", 1)
    assert db_module.delete_camera("cam-del") is True
    assert db_module.delete_camera("cam-del") is False


def test_post_camera_endpoint_creates_and_updates(client):
    from app.tests.conftest import auth_headers
    h = auth_headers(client, "admin")
    # Tạo mới
    r = client.post(
        "/api/camera/main/cameras",
        json={"camera_id": "ep-cam1", "role": "front",
              "source": "0", "enabled": 1},
        headers=h,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["created"] is True
    assert body["camera"]["camera_id"] == "ep-cam1"
    assert body["camera"]["source"] == "0"  # không có credential để che
    # Cập nhật (cùng camera_id, đổi role)
    r2 = client.post(
        "/api/camera/main/cameras",
        json={"camera_id": "ep-cam1", "role": "rear",
              "source": "1", "enabled": 1},
        headers=h,
    )
    assert r2.status_code == 201
    body2 = r2.json()
    assert body2["created"] is False  # đã tồn tại → cập nhật
    assert body2["camera"]["role"] == "rear"
    assert body2["camera"]["source"] == "1"


def test_post_camera_endpoint_invalid_role_422(client):
    from app.tests.conftest import auth_headers
    r = client.post(
        "/api/camera/main/cameras",
        json={"camera_id": "ep-bad", "role": "side",
              "source": "0", "enabled": 1},
        headers=auth_headers(client, "admin"),
    )
    assert r.status_code == 422


def test_post_camera_endpoint_masks_credentials(client):
    """Source RTSP có user:pass phải được che khi trả về qua API."""
    from app.tests.conftest import auth_headers
    r = client.post(
        "/api/camera/main/cameras",
        json={"camera_id": "ep-mask", "role": "front",
              "source": "rtsp://admin:hunter2@10.0.0.5:554/stream", "enabled": 1},
        headers=auth_headers(client, "admin"),
    )
    assert r.status_code == 201
    body = r.json()
    # display_source rút userinfo
    assert "hunter2" not in body["camera"]["source"]
    assert "admin@" not in body["camera"]["source"]
    assert "10.0.0.5:554" in body["camera"]["source"]


def test_list_cameras_endpoint_orders_and_masks(client):
    from app.tests.conftest import auth_headers
    _seed_cameras(client)
    r = client.get("/api/camera/main/cameras",
                   headers=auth_headers(client, "admin"))
    assert r.status_code == 200
    cams = r.json()["cameras"]
    # Lọc chỉ 3 camera ta vừa insert (test có thể đã có data khác)
    ids_in_test = [c["camera_id"] for c in cams if c["camera_id"].startswith("main-")]
    assert ids_in_test == ["main-front", "main-rear", "main-aux"]
    # Che credentials trên source của rear
    rear = next(c for c in cams if c["camera_id"] == "main-rear")
    assert "secret" not in rear["source"]
    assert "user:" not in rear["source"]


def test_delete_camera_endpoint(client):
    from app.tests.conftest import auth_headers
    _seed_cameras(client)
    h = auth_headers(client, "admin")
    r = client.delete("/api/camera/main/cameras/main-rear", headers=h)
    assert r.status_code == 200
    assert r.json()["deleted_camera_id"] == "main-rear"
    # Xóa lần 2 → 404
    r2 = client.delete("/api/camera/main/cameras/main-rear", headers=h)
    assert r2.status_code == 404


def test_delete_camera_endpoint_wrong_gate(client):
    """Camera thuộc gate khác → 404."""
    from app.tests.conftest import auth_headers
    import app.db as db_module
    db_module.upsert_camera("other-gate-cam", "secondary", "front", "0", 1)
    r = client.delete("/api/camera/main/cameras/other-gate-cam",
                      headers=auth_headers(client, "admin"))
    assert r.status_code == 404


def test_list_cameras_endpoint_requires_auth(client):
    r = client.get("/api/camera/main/cameras")
    assert r.status_code == 401


def test_post_camera_endpoint_invalid_source_422(client):
    """Source không hợp lệ → 422, không ghi DB."""
    from app.tests.conftest import auth_headers
    r = client.post(
        "/api/camera/main/cameras",
        json={"camera_id": "ep-bad-src", "role": "front",
              "source": "/nonexistent/path.mp4", "enabled": 1},
        headers=auth_headers(client, "admin"),
    )
    assert r.status_code == 422
    import app.db as db_module
    assert db_module.get_camera("ep-bad-src") is None


# ─── encounter_observations ────────────────────────────────────────────

def test_add_encounter_observation_idempotent(client):
    """Gọi add 2 lần cùng (encounter_id, camera_id, source_epoch) → 1 row."""
    import app.db as db_module
    db_module.add_encounter_observation(
        encounter_id="enc-1", camera_id="cam-A", gate_id="main",
        observed_at="2026-09-30T08:00:00", source_epoch=1,
        plate_read="59A12345",
    )
    db_module.add_encounter_observation(
        encounter_id="enc-1", camera_id="cam-A", gate_id="main",
        observed_at="2026-09-30T08:00:05", source_epoch=1,
        plate_read="59A12345",
        helmet_status="no_helmet",
    )
    obs = db_module.list_observations_for_encounter("enc-1")
    assert len(obs) == 1
    # Lần 2 cập nhật helmet_status (lần 1 không có)
    assert obs[0]["helmet_status"] == "no_helmet"
    # observed_at được cập nhật thành lần 2
    assert obs[0]["observed_at"] == "2026-09-30T08:00:05"


def test_add_encounter_observation_distinct_cameras(client):
    """2 camera khác nhau cho cùng encounter → 2 row."""
    import app.db as db_module
    db_module.add_encounter_observation(
        encounter_id="enc-2", camera_id="cam-front", gate_id="main",
        observed_at="2026-09-30T08:00:01", source_epoch=1,
        plate_read="59A12345",
    )
    db_module.add_encounter_observation(
        encounter_id="enc-2", camera_id="cam-rear", gate_id="main",
        observed_at="2026-09-30T08:00:03", source_epoch=1,
        plate_read="59A12345",
    )
    obs = db_module.list_observations_for_encounter("enc-2")
    assert len(obs) == 2
    cameras = sorted([o["camera_id"] for o in obs])
    assert cameras == ["cam-front", "cam-rear"]


def test_list_observations_empty(client):
    import app.db as db_module
    assert db_module.list_observations_for_encounter("nonexistent") == []