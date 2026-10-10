"""
Tests for Đợt E2.1: cập nhật issues[] trên violation_events.
- update_violation_issues(): idempotent, chỉ set observed_at nếu chưa có,
  encounter_id set nếu truyền.
- Endpoint PATCH /api/violations/{id}/issues: serialize Issue thành JSON.
- Endpoint GET /api/violations/{id}/issues: đọc JSON.
- Endpoint GET /api/violations/encounters: gom theo encounter_id, dedup
  issues theo code với priority 'resolved' > 'confirmed' > 'conflict' >
  'deferred' > 'pending'. display_status = red/yellow/gray/resolved.
"""
import json
import pytest


def _seed_violation(client, **overrides):
    """Tạo 1 violation_events trực tiếp qua DB để test E2.1."""
    import app.db as db_module
    defaults = {
        "timestamp": "2026-09-30T08:00:00",
        "violation_type": "NO_HELMET",
        "helmet_status": "no_helmet",
        "plate_read": "59A12345",
        "plate_matched": None,
        "gate_id": "gate_a",
        "status": "needs_review",
        "encounter_id": None,
        "issues_json": None,
        "observed_at": None,
        "source_epoch": 1,
    }
    defaults.update(overrides)
    return db_module.add_violation_event(**defaults)


def test_update_violation_issues_idempotent(client):
    """Ghi đè issues_json với cùng nội dung nhiều lần — không lỗi, dữ liệu giữ."""
    vid = _seed_violation(client)
    import app.db as db_module
    payload = '[{"code":"NO_HELMET","status":"confirmed","sample_count":5}]'
    # Lần 1
    assert db_module.update_violation_issues(vid, payload) is True
    # Lần 2 — ghi đè với cùng nội dung
    assert db_module.update_violation_issues(vid, payload) is True
    # Kiểm tra DB
    items = db_module.list_violations(limit=10)["items"]
    row = next(r for r in items if r["id"] == vid)
    parsed = json.loads(row["issues_json"])
    assert len(parsed) == 1
    assert parsed[0]["code"] == "NO_HELMET"
    assert parsed[0]["status"] == "confirmed"
    assert parsed[0]["sample_count"] == 5


