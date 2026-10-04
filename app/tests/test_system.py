"""
pytest tests for system health & cleanup API.
"""
import os
import pytest


def test_health_requires_auth(client):
    """GET /api/system/health without token returns 401."""
    resp = client.get("/api/system/health")
    assert resp.status_code == 401


def test_health_security_ok(client):
    """GET /api/system/health with security role returns 200 (guards see pipeline status on the live view)."""
    from app.tests.conftest import auth_headers
    resp = client.get("/api/system/health", headers=auth_headers(client, "security"))
    assert resp.status_code == 200


def test_health_admin_ok(client):
    """GET /api/system/health with admin role returns 200 + correct shape."""
    from app.tests.conftest import auth_headers
    resp = client.get("/api/system/health", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    data = resp.json()
    assert "pipeline" in data
    assert "db_size_mb" in data
    assert "snapshot_count" in data
    assert "snapshot_size_mb" in data
    assert "violations_today" in data
    assert isinstance(data["db_size_mb"], (int, float))
    # Đợt 2, Bước 7: recording field luôn có (kể cả khi TẮT → enabled=False).
    assert "recording" in data
    assert isinstance(data["recording"], dict)
    assert "enabled" in data["recording"]


def test_health_management_ok(client):
    """GET /api/system/health with management role also returns 200."""
    from app.tests.conftest import auth_headers
    resp = client.get("/api/system/health", headers=auth_headers(client, "management"))
    assert resp.status_code == 200


# ─── Đợt 2, Bước 5: Disk usage + storage breakdown ────────────────────────────

def test_health_has_disk_usage_fields(client):
    """
    Bước 5: /api/system/health phải trả disk_total_mb / disk_used_mb / disk_free_mb
    (>=0) — đây là field mới để AdminHealthPage render "Dung lượng đĩa".
    """
    from app.tests.conftest import auth_headers
    resp = client.get("/api/system/health", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    data = resp.json()
    for field in ("disk_total_mb", "disk_used_mb", "disk_free_mb"):
        assert field in data, f"missing field: {field}"
        assert isinstance(data[field], (int, float))
        assert data[field] >= 0, f"{field} must be >= 0 (got {data[field]})"


def test_health_has_storage_breakdown(client):
    """
    Bước 5: storage_breakdown phải có đủ 3 key (jpg/mp4/other) với count + size_mb.
    Test field shape thuần + tổng count khớp với snapshot_count (legacy field) — đảm bảo
    2 nguồn số liệu không lệch nhau sau refactor.
    """
    from app.tests.conftest import auth_headers
    resp = client.get("/api/system/health", headers=auth_headers(client, "admin"))
    data = resp.json()
    assert "storage_breakdown" in data
    b = data["storage_breakdown"]
    for key in ("jpg", "mp4", "other"):
        assert key in b, f"missing breakdown key: {key}"
        assert "count" in b[key]
        assert "size_mb" in b[key]
        assert isinstance(b[key]["count"], int)
        assert isinstance(b[key]["size_mb"], (int, float))
    # Tổng count breakdown phải khớp snapshot_count (backwards compat)
    total_breakdown = b["jpg"]["count"] + b["mp4"]["count"] + b["other"]["count"]
    assert total_breakdown == data["snapshot_count"], (
        f"breakdown total {total_breakdown} != snapshot_count {data['snapshot_count']}"
    )


def test_health_breakdown_counts_real_files_end_to_end(client, tmp_path, monkeypatch):
    """
    END-TO-END test cho breakdown: tạo file thật trong SNAPSHOTS_DIR qua monkeypatch
    (chuyển SNAPSHOTS_DIR sang tmp_path), insert 2 .jpg + 1 .mp4, gọi GET /api/system/health
    thật → assert breakdown count đúng (1+1+1, không phải 0). Đây là test hồi quy:
    nếu helper `_storage_breakdown` đếm sai (vd. glob không đệ quy, hoặc lấy nhầm
    extension viết hoa), test này FAIL.
    """
    from app.tests.conftest import auth_headers
    import app.api.system as sys_module
    import app.config as cfg

    # Patch SNAPSHOTS_DIR sang tmp_path (cả cfg và sys_module vì sys_module import snapshot lúc load)
    monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(tmp_path))
    monkeypatch.setattr(sys_module, "SNAPSHOTS_DIR", str(tmp_path))

    # Tạo file thật — size đủ lớn để MB > 0 sau khi round 2 chữ số
    # (300 bytes ≈ 0.000286 MB → round → 0.0; cần >= ~50KB để MB > 0)
    (tmp_path / "snap1.jpg").write_bytes(b"\xff\xd8" + b"x" * 60000)
    (tmp_path / "snap2.jpg").write_bytes(b"\xff\xd8" + b"x" * 120000)
    (tmp_path / "clip1.mp4").write_bytes(b"x" * 300000)
    (tmp_path / "README.txt").write_bytes(b"x" * 50000)

    resp = client.get("/api/system/health", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    data = resp.json()
    b = data["storage_breakdown"]
    assert b["jpg"]["count"] == 2, f"jpg count = {b['jpg']['count']}, expected 2"
    assert b["mp4"]["count"] == 1, f"mp4 count = {b['mp4']['count']}, expected 1"
    assert b["other"]["count"] == 1, f"other count = {b['other']['count']}, expected 1"
    # size_mb tổng phải > 0 (file đủ lớn để round 2 chữ số còn > 0)
    assert b["jpg"]["size_mb"] > 0, f"jpg size_mb = {b['jpg']['size_mb']}"
    assert b["mp4"]["size_mb"] > 0, f"mp4 size_mb = {b['mp4']['size_mb']}"


def test_cleanup_requires_admin(client):
    """POST /api/system/snapshots/cleanup with security role returns 403."""
    from app.tests.conftest import auth_headers
    resp = client.post(
        "/api/system/snapshots/cleanup?older_than_days=90",
        headers=auth_headers(client, "security"),
    )
    assert resp.status_code == 403


def test_cleanup_admin_ok(client):
    """POST /api/system/snapshots/cleanup with admin role returns 200."""
    from app.tests.conftest import auth_headers
    resp = client.post(
        "/api/system/snapshots/cleanup?older_than_days=90",
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "deleted_files" in data
    assert "updated_records" in data


def test_cleanup_invalid_days(client):
    """Cleanup with invalid older_than_days returns 422."""
    from app.tests.conftest import auth_headers
    resp = client.post(
        "/api/system/snapshots/cleanup?older_than_days=0",
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 422


def test_health_with_continuous_recording_enabled(client, monkeypatch):
    """Bật ghi hình liên tục: /api/system/health không được lỗi 500 (trước đây
    _recording_status_all_gates dùng GATES chưa import → NameError)."""
    import app.config as cfg
    from app.tests.conftest import auth_headers
    monkeypatch.setattr(cfg, "CONTINUOUS_RECORDING_ENABLED", True)
    resp = client.get("/api/system/health", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    assert resp.json()["recording"]["enabled"] is True
