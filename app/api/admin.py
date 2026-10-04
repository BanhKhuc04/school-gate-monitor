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
import time as _time_module
import sqlite3
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File
from fastapi.responses import StreamingResponse

from app.db import (
    add_vehicle, get_vehicle_by_plate, get_vehicle_by_id, list_vehicles,
    update_vehicle, delete_vehicle, list_violations, get_violation_stats,
    update_violation_status, get_violation_audit_log,
    get_student_violation_summary, get_violations_by_vehicle,
)
from app.schemas import VehicleIn, ViolationStatusUpdate
from app.auth import require_role

vehicles_router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])
violations_router = APIRouter(prefix="/api", tags=["violations"])
stats_router = APIRouter(prefix="/api/stats", tags=["stats"])

# Giữ đồng bộ tay với frontend/src/utils/violationLabels.js — chỉ dùng khi xuất CSV.
VIOLATION_TYPE_LABELS = {
    'NO_HELMET': 'Không đội mũ',
    'PLATE_NOT_REGISTERED': 'Biển số lạ',
    'NO_PLATE': 'Không có biển số',
    'PLATE_OBSCURED': 'Biển số bị che/mờ',
    'PLATE_UNREADABLE': 'Không đọc được biển số',  # legacy, kept for historical data
    'PLATE_LOW_CONFIDENCE': 'Biển số cần kiểm tra',  # đợt 2, Bước 1 — đọc được nhưng không đủ tin cậy
    'MULTIPLE': 'Nhiều vi phạm',
    'RIDING_THROUGH_GATE': 'Xe chạy qua cổng',
    'TOO_MANY_RIDERS': 'Chở quá số người quy định',
}


