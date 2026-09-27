"""
Admin JSON API routes.
- GET/POST /api/vehicles
- PUT/DELETE /api/vehicles/{id}
- POST /api/vehicles/import (CSV)
- GET /api/violations (with pagination + filters)
- GET /api/stats/summary
"""
import csv
import io
from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File

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


@vehicles_router.post("/import")
def import_vehicles_csv(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("admin")),
):
    """
    POST /api/vehicles/import — bulk import vehicles from CSV.

    CSV format: plate_number,student_name,student_class (header required).
    Best-effort: processes all rows even if some fail.
    Returns: {total, created, skipped, errors: [{row, message}]}
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Must upload a .csv file")

    content = file.file.read()
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row")

    # Normalize column names (flexible matching)
    fieldnames = [f.strip().lower() for f in reader.fieldnames]
    col_map = {k: v for k, v in zip(fieldnames, reader.fieldnames)}

    def get_col(row, keys):
        for k in keys:
            key_lower = k.lower()
            if key_lower in col_map:
                return row[col_map[key_lower]].strip()
        return ''

    created = 0
    skipped = 0
    errors: list[dict] = []

    for row_num, row in enumerate(reader, start=2):  # row_num starts at 2 (1 = header)
        plate = get_col(row, ['plate_number', 'plate', 'biển số'])
        student_name = get_col(row, ['student_name', 'name', 'tên', 'học sinh'])
        student_class = get_col(row, ['student_class', 'class', 'lớp', 'class_'])

        if not plate:
            errors.append({'row': row_num, 'message': 'Missing plate_number'})
            skipped += 1
            continue
        if not student_name:
            errors.append({'row': row_num, 'message': 'Missing student_name'})
            skipped += 1
            continue
        if not student_class:
            errors.append({'row': row_num, 'message': 'Missing student_class'})
            skipped += 1
            continue

        try:
            add_vehicle(plate, student_name, student_class)
            created += 1
        except ValueError as e:
            errors.append({'row': row_num, 'message': str(e)})
            skipped += 1
        except Exception as e:
            errors.append({'row': row_num, 'message': f'Unexpected error: {e}'})
            skipped += 1

    return {
        'total': created + skipped,
        'created': created,
        'skipped': skipped,
        'errors': errors,
    }


@violations_router.get("/violations")
def list_violations_json(
    limit: int = 50,
    offset: int = 0,
    date_from: str = None,
    date_to: str = None,
    violation_type: str = None,
    plate: str = None,
    current_user: dict = Depends(require_role("admin")),
):
    """
    GET /api/violations — list violation events with pagination and filters.

    Query params:
        limit: results per page (default 50, max 200)
        offset: skip N results (default 0)
        date_from: ISO timestamp start (inclusive)
        date_to: ISO timestamp end (inclusive)
        violation_type: e.g. 'NO_HELMET', 'PLATE_NOT_REGISTERED'
        plate: filter by plate number (partial match)
    """
    import app.db as db
    result = db.list_violations(
        limit=min(limit, 200),
        offset=offset,
        date_from=date_from,
        date_to=date_to,
        violation_type=violation_type,
        plate=plate,
    )
    # Attach snapshot_url to each item
    for row in result.get('items', []):
        if row.get('snapshot_path'):
            filename = row['snapshot_path'].split('/')[-1]
            row['snapshot_url'] = f'/media/{filename}'
        else:
            row['snapshot_url'] = None
    return result


@stats_router.get("/summary")
def get_stats_summary(current_user: dict = Depends(require_role("management", "admin"))):
    """GET /api/stats/summary — violation statistics (management or admin)."""
    return get_violation_stats()
