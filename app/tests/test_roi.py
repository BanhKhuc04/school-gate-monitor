"""
Test cho vùng nhận diện (ROI): module thuần app/cv/roi.py + API /api/roi/{gate_id}.
"""
import numpy as np
import pytest

from app.cv.detector import Detection
from app.cv.roi import parse_points, to_pixel_polygon, filter_by_roi


# ─── app/cv/roi.py — pure functions, không cần model ───────────────────────

def test_parse_points_empty_list_means_no_roi():
    assert parse_points([]) is None


def test_parse_points_valid():
    raw = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
    assert parse_points(raw) == [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]


def test_parse_points_too_few_raises():
    with pytest.raises(ValueError):
        parse_points([[0.1, 0.1], [0.9, 0.9]])


def test_parse_points_out_of_range_raises():
    with pytest.raises(ValueError):
        parse_points([[0.1, 0.1], [1.5, 0.1], [0.5, 0.9]])


def test_to_pixel_polygon_none_stays_none():
    assert to_pixel_polygon(None, 1280, 720) is None


def test_to_pixel_polygon_scales_correctly():
    points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
    px = to_pixel_polygon(points, 100, 200)
    assert px.tolist() == [[0, 0], [100, 0], [100, 200]]


def _det(bbox):
    return Detection(class_name="person", confidence=0.9, bbox=bbox)


def test_filter_by_roi_none_polygon_keeps_all():
    dets = [_det((0, 0, 10, 10)), _det((900, 900, 950, 950))]
    assert filter_by_roi(dets, None) == dets


def test_filter_by_roi_keeps_inside_drops_outside():
    # Vùng vuông giữa khung 100x100: (25,25)-(75,75)
    polygon_px = to_pixel_polygon([(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)], 100, 100)
    inside = _det((40, 40, 60, 60))     # center (50,50) — trong vùng
    outside = _det((0, 0, 10, 10))      # center (5,5) — ngoài vùng
    result = filter_by_roi([inside, outside], polygon_px)
    assert result == [inside]


# ─── API /api/roi/{gate_id} ─────────────────────────────────────────────────

def test_roi_get_requires_auth(client):
    resp = client.get("/api/roi/main")
    assert resp.status_code == 401


def test_roi_get_forbidden_for_non_admin(client):
    from app.tests.conftest import auth_headers
    resp = client.get("/api/roi/main", headers=auth_headers(client, "security"))
    assert resp.status_code == 403


def test_roi_get_default_none(client):
    from app.tests.conftest import auth_headers
    resp = client.get("/api/roi/some_gate_never_configured", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    assert resp.json()["points"] is None


def test_roi_post_save_and_roundtrip(client):
    from app.tests.conftest import auth_headers
    headers = auth_headers(client, "admin")
    points = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]

    resp = client.post("/api/roi/roi_test_gate_a", json={"points": points}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["points"] == points

    resp = client.get("/api/roi/roi_test_gate_a", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["points"] == points


def test_roi_post_too_few_points_400(client):
    from app.tests.conftest import auth_headers
    headers = auth_headers(client, "admin")
    resp = client.post("/api/roi/roi_test_gate_b", json={"points": [[0.1, 0.1], [0.5, 0.5]]}, headers=headers)
    assert resp.status_code == 400


def test_roi_post_clear_with_empty_list(client):
    from app.tests.conftest import auth_headers
    headers = auth_headers(client, "admin")
    gate = "roi_test_gate_c"
    client.post(f"/api/roi/{gate}", json={"points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]]}, headers=headers)
    resp = client.post(f"/api/roi/{gate}", json={"points": []}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["points"] is None

    resp = client.get(f"/api/roi/{gate}", headers=headers)
    assert resp.json()["points"] is None
