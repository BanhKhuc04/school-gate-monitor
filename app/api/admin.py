"""
Admin JSON API routes.
- GET/POST /api/vehicles
- PUT/DELETE /api/vehicles/{id}
- GET /api/violations
- GET /api/stats/summary
"""
from fastapi import APIRouter, HTTPException, Depends, status

from app.db import (
    add_vehicle, get_vehicle_by_plate, list_vehicles,
    update_vehicle, delete_vehicle, list_violations, get_violation_stats
)
from app.schemas import VehicleIn
from app.auth import require_role

vehicles_router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])
violations_router = APIRouter(prefix="/api", tags=["violations"])
stats_router = APIRouter(prefix="/api/stats", tags=["stats"])


@vehicles_router.get("")
def list_vehicles_json(current_user: dict = Depends(require_role("admin"))):
    """GET /api/vehicles — list all registered vehicles (admin only)."""
    return list_vehicles()


@vehicles_router.post("", status_code=status.HTTP_201_CREATED)
def add_vehicle_json(
    body: VehicleIn,
    current_user: dict = Depends(require_role("admin"))
):
    """POST /api/vehicles — add a new vehicle (admin only)."""
    try:
        add_vehicle(body.plate_number, body.student_name, body.student_class)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    return get_vehicle_by_plate(body.plate_number)


@vehicles_router.put("/{vehicle_id}")
def update_vehicle_json(
    vehicle_id: int,
    body: VehicleIn,
    current_user: dict = Depends(require_role("admin"))
):
    """PUT /api/vehicles/{id} — update a vehicle (admin only)."""
    success = update_vehicle(vehicle_id, body.plate_number, body.student_name, body.student_class)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return get_vehicle_by_plate(body.plate_number)


@vehicles_router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle_json(vehicle_id: int, current_user: dict = Depends(require_role("admin"))):
    """DELETE /api/vehicles/{id} — delete a vehicle (admin only)."""
    success = delete_vehicle(vehicle_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return None


@violations_router.get("/violations")
def list_violations_json(limit: int = 50, current_user: dict = Depends(require_role("admin"))):
    """GET /api/violations — list violation events with snapshot_url (admin only)."""
    rows = list_violations(limit=limit)
    result = []
    for row in rows:
        row_dict = dict(row)
        if row_dict.get("snapshot_path"):
            filename = row_dict["snapshot_path"].split("/")[-1]
            row_dict["snapshot_url"] = f"/media/{filename}"
        else:
            row_dict["snapshot_url"] = None
        result.append(row_dict)
    return result


@stats_router.get("/summary")
def get_stats_summary(current_user: dict = Depends(require_role("management", "admin"))):
    """GET /api/stats/summary — violation statistics (management or admin)."""
    return get_violation_stats()
