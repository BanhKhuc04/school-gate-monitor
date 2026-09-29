"""
pytest tests cho các cột/param mới ở tầng DB (đợt 2, Bước 1):
plate_confidence, gate_id, status='needs_review', và filter status trong
list_violations(). Đây là hợp đồng dữ liệu mà Bước 3 (ghép 2 camera) sẽ dựa vào.
"""
import datetime


def test_add_violation_event_persists_plate_confidence_and_gate_id(client):
    from app.db import add_violation_event, get_connection

    vid = add_violation_event(
        timestamp=datetime.datetime.now().isoformat(),
        plate_read="29A12345",
        plate_matched=None,
        helmet_status="unknown",
        violation_type="PLATE_LOW_CONFIDENCE",
        plate_confidence=0.42,
        gate_id="secondary",
        status="needs_review",
    )
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT plate_confidence, gate_id, status FROM violation_events WHERE id = ?", (vid,)
        ).fetchone()
    finally:
        conn.close()
    assert row["plate_confidence"] == 0.42
    assert row["gate_id"] == "secondary"
    assert row["status"] == "needs_review"


def test_add_violation_event_defaults_status_pending_when_omitted(client):
    """Không truyền status → mặc định 'pending', giữ đúng hành vi cũ trước Bước 1."""
    from app.db import add_violation_event, get_connection

    vid = add_violation_event(
        timestamp=datetime.datetime.now().isoformat(),
        plate_read="29A00000",
        plate_matched="29A00000",
        helmet_status="helmet",
        violation_type="NO_HELMET",
    )
    conn = get_connection()
    try:
        row = conn.execute("SELECT status, plate_confidence, gate_id FROM violation_events WHERE id = ?", (vid,)).fetchone()
    finally:
        conn.close()
    assert row["status"] == "pending"
    assert row["plate_confidence"] is None
    assert row["gate_id"] is None


def test_list_violations_status_filter(client):
    from app.db import add_violation_event, list_violations

    add_violation_event(
        timestamp=datetime.datetime.now().isoformat(),
        plate_read="29B11111", violation_type="PLATE_LOW_CONFIDENCE",
        helmet_status="unknown", status="needs_review",
    )
    add_violation_event(
        timestamp=datetime.datetime.now().isoformat(),
        plate_read="29B22222", plate_matched="29B22222", violation_type="NO_HELMET",
        helmet_status="no_helmet", status="pending",
    )

    needs_review_only = list_violations(status="needs_review")
    assert all(item["status"] == "needs_review" for item in needs_review_only["items"])
    assert any(item["plate_read"] == "29B11111" for item in needs_review_only["items"])
    assert not any(item["plate_read"] == "29B22222" for item in needs_review_only["items"])


def test_list_violations_no_status_filter_returns_both(client):
    from app.db import add_violation_event, list_violations

    add_violation_event(
        timestamp=datetime.datetime.now().isoformat(),
        plate_read="29C11111", violation_type="PLATE_LOW_CONFIDENCE",
        helmet_status="unknown", status="needs_review",
    )
    add_violation_event(
        timestamp=datetime.datetime.now().isoformat(),
        plate_read="29C22222", violation_type="NO_HELMET",
        helmet_status="no_helmet", status="pending",
    )
    result = list_violations()
    plates = {item["plate_read"] for item in result["items"]}
    assert "29C11111" in plates
    assert "29C22222" in plates


def test_get_violations_json_exposes_plate_confidence_field(client):
    """GET /api/violations phải trả plate_confidence cho từng item (SELECT ve.* tự
    động bao gồm cột mới — test này canh giữ nếu sau này có ai đổi SELECT thành
    liệt kê cột tường minh và quên thêm cột mới)."""
    from app.db import add_violation_event
    from app.tests.conftest import auth_headers

    add_violation_event(
        timestamp=datetime.datetime.now().isoformat(),
        plate_read="29D11111", violation_type="PLATE_LOW_CONFIDENCE",
        helmet_status="unknown", status="needs_review", plate_confidence=0.31,
        gate_id="main",
    )
    resp = client.get("/api/violations?plate=29D11111", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["plate_confidence"] == 0.31
    assert items[0]["gate_id"] == "main"
    assert items[0]["status"] == "needs_review"


def test_get_violations_json_status_query_param(client):
    from app.db import add_violation_event
    from app.tests.conftest import auth_headers

    add_violation_event(
        timestamp=datetime.datetime.now().isoformat(),
        plate_read="29E11111", violation_type="PLATE_LOW_CONFIDENCE",
        helmet_status="unknown", status="needs_review",
    )
    resp = client.get("/api/violations?status=needs_review", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    assert all(item["status"] == "needs_review" for item in resp.json()["items"])