def test_unicode_reason_persists(client):
    """Lý do tiếng Việt có dấu phải lưu/đọc nguyên vẹn (đảm bảo ensure_ascii=False)."""
    from app.tests.conftest import auth_headers
    vid = _seed_violation(client)
    resp = client.patch(
        f"/api/violations/{vid}/issues",
        json={
            "issues": [
                {"code": "PLATE_OBSCURED", "status": "deferred",
                 "reason": "chưa rõ biển — bị che khuất"},
            ],
        },
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200, resp.text
    import app.db as db_module
    row = next(r for r in db_module.list_violations(limit=10)["items"]
                if r["id"] == vid)
    parsed = json.loads(row["issues_json"])
    assert parsed[0]["reason"] == "chưa rõ biển — bị che khuất"


def test_update_violation_issues_none_returns_true(client):
    """Gọi với issues_json=None, observed_at=None, encounter_id=None
    thì không có gì để cập nhật — trả True, không lỗi."""
    vid = _seed_violation(client)
    import app.db as db_module
    assert db_module.update_violation_issues(vid, None) is True


def test_update_violation_issues_observed_at_only_first_wins(client):
    """observed_at chỉ set nếu chưa có — gọi 2 lần với 2 giá trị, lần 2 bị bỏ qua."""
    vid = _seed_violation(client)
    import app.db as db_module
    assert db_module.update_violation_issues(
        vid, '[{"code":"X","status":"pending"}]',
        observed_at="2026-09-30T08:00:01") is True
    assert db_module.update_violation_issues(
        vid, '[{"code":"X","status":"confirmed"}]',
        observed_at="2026-09-30T08:00:02") is True
    row = next(r for r in db_module.list_violations(limit=10)["items"]
                if r["id"] == vid)
    # observed_at lưu lần đầu, issues_json lưu lần cuối
    assert row["observed_at"] == "2026-09-30T08:00:01"
    parsed = json.loads(row["issues_json"])
    assert parsed[0]["status"] == "confirmed"


def test_update_violation_issues_encounter_id_overwrites(client):
    """encounter_id không có ràng buộc 'chỉ set nếu null' — luôn overwrite."""
    vid = _seed_violation(client, encounter_id="enc-1")
    import app.db as db_module
    assert db_module.update_violation_issues(
        vid, None, encounter_id="enc-2") is True
    row = next(r for r in db_module.list_violations(limit=10)["items"]
                if r["id"] == vid)
    assert row["encounter_id"] == "enc-2"


def test_update_violation_issues_invalid_id_returns_false(client):
    """ID không tồn tại → False."""
    import app.db as db_module
    assert db_module.update_violation_issues(
        999999, '[{"code":"X","status":"pending"}]') is False


def test_patch_issues_endpoint_persists_json(client):
    """Endpoint PATCH /api/violations/{id}/issues — nhận list[Issue],
    serialize JSON đúng."""
    from app.tests.conftest import auth_headers
    vid = _seed_violation(client)
    resp = client.patch(
        f"/api/violations/{vid}/issues",
        json={
            "issues": [
                {"code": "NO_HELMET", "status": "confirmed",
                 "sample_count": 6, "reason": "streak 6 frames"},
                {"code": "PLATE_OBSCURED", "status": "deferred",
                 "sample_count": 2, "reason": "best_conf < min"},
            ],
            "encounter_id": "enc-test-1",
            "observed_at": "2026-09-30T08:00:01",
        },
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200, resp.text
    import app.db as db_module
    row = next(r for r in db_module.list_violations(limit=10)["items"]
                if r["id"] == vid)
    parsed = json.loads(row["issues_json"])
    codes = {it["code"]: it for it in parsed}
    assert codes["NO_HELMET"]["status"] == "confirmed"
    assert codes["NO_HELMET"]["sample_count"] == 6
    assert codes["PLATE_OBSCURED"]["status"] == "deferred"
    assert row["encounter_id"] == "enc-test-1"
    assert row["observed_at"] == "2026-09-30T08:00:01"


def test_patch_issues_endpoint_requires_auth(client):
    """PATCH issues không auth → 401."""
    vid = _seed_violation(client)
    resp = client.patch(
        f"/api/violations/{vid}/issues",
        json={"issues": [{"code": "X", "status": "pending"}]},
    )
    assert resp.status_code == 401


def test_get_issues_endpoint_returns_json(client):
    """GET /issues — trả về issues_json parse được."""
    from app.tests.conftest import auth_headers
    vid = _seed_violation(client)
    import app.db as db_module
    db_module.update_violation_issues(
        vid,
        '[{"code":"NO_HELMET","status":"confirmed","sample_count":4}]',
        encounter_id="enc-get")
    resp = client.get(
        f"/api/violations/{vid}/issues",
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["encounter_id"] == "enc-get"
    issues = json.loads(data["issues"])
    assert issues[0]["code"] == "NO_HELMET"
    assert issues[0]["sample_count"] == 4


def test_encounters_endpoint_groups_by_encounter_id(client):
    """GET /violations/encounters — gom nhiều record cùng encounter_id
    thành 1 group; issues dedup theo code với priority cao nhất.

    Pre-E3 fix plan: truyền limit=200 để bao trùm mọi encounter trong DB
    test (DB module-shared nên có thể có encounter từ test khác)."""
    from app.tests.conftest import auth_headers
    import app.db as db_module
    # 2 record cùng encounter_id 'enc-A'
    vid_a1 = _seed_violation(client, encounter_id="enc-A",
                              gate_id="gate_a", violation_type="NO_HELMET")
    vid_a2 = _seed_violation(client, encounter_id="enc-A",
                              gate_id="gate_a", violation_type="PLATE_NOT_REGISTERED")
    db_module.update_violation_issues(
        vid_a1, '[{"code":"NO_HELMET","status":"pending","sample_count":2}]')
    db_module.update_violation_issues(
        vid_a2, '[{"code":"PLATE_NOT_REGISTERED","status":"confirmed","sample_count":4},'
                '{"code":"NO_HELMET","status":"confirmed","sample_count":6}]')
    # 1 record encounter_id riêng 'enc-B' (legacy: không có encounter_id)
    vid_b = _seed_violation(client, gate_id="gate_b",
                              violation_type="NO_HELMET")
    resp = client.get(
        "/api/violations/encounters?limit=200",
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    items = {g["encounter_id"]: g for g in data["items"]}
    # enc-A có 2 record
    assert "enc-A" in items
    a = items["enc-A"]
    assert set(a["violation_ids"]) == {vid_a1, vid_a2}
    # NO_HELMET: lưu 2 lần với status pending (vid_a1) + confirmed (vid_a2)
    # → group giữ status cao nhất = confirmed
    no_helmet = next(it for it in a["issues"] if it["code"] == "NO_HELMET")
    assert no_helmet["status"] == "confirmed"
    assert no_helmet["sample_count"] == 6
    # PLATE_NOT_REGISTERED: chỉ ở vid_a2
    pnr = next(it for it in a["issues"] if it["code"] == "PLATE_NOT_REGISTERED")
    assert pnr["status"] == "confirmed"
    # display_status: có confirmed → red
    assert a["display_status"] == "red"
    # enc-B (legacy-{id}) — chỉ có 1 record, không có issues_json.
    # DB module-shared giữa các test, có thể có encounter từ test khác;
    # kiểm tra legacy-xuất hiện dạng 'legacy-{id}' chứ không bắt buộc id cụ thể.
    legacy_keys = [k for k in items if k.startswith("legacy-")]
    assert any(k == f"legacy-{vid_b}" for k in legacy_keys), (
        f"legacy-{vid_b} phải có trong items; hiện có legacy keys={legacy_keys}"
    )
    b = items[f"legacy-{vid_b}"]
    assert b["violation_ids"] == [vid_b]
    assert b["issues"] == []
    # Không có issue nào → gray
    assert b["display_status"] == "gray"
    # Total = tổng số encounter_id khác nhau, KHÔNG phải số row.
    # Khi chạy độc lập chỉ có 2 (enc-A + legacy-{vid_b}); khi chạy cùng các test
    # khác trong module có thể nhiều hơn.
    assert data["total"] == len(items)
    assert data["total"] >= 2, (
        f"total phải >= 2 (enc-A + legacy-{vid_b}); total={data['total']}"
    )


def test_encounters_endpoint_yellow_when_only_pending(client):
    """Group chỉ có issue pending/deferred/conflict → display_status='yellow'."""
    from app.tests.conftest import auth_headers
    import app.db as db_module
    vid = _seed_violation(client, encounter_id="enc-yellow")
    db_module.update_violation_issues(
        vid, '[{"code":"NO_HELMET","status":"deferred","sample_count":2}]'
    )
    resp = client.get(
        "/api/violations/encounters",
        headers=auth_headers(client, "admin"),
    )
    items = {g["encounter_id"]: g for g in resp.json()["items"]}
    assert items["enc-yellow"]["display_status"] == "yellow"


def test_encounters_endpoint_resolved_overrides_confirmed(client):
    """Nếu vẫn còn issue confirmed chưa resolved → đỏ.
    Pre-E3 fix plan: 'resolved của một issue resolved có thể che issue khác'
    là lỗi — fix để confirmed hiển thị đỏ, chỉ toàn resolved mới là resolved.
    """
    from app.tests.conftest import auth_headers
    import app.db as db_module
    vid = _seed_violation(client, encounter_id="enc-resolved")
    db_module.update_violation_issues(
        vid, '[{"code":"NO_HELMET","status":"confirmed","sample_count":6},'
              '{"code":"PLATE_NOT_REGISTERED","status":"resolved","sample_count":4}]'
    )
    resp = client.get(
        "/api/violations/encounters",
        headers=auth_headers(client, "admin"),
    )
    items = {g["encounter_id"]: g for g in resp.json()["items"]}
    # Có 1 issue confirmed (NO_HELMET) + 1 issue resolved (PLATE_NOT_REGISTERED)
    # → display_status phải là 'red' (vẫn còn lỗi confirmed chưa đóng)
    assert items["enc-resolved"]["display_status"] == "red", (
        "encounter có issue confirmed + resolved → phải đỏ, không phải resolved"
    )


def test_encounters_endpoint_dedup_higher_priority_wins(client):
    """Khi 2 record cùng code NO_HELMET với status khác nhau, group giữ
    status cao nhất (priority resolved>confirmed>conflict>deferred>pending)."""
    from app.tests.conftest import auth_headers
    import app.db as db_module
    vid1 = _seed_violation(client, encounter_id="enc-dup",
                            gate_id="gate_a", violation_type="NO_HELMET")
    vid2 = _seed_violation(client, encounter_id="enc-dup",
                            gate_id="gate_a", violation_type="NO_HELMET")
    db_module.update_violation_issues(
        vid1, '[{"code":"NO_HELMET","status":"pending","sample_count":1}]'
    )
    db_module.update_violation_issues(
        vid2, '[{"code":"NO_HELMET","status":"conflict","sample_count":3}]'
    )
    resp = client.get(
        "/api/violations/encounters",
        headers=auth_headers(client, "admin"),
    )
    g = next(g for g in resp.json()["items"] if g["encounter_id"] == "enc-dup")
    no_helmet = next(it for it in g["issues"] if it["code"] == "NO_HELMET")
    # conflict > pending → giữ conflict, sample_count=3
    assert no_helmet["status"] == "conflict"
    assert no_helmet["sample_count"] == 3
    # display_status: conflict → yellow
    assert g["display_status"] == "yellow"


def test_issue_schema_validates_required_fields():
    """Issue Pydantic schema: code + status bắt buộc, các field khác default."""
    from app.schemas import Issue
    iss = Issue(code="NO_HELMET", status="confirmed")
    assert iss.sample_count == 0
    assert iss.reason is None
    assert iss.evidence_ref is None


def test_issue_schema_rejects_unknown_status():
    """IssueStatus literal — status ngoài enum bị reject."""
    from app.schemas import Issue
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Issue(code="NO_HELMET", status="nonsense")


def test_encounters_endpoint_all_resolved_is_resolved(client):
    """Tất cả issue resolved → display_status='resolved'.
    Phân biệt với confirmed: chỉ khi toàn bộ confirmed mới chuyển resolved.
    """
    from app.tests.conftest import auth_headers
    import app.db as db_module
    vid = _seed_violation(client, encounter_id="enc-all-resolved")
    db_module.update_violation_issues(
        vid, '[{"code":"NO_HELMET","status":"resolved","sample_count":3},'
              '{"code":"PLATE_NOT_REGISTERED","status":"resolved","sample_count":5}]'
    )
    resp = client.get(
        "/api/violations/encounters",
        headers=auth_headers(client, "admin"),
    )
    items = {g["encounter_id"]: g for g in resp.json()["items"]}
    # Tất cả resolved → display_status = 'resolved' (không phải 'red')
    assert items["enc-all-resolved"]["display_status"] == "resolved"


def test_encounters_endpoint_pagination_limit_one(client):
    """limit=1, offset=0 → trả đúng 1 encounter (bất kể DB có bao nhiêu row).
    Total phản ánh tổng số encounter_id distinct, không phải tổng row.
    """
    from app.tests.conftest import auth_headers
    # Tạo 3 encounter distinct
    _seed_violation(client, encounter_id="enc-p1", gate_id="gate_a",
                    violation_type="NO_HELMET")
    _seed_violation(client, encounter_id="enc-p2", gate_id="gate_a",
                    violation_type="NO_HELMET")
    _seed_violation(client, encounter_id="enc-p3", gate_id="gate_a",
                    violation_type="NO_HELMET")
    resp = client.get(
        "/api/violations/encounters?limit=1&offset=0",
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    # Chỉ 1 encounter trả về do limit=1
    assert len(data["items"]) == 1, f"limit=1 nhưng trả về {len(data['items'])} items"
    # Total >= 3 (enc-p1, enc-p2, enc-p3 + có thể encounter từ test khác)
    assert data["total"] >= 3, f"total={data['total']} phải >= 3 distinct encounters"
    # Total != len(items) vì có pagination
    assert data["total"] != len(data["items"]), (
        f"total={data['total']} == len(items)={len(data['items'])} — "
        "pagination không hoạt động đúng"
    )
    # offset tiếp theo (limit=1, offset=1) phải trả encounter khác
    resp2 = client.get(
        "/api/violations/encounters?limit=1&offset=1",
        headers=auth_headers(client, "admin"),
    )
    items2 = [g["encounter_id"] for g in resp2.json()["items"]]
    items1 = [g["encounter_id"] for g in data["items"]]
    assert items1 != items2, "offset=1 phải trả encounter khác offset=0"


def test_encounter_group_schema_defaults():
    """EncounterGroup schema có default list rỗng."""
    from app.schemas import EncounterGroup
    g = EncounterGroup(encounter_id="enc-x")
    assert g.issues == []
    assert g.violation_ids == []
    assert g.display_status == "gray"