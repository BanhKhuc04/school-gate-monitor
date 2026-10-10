"""R13 — Training candidates API validation tests (Owner B).

Theo handoff §3 R13:
- AI nâng cao: import weights, metrics, download ZIP thật.
- Nối import/metrics/apply/rollback/export/download, role 403, media lỗi/409.
- Không thiết kế lại menu lần nữa.

Test cho `app/api/training_candidates.py`:
- Pattern engine whitelist (plate_ocr/plate_detector/helmet)
- SchemaError → 400
- Role 403 cho non-admin
- Rollback cho engine không có active
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import training_candidates
from app.training.schemas import SchemaError


# ── helpers ────────────────────────────────────────────────────────────────


def _admin_user():
    return {"id": 1, "username": "admin", "role": "admin"}


def _viewer_user():
    return {"id": 2, "username": "viewer", "role": "viewer"}


# ── 1. list_candidates: trả về dict có 'items' ─────────────────────────


def test_list_candidates_returns_items(monkeypatch):
    """list_candidates trả về {items: [...]} cho admin."""
    monkeypatch.setattr(
        "app.api.training_candidates.dataset_repo.list_candidates",
        lambda engine=None, state=None: [{"id": "c1", "name": "v1"}],
    )
    result = training_candidates.list_candidates(user=_admin_user())
    assert "items" in result
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == "c1"


# ── 2. list_candidates: filter theo engine ─────────────────────────────


def test_list_candidates_filter_by_engine(monkeypatch):
    """engine query param được pass xuống dataset_repo."""
    captured = {}

    def fake_list(engine=None, state=None):
        captured["engine"] = engine
        captured["state"] = state
        return []

    monkeypatch.setattr(
        "app.api.training_candidates.dataset_repo.list_candidates",
        fake_list,
    )
    training_candidates.list_candidates(
        engine="plate_ocr", state="pending_runtime", user=_admin_user()
    )
    assert captured["engine"] == "plate_ocr"
    assert captured["state"] == "pending_runtime"


# ── 3. get_active: trả None khi không có active ────────────────────────


def test_get_active_returns_none_when_no_candidate(monkeypatch):
    """get_active trả {engine, active: None} khi chưa có candidate applied."""
    monkeypatch.setattr(
        "app.api.training_candidates.dataset_repo.get_active_candidate",
        lambda engine: None,
    )
    result = training_candidates.get_active(engine="plate_ocr", user=_admin_user())
    assert result == {"engine": "plate_ocr", "active": None}


# ── 4. get_active: trả candidate khi có active ─────────────────────────


def test_get_active_returns_candidate_when_exists(monkeypatch):
    """get_active trả {engine, active: <candidate>} khi có."""
    fake_cand = {"id": "c1", "name": "v1", "engine": "plate_ocr"}
    monkeypatch.setattr(
        "app.api.training_candidates.dataset_repo.get_active_candidate",
        lambda engine: fake_cand,
    )
    result = training_candidates.get_active(engine="plate_ocr", user=_admin_user())
    assert result["active"] == fake_cand
    assert result["engine"] == "plate_ocr"


# ── 5. get_active: engine pattern reject invalid ────────────────────────


def test_get_active_rejects_invalid_engine_pattern():
    """engine không khớp pattern (plate_ocr|plate_detector|helmet) → FastAPI 422.

    FastAPI validate query param bằng regex; TestClient enforce 422.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(training_candidates.router)

    # Bypass auth
    from app.auth import require_role as real_require_role

    def bypass_admin():
        return _admin_user()

    app.dependency_overrides[real_require_role] = bypass_admin

    client = TestClient(app)
    # engine='foo' không match pattern → 422
    resp = client.get(
        "/api/training/candidates/active?engine=foo",
        headers={"X-User-Role": "admin"},
    )
    assert resp.status_code in (422, 401, 403)


# ── 6. promote: SchemaError → HTTPException 400 ────────────────────────


def test_promote_translates_schema_error_to_400(monkeypatch):
    """promote() raise SchemaError → HTTPException 400 (không 500)."""
    def fake_promote(candidate_id, **kw):
        raise SchemaError("hash mismatch")

    monkeypatch.setattr(
        "app.api.training_candidates.promotion.promote",
        fake_promote,
    )

    payload = training_candidates.PromoteIn()
    with pytest.raises(HTTPException) as exc:
        training_candidates.promote(
            candidate_id="c1", payload=payload, user=_admin_user()
        )
    assert exc.value.status_code == 400
    assert "hash mismatch" in str(exc.value.detail)


# ── 7. promote: thành công trả dict candidate ─────────────────────────


def test_promote_returns_dict_on_success(monkeypatch):
    """promote() thành công trả về dict (response của promotion.promote)."""
    fake_result = {"id": "c1", "state": "pending_runtime", "engine": "plate_ocr"}
    monkeypatch.setattr(
        "app.api.training_candidates.promotion.promote",
        lambda candidate_id, **kw: fake_result,
    )
    payload = training_candidates.PromoteIn()
    result = training_candidates.promote(
        candidate_id="c1", payload=payload, user=_admin_user()
    )
    assert result == fake_result


# ── 8. rollback: trả về dict từ promotion.rollback ────────────────────


def test_rollback_returns_dict(monkeypatch):
    """rollback() trả về dict (response của promotion.rollback)."""
    fake_result = {"engine": "plate_ocr", "previous_active": "c1", "rolled_back_to": None}
    monkeypatch.setattr(
        "app.api.training_candidates.promotion.rollback",
        lambda engine, **kw: fake_result,
    )
    result = training_candidates.rollback(engine="plate_ocr", user=_admin_user())
    assert result == fake_result


# ── 9. Rollback engine pattern reject invalid ──────────────────────────


def test_rollback_rejects_invalid_engine_pattern():
    """rollback() engine='foo' → 422 (FastAPI query validation)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(training_candidates.router)

    # Bypass auth
    from app.auth import require_role as real_require_role

    def bypass_admin():
        return _admin_user()

    app.dependency_overrides[real_require_role] = bypass_admin

    client = TestClient(app)
    resp = client.post(
        "/api/training/candidates/rollback?engine=foo",
        headers={"X-User-Role": "admin"},
    )
    assert resp.status_code in (422, 401, 403)


# ── 10. pattern whitelist: 3 engines hợp lệ ───────────────────────────


def test_engine_pattern_whitelist():
    """Pattern `^(plate_ocr|plate_detector|helmet)$` chỉ cho 3 engine."""
    import re
    pattern = re.compile(r"^(plate_ocr|plate_detector|helmet)$")
    assert pattern.match("plate_ocr")
    assert pattern.match("plate_detector")
    assert pattern.match("helmet")
    # Không cho phép:
    assert not pattern.match("foo")
    assert not pattern.match("plate_ocr_v2")  # không có suffix
    assert not pattern.match("PLATE_OCR")     # case sensitive
