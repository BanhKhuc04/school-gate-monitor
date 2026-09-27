"""
pytest tests for face enrollment API (app/api/faces.py).
Uses mocking for insightface to keep tests fast.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi import status
from app.tests.conftest import auth_headers

# Fake embedding bytes (512 floats × 4 bytes each = 2048 bytes)
_FAKE_EMBEDDING = b"\x00" * 2048

# Valid JPEG image bytes (tiny solid-color image)
_TINY_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
    b"\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d"
    b"\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
    b"\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04"
    b"\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x13Qa\x14"
    b"q\x91#3B\x81\x91\xa1R\xb1\xb2\xc1\xb3\x82\x15R\xd1\xf0$4br"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd4\xff\xd9"
)


def _mock_detect_and_embed(image_bytes):
    """Mock that simulates detect_and_embed: returns bytes or None."""
    if not image_bytes or len(image_bytes) < 100:
        return None  # too small / empty
    return _FAKE_EMBEDDING


# ─── Enroll ────────────────────────────────────────────────────────────────────

class TestFaceEnroll:
    def test_enroll_requires_auth(self, client):
        r = client.post(
            "/api/faces/enroll",
            data={"label_name": "Test"},
            files={"photo": ("face.jpg", b"\x00\x00\x00\x00", "image/jpeg")},
        )
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_enroll_requires_admin(self, client):
        r = client.post(
            "/api/faces/enroll",
            data={"label_name": "Test"},
            files={"photo": ("face.jpg", b"\x00\x00\x00\x00", "image/jpeg")},
            headers=auth_headers(client, "management"),
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_enroll_empty_image_rejected(self, client):
        r = client.post(
            "/api/faces/enroll",
            data={"label_name": "Empty Test"},
            files={"photo": ("empty.jpg", b"", "image/jpeg")},
            headers=auth_headers(client, "admin"),
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_enroll_small_invalid_image_rejected(self, client):
        """Image too small for JPEG decoding → 400."""
        r = client.post(
            "/api/faces/enroll",
            data={"label_name": "Tiny Test"},
            files={"photo": ("tiny.jpg", b"\xff\xd8\xff", "image/jpeg")},
            headers=auth_headers(client, "admin"),
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_enroll_no_face_detected_rejected(self, client):
        """Valid JPEG but no face → 400."""
        with patch("app.cv.face.detect_and_embed", return_value=None):
            r = client.post(
                "/api/faces/enroll",
                data={"label_name": "No Face"},
                files={"photo": ("nface.jpg", _TINY_JPEG, "image/jpeg")},
                headers=auth_headers(client, "admin"),
            )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert "no face" in r.json()["detail"].lower()

    def test_enroll_success(self, client):
        """Valid image + face detected → 200, returns face record."""
        with patch("app.cv.face.detect_and_embed", return_value=_FAKE_EMBEDDING):
            r = client.post(
                "/api/faces/enroll",
                data={"label_name": "Test User 1"},
                files={"photo": ("face.jpg", _TINY_JPEG, "image/jpeg")},
                headers=auth_headers(client, "admin"),
            )
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert data["label_name"] == "Test User 1"
        assert "id" in data

    def test_enroll_with_vehicle_id(self, client):
        """Enroll with optional vehicle_id → stored in DB."""
        with patch("app.cv.face.detect_and_embed", return_value=_FAKE_EMBEDDING):
            r = client.post(
                "/api/faces/enroll",
                data={"label_name": "Test User 2", "vehicle_id": "1"},
                files={"photo": ("face.jpg", _TINY_JPEG, "image/jpeg")},
                headers=auth_headers(client, "admin"),
            )
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert data["label_name"] == "Test User 2"


# ─── List ─────────────────────────────────────────────────────────────────────

class TestFaceList:
    def test_list_requires_auth(self, client):
        r = client.get("/api/faces")
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_requires_admin(self, client):
        r = client.get("/api/faces", headers=auth_headers(client, "management"))
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_list_ok(self, client):
        r = client.get("/api/faces", headers=auth_headers(client, "admin"))
        assert r.status_code == status.HTTP_200_OK
        assert isinstance(r.json(), list)


# ─── Delete ──────────────────────────────────────────────────────────────────

class TestFaceDelete:
    def test_delete_requires_auth(self, client):
        r = client.delete("/api/faces/999")
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_nonexistent(self, client):
        r = client.delete("/api/faces/99999", headers=auth_headers(client, "admin"))
        assert r.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_requires_admin(self, client):
        r = client.delete("/api/faces/1", headers=auth_headers(client, "management"))
        assert r.status_code == status.HTTP_403_FORBIDDEN


# ─── Events ──────────────────────────────────────────────────────────────────

class TestFaceEvents:
    def test_events_requires_auth(self, client):
        r = client.get("/api/faces/events")
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_events_admin_ok(self, client):
        r = client.get("/api/faces/events", headers=auth_headers(client, "admin"))
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert "total" in data
        assert "items" in data
        assert "limit" in data
        assert "offset" in data

    def test_events_management_ok(self, client):
        r = client.get("/api/faces/events", headers=auth_headers(client, "management"))
        assert r.status_code == status.HTTP_200_OK

    def test_events_pagination(self, client):
        r = client.get("/api/faces/events?limit=10&offset=0", headers=auth_headers(client, "admin"))
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert data["limit"] == 10
        assert data["offset"] == 0
