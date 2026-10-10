"""
Tests for Feature 2: Repeat offender tracking + violations summary.
"""
import pytest
import time
from datetime import datetime, timedelta, timezone


def test_violations_summary_requires_auth(client):
    """GET /api/vehicles/violations-summary without auth → 401."""
    resp = client.get("/api/vehicles/violations-summary")
    assert resp.status_code == 401


def test_violations_summary_admin_ok(client):
    """Admin can access violations summary → 200."""
    from app.tests.conftest import auth_headers

    resp = client.get(
        "/api/vehicles/violations-summary",
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_violations_summary_teacher_ok(client):
    """Teacher can access violations summary (scoped to their class)."""
    from app.tests.conftest import auth_headers

    resp = client.get(
        "/api/vehicles/violations-summary",
        headers=auth_headers(client, "teacher"),
    )
    assert resp.status_code == 200


def test_violations_summary_management_ok(client):
    """Management can access violations summary."""
    from app.tests.conftest import auth_headers

    resp = client.get(
        "/api/vehicles/violations-summary",
        headers=auth_headers(client, "management"),
    )
    assert resp.status_code == 200


def test_repeat_offender_flag(client):
    """4 violations in window → is_repeat_offender=True."""
    from app.tests.conftest import auth_headers
    from app.db import add_vehicle, add_violation_event

    # Add a test vehicle
    plate = f"RPT{int(time.time()*1000)%90000+10000:05d}"
    add_vehicle(plate, "Test Student", "10A1")

    # Add 4 violations in the last 30 days
    now = datetime.now(timezone.utc).isoformat()
    for _i in range(4):
        add_violation_event(
            timestamp=now,
            plate_read=plate,
            plate_matched=plate,
            helmet_status="no_helmet",
            violation_type="NO_HELMET",
        )

    resp = client.get(
        "/api/vehicles/violations-summary",
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    # Find our vehicle
    our_vehicle = next((v for v in data if v["plate_number"] == plate), None)
    assert our_vehicle is not None
    assert our_vehicle["violations_in_window"] >= 4
    assert our_vehicle["is_repeat_offender"] is True


def test_non_repeat_offender_flag(client):
    """2 violations in window → is_repeat_offender=False."""
    from app.tests.conftest import auth_headers
    from app.db import add_vehicle, add_violation_event

    plate = f"NON{int(time.time()*1000)%90000+10000:05d}"
    add_vehicle(plate, "Test Student 2", "10A2")

    now = datetime.now(timezone.utc).isoformat()
    for _i in range(2):
        add_violation_event(
            timestamp=now,
            plate_read=plate,
            plate_matched=plate,
            helmet_status="no_helmet",
            violation_type="NO_HELMET",
        )

    resp = client.get(
        "/api/vehicles/violations-summary",
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    our_vehicle = next((v for v in data if v["plate_number"] == plate), None)
    assert our_vehicle is not None
    assert our_vehicle["violations_in_window"] >= 2
    assert our_vehicle["is_repeat_offender"] is False


def test_teacher_scope_filter(client):
    """Teacher only sees vehicles from their homeroom_class."""
    from app.tests.conftest import auth_headers
    from app.db import add_vehicle

    # Add vehicle in teacher's class (10A1)
    plate1 = f"T1A{int(time.time()*1000)%90000+10000:05d}"
    add_vehicle(plate1, "Student In Class", "10A1")

    # Add vehicle in different class
    plate2 = f"T2A{int(time.time()*1000)%90000+10000:05d}"
    add_vehicle(plate2, "Student Other Class", "11B2")

    resp = client.get(
        "/api/vehicles/violations-summary",
        headers=auth_headers(client, "teacher"),
    )
    assert resp.status_code == 200
    data = resp.json()
    plates = [v["plate_number"] for v in data]
    assert plate1 in plates
    assert plate2 not in plates  # teacher only sees 10A1
