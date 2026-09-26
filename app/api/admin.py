"""
Admin API routes.
- GET /admin → admin.html (list vehicles + form)
- POST /admin/vehicles → thêm xe (redirect)
- POST /admin/vehicles/{id}/edit → sửa xe (redirect)
- POST /admin/vehicles/{id}/delete → xóa xe (redirect)
- GET /admin/violations → bảng vi phạm

- JSON API /api/vehicles (role admin)
"""
from fastapi import APIRouter, Request, Form, HTTPException, Depends, status
from fastapi.responses import RedirectResponse, HTMLResponse

from app.db import (
    add_vehicle, get_vehicle_by_plate, list_vehicles,
    update_vehicle, delete_vehicle, list_violations, get_violation_stats
)
from app.schemas import VehicleIn
from app.auth import require_role


router = APIRouter(prefix="/admin", tags=["admin"])
vehicles_router = APIRouter(prefix="/api", tags=["vehicles"])
stats_router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Trang admin - danh sách xe + form thêm mới."""
    vehicles = list_vehicles()
    return request.app.state.jinja2_env.get_template("admin.html").render(
        request=request,
        vehicles=vehicles,
        error=None
    )


@router.post("/vehicles")
async def add_vehicle_route(request: Request,
                           plate_number: str = Form(...),
                           student_name: str = Form(...),
                           student_class: str = Form(...)):
    """Thêm xe mới, redirect về /admin."""
    try:
        add_vehicle(plate_number, student_name, student_class)
    except ValueError as e:
        # Lỗi: biển số đã tồn tại
        vehicles = list_vehicles()
        return request.app.state.jinja2_env.get_template("admin.html").render(
            request=request,
            vehicles=vehicles,
            error=str(e)
        )
    
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/vehicles/{vehicle_id}/edit")
async def edit_vehicle_form(request: Request, vehicle_id: int):
    """Form sửa xe."""
    vehicles = list_vehicles()
    vehicle = next((v for v in vehicles if v['id'] == vehicle_id), None)
    
    if not vehicle:
        return RedirectResponse(url="/admin", status_code=303)
    
    return request.app.state.jinja2_env.get_template("admin_edit.html").render(
        request=request,
        vehicle=vehicle
    )


@router.post("/vehicles/{vehicle_id}/edit")
async def edit_vehicle_route(request: Request, vehicle_id: int,
                             plate_number: str = Form(...),
                             student_name: str = Form(...),
                             student_class: str = Form(...)):
    """Sửa xe, redirect về /admin."""
    try:
        update_vehicle(vehicle_id, plate_number, student_name, student_class)
    except ValueError as e:
        # Lỗi
        vehicles = list_vehicles()
        vehicle = next((v for v in vehicles if v['id'] == vehicle_id), None)
        return request.app.state.jinja2_env.get_template("admin_edit.html").render(
            request=request,
            vehicle=vehicle,
            error=str(e)
        )
    
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/vehicles/{vehicle_id}/delete")
async def delete_vehicle_route(request: Request, vehicle_id: int):
    """Xóa xe, redirect về /admin."""
    delete_vehicle(vehicle_id)
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/violations", response_class=HTMLResponse)
async def violations_page(request: Request):
    """Trang xem danh sách vi phạm."""
    violations = list_violations(limit=50)
    return request.app.state.jinja2_env.get_template("admin_violations.html").render(
        request=request,
        violations=violations
    )


# ─── JSON API ────────────────────────────────────────────────────────────────

json_router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


@json_router.get("")
def list_vehicles_json(current_user: dict = Depends(require_role("admin"))):
    """GET /api/vehicles — list all registered vehicles (admin only)."""
    return list_vehicles()


@json_router.post("", status_code=status.HTTP_201_CREATED)
def add_vehicle_json(
    body: VehicleIn,
    current_user: dict = Depends(require_role("admin"))
):
    """POST /api/vehicles — add a new vehicle (admin only)."""
    try:
        vehicle_id = add_vehicle(body.plate_number, body.student_name, body.student_class)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    # Return the newly created vehicle
    return get_vehicle_by_plate(body.plate_number)


@json_router.put("/{vehicle_id}")
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


@json_router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle_json(vehicle_id: int, current_user: dict = Depends(require_role("admin"))):
    """DELETE /api/vehicles/{id} — delete a vehicle (admin only)."""
    success = delete_vehicle(vehicle_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return None


@vehicles_router.get("/violations")
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
