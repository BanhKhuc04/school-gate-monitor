"""
pytest tests for vehicles CRUD + CSV import.
"""
import pytest
import io


def test_list_vehicles_requires_auth(client):
    """GET /api/vehicles without token returns 401."""
    resp = client.get("/api/vehicles")
    assert resp.status_code == 401


def test_add_vehicle_ok(client):
    """Admin can add a vehicle (returns 201)."""
    from app.tests.conftest import auth_headers
    import time
    unique = f"T{int(time.time()*1000)%100000:05d}"
    resp = client.post("/api/vehicles", json={
        "plate_number": unique,
        "student_name": "Nguyen Van A",
        "student_class": "10A1",
    }, headers=auth_headers(client, "admin"))
    assert resp.status_code == 201
    assert resp.json()["plate_number"] == unique


def test_add_vehicle_duplicate(client):
    """Duplicate plate_number returns 409."""
    from app.tests.conftest import auth_headers
    import time
    unique = f"D{int(time.time()*1000)%100000:05d}"
    client.post("/api/vehicles", json={
        "plate_number": unique, "student_name": "A", "student_class": "10A",
    }, headers=auth_headers(client, "admin"))
    resp = client.post("/api/vehicles", json={
        "plate_number": unique, "student_name": "B", "student_class": "10B",
    }, headers=auth_headers(client, "admin"))
    assert resp.status_code == 409


def test_csv_import_success(client):
    """CSV import creates vehicles and returns correct counts."""
    from app.tests.conftest import auth_headers
    import time
    p1 = f"I{int(time.time()*1000)%90000+10000:05d}"
    p2 = f"J{int(time.time()*1000+1)%90000+10000:05d}"
    csv_content = f"plate_number,student_name,student_class\n{p1},Nguyen X,11A1\n{p2},Tran Y,11A2"
    resp = client.post(
        "/api/vehicles/import",
        files={"file": ("vehicles.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 2, f"expected 2, got {data}"
    assert data["skipped"] == 0
    assert data["errors"] == []


def test_csv_import_requires_admin(client):
    """CSV import rejects non-admin roles."""
    from app.tests.conftest import auth_headers
    csv_content = "plate_number,student_name,student_class\nX001,Name,Class"
    resp = client.post(
        "/api/vehicles/import",
        files={"file": ("vehicles.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=auth_headers(client, "security"),
    )
    assert resp.status_code == 403
