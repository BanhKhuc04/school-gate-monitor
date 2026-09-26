"""
Admin API routes.
- GET /admin → admin.html (list vehicles + form)
- POST /admin/vehicles → thêm xe (redirect)
- POST /admin/vehicles/{id}/edit → sửa xe (redirect)
- POST /admin/vehicles/{id}/delete → xóa xe (redirect)
- GET /admin/violations → bảng vi phạm
"""
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse

from app.db import (
    add_vehicle, get_vehicle_by_plate, list_vehicles,
    update_vehicle, delete_vehicle, list_violations
)

router = APIRouter(prefix="/admin", tags=["admin"])


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