@vehicles_router.get("")
def list_vehicles_json(current_user: dict = Depends(require_role("admin", "teacher", "management"))):
    """GET /api/vehicles — list all registered vehicles. Teacher sees only their class."""
    class_filter = (
        current_user.get("homeroom_class")
        if current_user.get("role") == "teacher" else None
    )
    return list_vehicles(student_class=class_filter)


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
    dry_run: bool = False,
    confirm: bool = False,
    current_user: dict = Depends(require_role("admin")),
):
    """
    POST /api/vehicles/import — bulk import vehicles from CSV.

    CSV format: plate_number,student_name,student_class (header required).
    Best-effort: processes all rows even if some fail.

    Query params:
    - dry_run=true : parse & validate only, return preview without writing to DB.
    - confirm=true : actually commit (alias for default behavior, kept for clarity).
      When neither is set, behaves like confirm=true (backwards-compatible).
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

    # Feature 11: Parse all rows first (even in dry-run)
    parsed_rows: list[dict] = []
    for row_num, row in enumerate(reader, start=2):
        plate = get_col(row, ['plate_number', 'plate', 'biển số'])
        student_name = get_col(row, ['student_name', 'name', 'tên', 'học sinh'])
        student_class = get_col(row, ['student_class', 'class', 'lớp', 'class_'])

        issues = []
        if not plate:
            issues.append('Missing plate_number')
        if not student_name:
            issues.append('Missing student_name')
        if not student_class:
            issues.append('Missing student_class')

        parsed_rows.append({
            'row': row_num,
            'plate': plate,
            'student_name': student_name,
            'student_class': student_class,
            'issues': issues,
        })

    # Feature 11: Dry-run — validate only, no DB writes
    if dry_run:
        errors = [{'row': r['row'], 'message': r['issues'][0]} for r in parsed_rows if r['issues']]
        preview = [r for r in parsed_rows if not r['issues']][:1]
        return {
            'created': len([r for r in parsed_rows if not r['issues']]),
            'skipped': len(errors),
            'errors': errors,
            'preview': [f"{r['plate']} | {r['student_name']} | {r['student_class']}" for r in preview],
        }

    # --- Confirm (or default): actually write to DB ---
    if dry_run:
        return  # unreachable, already handled above; kept for clarity

    def add_with_retry(plate: str, name: str, cls: str) -> bool:
        """Call add_vehicle with retry on SQLITE_LOCKED and similar errors."""
        import traceback as _tb
        for attempt in range(8):
            try:
                add_vehicle(plate, name, cls)
                return True
            except sqlite3.OperationalError as e:
                msg = str(e)
                if attempt < 7:
                    wait = 0.1 * (2 ** attempt)
                    print(f"[CSV import] row plate={plate} attempt {attempt+1} failed: {msg}, retrying in {wait:.2f}s")
                    _time_module.sleep(wait)
                    continue
                print(f"[CSV import] FINAL FAILURE plate={plate}: {msg}\n{_tb.format_exc()}")
                raise
        return False

    created = 0
    skipped = 0
    errors: list[dict] = []

    for r in parsed_rows:
        if r['issues']:
            errors.append({'row': r['row'], 'message': r['issues'][0]})
            skipped += 1
            continue

        try:
            add_with_retry(r['plate'], r['student_name'], r['student_class'])
            created += 1
        except ValueError as e:
            errors.append({'row': r['row'], 'message': str(e)})
            skipped += 1
        except Exception as e:
            errors.append({'row': r['row'], 'message': f'Unexpected error: {e}'})
            skipped += 1

    return {
        'total': created + skipped,
        'created': created,
        'skipped': skipped,
        'errors': errors,
    }


@vehicles_router.get("/export")
def export_vehicles_csv(current_user: dict = Depends(require_role("admin"))):
    """GET /api/vehicles/export — xuất toàn bộ xe đăng ký ra CSV (mở được bằng Excel)."""
    buffer = io.StringIO()
    buffer.write('﻿')  # UTF-8 BOM — Excel hiển thị đúng tiếng Việt có dấu
    writer = csv.writer(buffer)
    writer.writerow(['Biển số', 'Học sinh', 'Lớp'])
    for v in list_vehicles():
        writer.writerow([v['plate_number'], v['student_name'], v['student_class']])

    filename = f"xe_dang_ky_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@violations_router.get("/violations")
def list_violations_json(
    limit: int = 50,
    offset: int = 0,
    date_from: str = None,
    date_to: str = None,
    violation_type: str = None,
    plate: str = None,
    status: str = None,
    current_user: dict = Depends(require_role("admin", "teacher", "management")),
):
    """
    GET /api/violations — list violation events with pagination and filters.
    Teacher role automatically scoped to their homeroom_class (server-side enforcement).

    Query params:
        limit: results per page (default 50, max 200)
        offset: skip N results (default 0)
        date_from: ISO timestamp start (inclusive)
        date_to: ISO timestamp end (inclusive)
        violation_type: e.g. 'NO_HELMET', 'PLATE_NOT_REGISTERED'
        plate: filter by plate number (partial match)
        status: e.g. 'needs_review' (đợt 2, Bước 1)
    """
    import app.db as db
    # Feature 9: server-side scope enforcement for teacher role
    class_filter = (
        current_user.get("homeroom_class")
        if current_user.get("role") == "teacher" else None
    )
    result = db.list_violations(
        limit=min(limit, 200),
        offset=offset,
        date_from=date_from,
        date_to=date_to,
        violation_type=violation_type,
        plate=plate,
        student_class=class_filter,
        status=status,
    )
    # Attach snapshot_url and clip_url to each item
    for row in result.get('items', []):
        if row.get('snapshot_path'):
            filename = row['snapshot_path'].split('/')[-1]
            row['snapshot_url'] = f'/media/{filename}'
        else:
            row['snapshot_url'] = None
        if row.get('clip_path'):
            clip_filename = row['clip_path'].split('/')[-1]
            row['clip_url'] = f'/media/{clip_filename}'
        else:
            row['clip_url'] = None
    return result


@violations_router.get("/violations/export")
def export_violations_csv(
    date_from: str = None,
    date_to: str = None,
    violation_type: str = None,
    plate: str = None,
    current_user: dict = Depends(require_role("admin")),
):
    """
    GET /api/violations/export — xuất toàn bộ vi phạm khớp filter ra CSV (mở
    được trực tiếp bằng Excel). Cùng filter với GET /api/violations, không
    phân trang — dùng lại list_violations() với limit lớn thay vì viết lại
    SQL riêng.
    """
    import app.db as db
    result = db.list_violations(
        limit=100000, offset=0,
        date_from=date_from, date_to=date_to,
        violation_type=violation_type, plate=plate,
    )

    buffer = io.StringIO()
    buffer.write('﻿')  # UTF-8 BOM — để Excel hiển thị đúng tiếng Việt có dấu
    writer = csv.writer(buffer)
    writer.writerow([
        'Thời gian', 'Loại vi phạm', 'Biển số đọc được', 'Biển số khớp',
        'Học sinh', 'Lớp', 'Tư thế',
    ])
    for row in result['items']:
        # MULTIPLE → liệt kê rõ từng lỗi (violation_details), không chỉ "Nhiều vi phạm"
        types = [t for t in (row.get('violation_details') or '').split(',') if t] or [row.get('violation_type', '')]
        writer.writerow([
            row.get('timestamp', ''),
            ' + '.join(VIOLATION_TYPE_LABELS.get(t, t) for t in types),
            row.get('plate_read') or '',
            row.get('plate_matched') or '',
            row.get('student_name') or '',
            row.get('student_class') or '',
            row.get('posture_status') or '',
        ])

    filename = f"vi_pham_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@stats_router.get("/summary")
def get_stats_summary(current_user: dict = Depends(require_role("management", "admin"))):
    """GET /api/stats/summary — violation statistics (management or admin)."""
    return get_violation_stats()


# ─── Feature 10: Violation status + audit log ───────────────────────────────────

_VIOLATION_STATUSES = {"reviewed", "resolved", "reopened"}


@violations_router.patch("/violations/{violation_id}/status")
def set_violation_status(
    violation_id: int,
    body: ViolationStatusUpdate,
    current_user: dict = Depends(require_role("admin", "security", "management")),
):
    """PATCH /api/violations/{id}/status — cập nhật trạng thái vi phạm."""
    if body.status not in _VIOLATION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of: {', '.join(_VIOLATION_STATUSES)}",
        )
    ok = update_violation_status(
        violation_id, body.status, current_user["username"], body.note
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Violation not found")
    return {"status": "ok"}


@violations_router.get("/violations/{violation_id}/audit-log")
def get_violation_audit(
    violation_id: int,
    current_user: dict = Depends(require_role("admin", "security", "management")),
):
    """GET /api/violations/{id}/audit-log — lấy lịch sử xử lý vi phạm."""
    return get_violation_audit_log(violation_id)


# ─── Feature 2 + 6: Violation summary + history ────────────────────────────────

@vehicles_router.get("/violations-summary")
def violations_summary(
    current_user: dict = Depends(require_role("admin", "management", "teacher")),
):
    """
    GET /api/vehicles/violations-summary — tóm tắt vi phạm theo xe/học sinh.
    Teacher chỉ xem lớp mình (server-side filter).
    """
    class_filter = (
        current_user["homeroom_class"]
        if current_user.get("role") == "teacher" else None
    )
    return get_student_violation_summary(student_class=class_filter)


@vehicles_router.get("/{vehicle_id}/violations")
def vehicle_violation_history(
    vehicle_id: int,
    current_user: dict = Depends(require_role("admin", "management", "security", "teacher")),
):
    """
    GET /api/vehicles/{id}/violations — lịch sử vi phạm của 1 xe.
    Teacher chỉ xem xe thuộc lớp mình.
    """
    if current_user.get("role") == "teacher":
        vehicle = get_vehicle_by_id(vehicle_id)
        if vehicle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
        if vehicle.get("student_class") != current_user.get("homeroom_class"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return get_violations_by_vehicle(vehicle_id)
