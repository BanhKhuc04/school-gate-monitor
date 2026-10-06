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
import json
import time as _time_module
import sqlite3
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db import (
    add_vehicle, get_vehicle_by_plate, get_vehicle_by_id, list_vehicles,
    update_vehicle, delete_vehicle, list_violations, get_violation_stats,
    update_violation_status, update_violation_issues, get_violation_audit_log,
    get_student_violation_summary, get_violations_by_vehicle,
    add_roster_entry, bulk_add_roster, list_roster, delete_roster_entry,
    get_roster_entry, get_vehicle_by_student_id,
    save_import_log, get_import_log, payload_hash_from_bytes,
)
from app.schemas import VehicleIn, ViolationStatusUpdate, RosterEntryIn, Issue
from app.auth import require_role

vehicles_router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])
violations_router = APIRouter(prefix="/api", tags=["violations"])
stats_router = APIRouter(prefix="/api/stats", tags=["stats"])
roster_router = APIRouter(prefix="/api/roster", tags=["roster"])

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


def _teacher_class(user: dict) -> str | None:
    if user.get("role") != "teacher":
        return None
    school_class = (user.get("homeroom_class") or "").strip()
    if not school_class:
        raise HTTPException(status_code=403, detail="Teacher has no assigned class")
    return school_class


@vehicles_router.get("")
def list_vehicles_json(current_user: dict = Depends(require_role("admin", "teacher", "management"))):
    """GET /api/vehicles — list all registered vehicles. Teacher sees only their class."""
    class_filter = _teacher_class(current_user)
    return list_vehicles(student_class=class_filter)


@vehicles_router.post("", status_code=status.HTTP_201_CREATED)
def add_vehicle_json(
    body: VehicleIn,
    current_user: dict = Depends(require_role("admin"))
):
    """POST /api/vehicles — add a new vehicle (admin only).
    T2.3: truyền đủ các trường mở rộng (photo_path, dob, phone, student_id) xuống DB
    — bug cũ chỉ gọi add_vehicle với 3 tham số, làm mất hồ sơ."""
    try:
        add_vehicle(
            body.plate_number, body.student_name, body.student_class,
            photo_path=body.photo_path, dob=body.dob,
            phone=body.phone, student_id=body.student_id,
        )
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
    success = update_vehicle(
        vehicle_id,
        body.plate_number, body.student_name, body.student_class,
        photo_path=body.photo_path, dob=body.dob,
        phone=body.phone, student_id=body.student_id,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return get_vehicle_by_plate(body.plate_number)


@vehicles_router.get("/{vehicle_id:int}", name="get_vehicle_detail")
def get_vehicle_detail_json(
    vehicle_id: int,
    current_user: dict = Depends(require_role("admin", "management", "teacher")),
):
    """GET /api/vehicles/{id} — full record (kèm photo_path, dob, phone, student_id).
    Teacher: 403 nếu không thuộc lớp mình (trả 404 để không lộ tồn tại).
    T2.3 — dùng converter `:int` để không match `/export`, `/import`,
    `/violations-summary` (những path này được khai báo trước)."""
    vehicle = get_vehicle_by_id(vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    if current_user.get("role") == "teacher":
        if vehicle.get("student_class") != (current_user.get("homeroom_class") or "").strip():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return vehicle


@vehicles_router.delete("/{vehicle_id:int}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle_json(vehicle_id: int, current_user: dict = Depends(require_role("admin"))):
    """DELETE /api/vehicles/{id} — delete a vehicle (admin only).
    T2.3 — dùng `:int` converter để không ăn nhầm `/export`, `/import`."""
    success = delete_vehicle(vehicle_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return None


@vehicles_router.post("/import")
def import_vehicles_csv(
    file: UploadFile = File(...),
    dry_run: bool = False,
    confirm: bool = False,
    import_id: str | None = None,
    current_user: dict = Depends(require_role("admin")),
):
    """
    POST /api/vehicles/import — bulk import vehicles from CSV.

    CSV format: plate_number,student_name,student_class [, student_id, dob, phone]
    (header required). Best-effort: processes all rows even if some fail.

    Query params:
    - dry_run=true : parse & validate only, return preview without writing to DB.
    - confirm=true : actually commit (alias for default behavior, kept for clarity).
      When neither is set, behaves like confirm=true (backwards-compatible).
    - import_id (optional): client-generated UUID cho idempotency. Server ghi nhận
      và trả về `import_id` đã dùng; nếu gọi 2 lần với cùng import_id thì lần
      2 trả về kết quả đã ghi nhận (chống gửi lặp).

    T2.5:
    - Decode UTF-8-SIG (tự loại BOM).
    - Hỗ trợ quoted field, newline trong quoted (csv stdlib).
    - Validation: trim tên/lớp; lớp rỗng → reject; phone chỉ chữ số + '+'.
    - Round-trip: xuất ra file rồi import lại DB trống phải giữ student_id/dob/phone/photo_path.
    - Giới hạn 5 MB / 10.000 dòng (cấu hình qua env CSV_IMPORT_MAX_BYTES/_ROWS).
    """
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Must upload a .csv file")

    # T2.5 — giới hạn kích thước file
    import os as _os
    max_bytes = int(_os.environ.get("CSV_IMPORT_MAX_BYTES", str(5 * 1024 * 1024)))
    max_rows = int(_os.environ.get("CSV_IMPORT_MAX_ROWS", "10000"))
    content = file.file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File quá lớn (>{max_bytes // (1024*1024)} MB). Vui lòng tách nhỏ.",
        )

    # T2.5 — utf-8-sig tự loại BOM
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="File phải UTF-8 (BOM optional).")

    # Parse quoted field chuẩn csv stdlib
    try:
        reader = csv.DictReader(io.StringIO(text))
    except csv.Error as e:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row")

    # T2.5 — chuẩn hoá header (lowercase, strip)
    fieldnames = [f.strip().lower() for f in reader.fieldnames]
    col_map = {k: v for k, v in zip(fieldnames, reader.fieldnames)}

    def get_col(row, keys):
        for k in keys:
            key_lower = k.lower()
            if key_lower in col_map:
                val = row.get(col_map[key_lower], "") or ""
                return val.strip() if val else ""
        return ''

    import re as _re
    _phone_re = _re.compile(r"^[+0-9 ()-]{6,20}$")

    # Parse all rows first
    parsed_rows: list[dict] = []
    for row_num, row in enumerate(reader, start=2):
        if row_num - 1 > max_rows:
            raise HTTPException(
                status_code=413,
                detail=f"CSV quá nhiều dòng (>{max_rows}). Vui lòng tách nhỏ.",
            )
        plate = get_col(row, ['plate_number', 'plate', 'biển số'])
        student_name = get_col(row, ['student_name', 'name', 'tên', 'học sinh'])
        student_class = get_col(row, ['student_class', 'class', 'lớp', 'class_'])
        student_id = get_col(row, ['student_id', 'mã số', 'mssv'])
        dob_val = get_col(row, ['dob', 'ngày sinh', 'birthday'])
        phone = get_col(row, ['phone', 'sđt', 'sdt', 'số điện thoại'])
        photo_path = get_col(row, ['photo_path', 'ảnh', 'photo', 'photo path'])

        issues = []
        if not plate:
            issues.append('Missing plate_number')
        if not student_name:
            issues.append('Missing student_name')
        if not student_class:
            issues.append('Missing student_class')
        elif not student_class.strip():
            issues.append('Blank student_class after trim')
        if dob_val:
            # Kiểm tra định dạng YYYY-MM-DD cơ bản
            if not _re.match(r"^\d{4}-\d{2}-\d{2}$", dob_val):
                issues.append(f'Invalid dob format: {dob_val!r} (YYYY-MM-DD)')
        if phone and not _phone_re.match(phone):
            issues.append(f'Invalid phone: {phone!r}')

        parsed_rows.append({
            'row': row_num,
            'plate': plate,
            'student_name': student_name,
            'student_class': student_class,
            'student_id': student_id or None,
            'dob': dob_val or None,
            'phone': phone or None,
            'photo_path': photo_path or None,
            'issues': issues,
        })

    # R4 — Idempotency lưu bền vững: nếu (import_id, payload_hash) đã có
    # trong import_log → trả lại kết quả cũ (chống submit lặp). Nếu
    # import_id cũ nhưng payload_hash khác → 409 (key trùng, nội dung đổi).
    payload_hash = payload_hash_from_bytes(content)
    if import_id:
        existing = get_import_log(import_id, payload_hash)
        if existing is not None:
            # Replay: trả lại response cũ và đánh dấu replay=True
            return {**existing, "replay": True, "import_id": import_id}
        # Check xung đột key (import_id cũ nhưng payload khác)
        from app.db import get_connection as _gc, _write_lock as _wl
        with _wl:
            conn_check = _gc()
            try:
                cur_check = conn_check.cursor()
                cur_check.execute(
                    "SELECT payload_hash FROM import_log WHERE import_id = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (import_id,),
                )
                row_check = cur_check.fetchone()
                if row_check and row_check["payload_hash"] != payload_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"import_id {import_id!r} đã dùng với file khác; "
                            "dùng import_id mới hoặc đợi kết quả cũ phản hồi."
                        ),
                    )
            finally:
                conn_check.close()

    # Dry-run — validate only
    if dry_run:
        errors = []
        for r in parsed_rows:
            for issue in r['issues']:
                errors.append({'row': r['row'], 'message': issue})
        valid = [r for r in parsed_rows if not r['issues']]
        # T2.5 — preview phải phản ánh số thực tế sẽ tạo/bỏ/trùng
        existing_plates = {v["plate_number"] for v in list_vehicles()}
        duplicates = [r for r in valid if r['plate'] in existing_plates]
        new_rows = [r for r in valid if r['plate'] not in existing_plates]
        return {
            'created': len(new_rows),
            'duplicates': len(duplicates),
            'skipped': len(errors),
            'errors': errors,
            'preview': [
                f"{r['plate']} | {r['student_name']} | {r['student_class']}"
                for r in (new_rows + duplicates)[:3]
            ],
        }

    # --- Confirm (or default): actually write to DB ---
    def add_with_retry(plate: str, name: str, cls: str,
                       sid=None, dob=None, phone=None, photo_path=None) -> tuple[bool, str]:
        """Call add_vehicle with retry on SQLITE_LOCKED and similar errors.
        Returns (success, message)."""
        import traceback as _tb
        for attempt in range(8):
            try:
                add_vehicle(plate, name, cls,
                            photo_path=photo_path, dob=dob,
                            phone=phone, student_id=sid)
                return True, ""
            except sqlite3.OperationalError as e:
                msg = str(e)
                if attempt < 7:
                    wait = 0.1 * (2 ** attempt)
                    print(f"[CSV import] row plate={plate} attempt {attempt+1} failed: {msg}, retrying in {wait:.2f}s")
                    _time_module.sleep(wait)
                    continue
                print(f"[CSV import] FINAL FAILURE plate={plate}: {msg}\n{_tb.format_exc()}")
                return False, f"DB locked: {msg}"
        return False, "max retries exceeded"

    created = 0
    skipped = 0
    duplicates = 0
    errors: list[dict] = []

    for r in parsed_rows:
        if r['issues']:
            for issue in r['issues']:
                errors.append({'row': r['row'], 'message': issue})
            skipped += 1
            continue

        try:
            ok, msg = add_with_retry(
                r['plate'], r['student_name'], r['student_class'],
                sid=r.get('student_id'),
                dob=r.get('dob'),
                phone=r.get('phone'),
                photo_path=r.get('photo_path'),
            )
            if ok:
                created += 1
            else:
                # DB locked: coi như lỗi hệ thống, abort? Tiếp để có partial result.
                errors.append({'row': r['row'], 'message': msg})
                skipped += 1
        except ValueError as e:
            # Trùng biển hoặc validation lỗi
            msg = str(e)
            if "đã tồn tại" in msg or "duplicate" in msg.lower():
                duplicates += 1
                errors.append({'row': r['row'], 'message': msg, 'duplicate': True})
            else:
                errors.append({'row': r['row'], 'message': msg})
            skipped += 1
        except Exception as e:
            errors.append({'row': r['row'], 'message': f'Unexpected error: {e}'})
            skipped += 1

    # R4 — Lưu kết quả vào import_log để replay (chỉ khi confirm + có import_id)
    response_payload = {
        'total': created + skipped,
        'created': created,
        'duplicates': duplicates,
        'skipped': skipped,
        'errors': errors,
    }
    if import_id:
        try:
            save_import_log(import_id, payload_hash, response_payload)
        except Exception as e:
            # Log fail không chặn response 2 — print để debug
            print(f"[CSV import] save_import_log failed: {e}")
        response_payload["import_id"] = import_id
    return response_payload


@vehicles_router.get("/export")
def export_vehicles_csv(current_user: dict = Depends(require_role("admin"))):
    """GET /api/vehicles/export — xuất toàn bộ xe đăng ký ra CSV (mở được bằng Excel).
    T2.5 + R4 — round-trip đầy đủ: thêm student_id, dob, phone, photo_path
    để import lại không mất hồ sơ; chống CSV injection (Excel formula) bằng
    prefix `'` nếu giá trị bắt đầu bằng `=`, `+`, `-`, `@`, tab hoặc CR.
    """
    buffer = io.StringIO()
    buffer.write('﻿')  # UTF-8 BOM — Excel hiển thị đúng tiếng Việt có dấu
    writer = csv.writer(buffer)
    writer.writerow(['Biển số', 'Học sinh', 'Lớp', 'Mã số', 'Ngày sinh',
                     'SĐT', 'Photo Path'])

    def _safe(v):
        """Trả về input nếu an toàn; prefix "'" để chống formula injection."""
        if v is None:
            return ''
        s = str(v)
        if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + s
        return s

    for v in list_vehicles():
        writer.writerow([
            _safe(v['plate_number']),
            _safe(v['student_name']),
            _safe(v['student_class']),
            _safe(v.get('student_id') or ''),
            _safe(v.get('dob') or ''),
            _safe(v.get('phone') or ''),
            _safe(v.get('photo_path') or ''),
        ])

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
    class_filter = _teacher_class(current_user)
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
    # Attach snapshot_url, crop_snapshot_url, and clip_url to each item
    # T2.2 — dùng /api/media/... để áp dụng scope check server-side (auth +
    # teacher lớp). Trước đây là /media/{filename} (chỉ hoạt động khi
    # dev mount static). Production tắt static /media nên response trống.
    for row in result.get('items', []):
        if row.get('snapshot_path'):
            filename = row['snapshot_path'].split('/')[-1]
            row['snapshot_url'] = f'/api/media/snapshots/{filename}'
        else:
            row['snapshot_url'] = None
        # UT5: ảnh crop cận cảnh (NULL nếu vi phạm cũ chưa có)
        if row.get('crop_snapshot_path'):
            crop_filename = row['crop_snapshot_path'].split('/')[-1]
            row['crop_snapshot_url'] = f'/api/media/snapshots/{crop_filename}'
        else:
            row['crop_snapshot_url'] = None
        if row.get('clip_path'):
            clip_filename = row['clip_path'].split('/')[-1]
            row['clip_url'] = f'/api/media/clips/{clip_filename}'
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
        writer.writerow([
            row.get('timestamp', ''),
            VIOLATION_TYPE_LABELS.get(row.get('violation_type'), row.get('violation_type', '')),
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


@stats_router.get("/passages")
def get_passage_stats(date: str | None = None, gate_id: str | None = None,
                      current_user: dict = Depends(require_role("management", "admin", "security"))):
    """GET /api/stats/passages?date=YYYY-MM-DD&gate_id= — số lượt VÀO/RA theo
    người trong 1 ngày (giờ VN, mặc định hôm nay), tách đi bộ / đi xe."""
    from app.db import get_gate_passage_summary, vn_to_utc_range, vn_today_range
    if date is not None:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="date phải có dạng YYYY-MM-DD")
    start, end = vn_to_utc_range(date) if date else vn_today_range()
    return get_gate_passage_summary(start, end, gate_id)


# ─── Feature 10: Violation status + audit log ───────────────────────────────────

_VIOLATION_STATUSES = {"reviewed", "resolved", "reopened"}


@violations_router.patch("/violations/{violation_id}/status")
def set_violation_status(
    violation_id: int,
    body: ViolationStatusUpdate,
    current_user: dict = Depends(require_role("admin", "security", "management")),
):
    """PATCH /api/violations/{id}/status — cập nhật trạng thái vi phạm.

    T2.4 — client PHẢI gửi expected_version (atomic CAS). Thiếu → 422;
    mismatch → 409 với current_version để client biết refresh.
    """
    if body.status not in _VIOLATION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of: {', '.join(_VIOLATION_STATUSES)}",
        )
    if body.expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expected_version is required (T2.4 optimistic concurrency)",
        )
    result = update_violation_status(
        violation_id, body.status, current_user["username"], body.note,
        expected_version=body.expected_version,
    )
    if not result.get("ok"):
        if result.get("error") == "version_conflict":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "version_conflict",
                    "current_version": result["current_version"],
                    "message": "Violation đã bị cập nhật bởi operator khác; "
                               "tải lại và thử lại.",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Violation not found",
        )
    return {"status": "ok", "version": result["version"]}


class ViolationIssuesUpdate(ViolationStatusUpdate):
    """Đợt E2.1: cập nhật issues[] cho 1 violation.
    - issues: danh sách Issue, sẽ được serialize thành JSON và lưu vào
      violation_events.issues_json. Idempotent.
    - encounter_id / observed_at: optional override (chỉ set nếu chưa có)."""
    issues: list[Issue] = []
    encounter_id: str | None = None
    observed_at: str | None = None


def _json_str(value) -> str:
    """Helper serialize một field string thành JSON literal an toàn."""
    import json as _json
    if value is None:
        return "null"
    return _json.dumps(value)


@violations_router.patch("/violations/{violation_id}/issues")
def set_violation_issues(
    violation_id: int,
    body: ViolationIssuesUpdate,
    current_user: dict = Depends(require_role("admin", "security", "management")),
):
    """PATCH /api/violations/{id}/issues — cập nhật issues[] (Đợt E2.1).

    Pipeline gọi endpoint này khi:
    - OCR đến trễ (gộp thêm NO_PLATE/PLATE_OBSCURED/PLATE_LOW_CONFIDENCE).
    - EventManager xác nhận streak (gộp NO_HELMET/RIDING_THROUGH_GATE).
    - Bằng chứng bị thu hồi (status='deferred').

    Endpoint idempotent — ghi đè issues_json bằng danh sách mới. Trường
    nghiệp vụ (status nghiệp vụ 'reviewed'/'resolved') không bị động vào.
    """
    issues_json = None
    if body.issues is not None:
        parts = []
        for iss in body.issues:
            parts.append(
                f'{{"code":{_json_str(iss.code)},'
                f'"status":{_json_str(iss.status)},'
                f'"reason":{_json_str(iss.reason)},'
                f'"sample_count":{int(iss.sample_count)},'
                f'"evidence_ref":{_json_str(iss.evidence_ref)}}}'
            )
        issues_json = "[" + ",".join(parts) + "]"
    ok = update_violation_issues(
        violation_id,
        issues_json,
        observed_at=body.observed_at,
        encounter_id=body.encounter_id,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Violation not found")
    return {"status": "ok"}


@violations_router.get("/violations/{violation_id}/issues")
def get_violation_issues(
    violation_id: int,
    current_user: dict = Depends(require_role("admin", "teacher", "management")),
):
    """GET /api/violations/{id}/issues — đọc issues[] hiện tại."""
    import app.db as db
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, issues_json, encounter_id, observed_at "
            "FROM violation_events WHERE id = ?",
            (violation_id,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Violation not found")
    row = dict(row)
    return {
        "violation_id": violation_id,
        "issues": row.get("issues_json"),
        "encounter_id": row.get("encounter_id"),
        "observed_at": row.get("observed_at"),
    }


@violations_router.get("/violations/encounters")
def list_violation_encounters(
    date_from: str = None,
    date_to: str = None,
    limit: int = 50,
    offset: int = 0,
    plate: str = None,
    violation_type: str = None,
    current_user: dict = Depends(require_role("admin", "teacher", "management")),
):
    """GET /api/violations/encounters — gom vi phạm theo encounter_id.

    Pre-E3 fix plan: gom encounter TRƯỚC khi phân trang — total = tổng số
    encounter_id khác nhau khớp filter (KHÔNG phải số row trong trang hiện tại).
    Pagination theo số encounter (1-200/offset >=0).

    Trả về danh sách EncounterGroup. Nếu 1 record chưa có encounter_id,
    coi như encounter_id = 'legacy-{id}' để vẫn hiển thị. UI dùng cho
    board trạng thái (đợt E2.2).

    display_status:
      - resolved: Tất cả issue đều resolved.
      - red: Có ≥1 issue confirmed (chưa resolved) — lỗi đã xác nhận, vẫn đỏ.
      - yellow: Chỉ có issue pending/deferred/conflict — cần xem xét.
      - gray: Chưa có issue nào (legacy record chưa có issues_json).
    """
    import app.db as db
    class_filter = _teacher_class(current_user)
    # Validate limit/offset per plan: limit 1-200, offset >= 0
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))
    result = db.list_violation_encounters(
        limit=safe_limit,
        offset=safe_offset,
        date_from=date_from,
        date_to=date_to,
        student_class=class_filter, plate=plate, violation_type=violation_type,
    )
    # Thêm URL cho ảnh/clip (giữ nguyên response shape)
    for bucket in result.get('items', []):
        if bucket.get('snapshot_path'):
            bucket['snapshot_url'] = f"/api/media/snapshots/{bucket['snapshot_path'].replace(chr(92), '/').split('/')[-1]}"
        if bucket.get('crop_snapshot_path'):
            bucket['crop_snapshot_url'] = f"/api/media/snapshots/{bucket['crop_snapshot_path'].replace(chr(92), '/').split('/')[-1]}"
        if bucket.get('clip_path'):
            bucket['clip_url'] = f"/api/media/clips/{bucket['clip_path'].replace(chr(92), '/').split('/')[-1]}"
    return result


@violations_router.get("/violations/{violation_id}")
def get_violation_detail(violation_id: int,
    current_user: dict = Depends(require_role("admin", "security", "teacher", "management"))):
    import app.db as db
    school_class = _teacher_class(current_user)
    conn = db.get_connection()
    try:
        row = conn.execute("SELECT ve.*, rv.student_name, rv.student_class FROM violation_events ve LEFT JOIN registered_vehicles rv ON rv.plate_number=ve.plate_matched WHERE ve.id=?", (violation_id,)).fetchone()
        if row is None or (school_class and row['student_class'] != school_class):
            raise HTTPException(status_code=404, detail="Violation not found")
        result = dict(row)
        result['issues'] = json.loads(result.get('issues_json') or '[]')
        for key, kind in [('snapshot_path','snapshots'),('crop_snapshot_path','snapshots'),('clip_path','clips')]:
            value = result.get(key)
            result[key.replace('_path','_url')] = f"/api/media/{kind}/{value.replace(chr(92), '/').split('/')[-1]}" if value else None
        return result
    finally:
        conn.close()


@violations_router.get("/violations/{violation_id}/audit-log")
def get_violation_audit(
    violation_id: int,
    current_user: dict = Depends(require_role("admin", "security", "management")),
):
    """GET /api/violations/{id}/audit-log — lấy lịch sử xử lý vi phạm."""
    return get_violation_audit_log(violation_id)


class ClearViolationsRequest(BaseModel):
    scope: Literal["test", "all"]


@violations_router.post("/violations/clear")
def clear_violations_endpoint(
    payload: ClearViolationsRequest,
    current_user: dict = Depends(require_role("admin")),
):
    """
    POST /api/violations/clear — xóa vi phạm.
    scope=test: chỉ vi phạm của video test (ảnh/clip xóa hẳn).
    scope=all: tất cả; DB được sao lưu trước, ảnh/clip dời vào
    data/backups/truoc_khi_xoa_vi_pham_<giờ>/ nên khôi phục được.
    """
    import os
    import shutil
    import app.db as db
    from app.config import BACKUP_DIR, BASE_DIR, SNAPSHOTS_DIR
    started = datetime.now()
    backup = None
    if payload.scope == "all":
        backup = os.path.join(BACKUP_DIR, f"truoc_khi_xoa_vi_pham_{started:%Y%m%d_%H%M%S}")
        os.makedirs(backup, exist_ok=True)
        db.backup_database(os.path.join(backup, "app.db"))
    result = db.clear_violations(test_only=payload.scope == "test")
    moved = removed = 0
    for name in result["media"]:
        path = os.path.join(SNAPSHOTS_DIR, name)
        if not os.path.isfile(path):
            continue
        try:
            if backup:
                shutil.move(path, os.path.join(backup, name))
                moved += 1
            else:
                os.remove(path)
                removed += 1
        except OSError:
            pass  # a clip still being written; the record itself is gone
    shown = os.path.relpath(backup, BASE_DIR) if backup else None
    try:
        db.log_maintenance_run(
            "clear_violations", started.isoformat(), datetime.now().isoformat(), True,
            {"by": current_user.get("username"), "scope": payload.scope,
             "deleted": result["deleted"], "media_moved": moved, "media_removed": removed,
             "backup": shown})
    except Exception:
        pass
    return {"deleted": result["deleted"], "media_moved": moved,
            "media_removed": removed, "backup": shown}


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


@vehicles_router.get("/{vehicle_id:int}/violations")
def vehicle_violation_history(
    vehicle_id: int,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(require_role("admin", "management", "security", "teacher")),
):
    """
    GET /api/vehicles/{id}/violations — lịch sử vi phạm của 1 xe.
    Teacher chỉ xem xe thuộc lớp mình.
    T2.3 — thêm `limit` (1..200) và `offset` (>=0) cho server pagination;
    trả `{items, total, limit, offset}` thay vì list thuần.
    """
    if current_user.get("role") == "teacher":
        vehicle = get_vehicle_by_id(vehicle_id)
        if vehicle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
        if vehicle.get("student_class") != current_user.get("homeroom_class"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))
    return get_violations_by_vehicle(
        vehicle_id, limit=safe_limit, offset=safe_offset
    )


# ─── UT8: upload ảnh học sinh + roster + public register ─────────────────────

import os as _os
from app.config import SNAPSHOTS_DIR as _SNAPSHOTS_DIR

# Thư mục con cho ảnh hồ sơ — tách khỏi snapshots vi phạm để dễ quản lý
_STUDENT_PHOTOS_DIR = _os.path.join(_os.path.dirname(_SNAPSHOTS_DIR), "student_photos")
_os.makedirs(_STUDENT_PHOTOS_DIR, exist_ok=True)

# R5 — giới hạn kích thước + pixel decode ảnh
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB (admin) — public đã có 5MB riêng
_MAX_PIXELS = 4096 * 4096  # ~16.7M pixel; PIL sẽ check


def _decode_and_save_image(
    raw_bytes: bytes,
    original_filename: str | None,
    student_photos_dir: str,
    max_bytes: int = _MAX_UPLOAD_BYTES,
    max_pixels: int = _MAX_PIXELS,
) -> dict:
    """R5 — helper decode ảnh thật + giới hạn + UUID.

    Args:
        raw_bytes: bytes đã đọc (đã check max_bytes).
        original_filename: tên gốc client gửi (chỉ dùng cho gợi ý extension).
        student_photos_dir: thư mục lưu file.
        max_bytes: bytes tối đa (mặc định 5MB).
        max_pixels: pixel tối đa sau decode (mặc định ~16M).

    Returns:
        dict {photo_path, photo_url, width, height, format}.

    Raises:
        HTTPException 400 nếu MIME/extension lạ, decode fail, pixel limit.
    """
    import io as _io
    import uuid as _uuid
    from PIL import Image as _Image, UnidentifiedImageError

    if len(raw_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Ảnh quá lớn (> {max_bytes // (1024*1024)} MB). Vui lòng resize.",
        )

    # Decode thật — KHÔNG tin MIME/extension client gửi.
    try:
        img = _Image.open(_io.BytesIO(raw_bytes))
        img.load()  # force decode để bắt truncated/corrupt
    except (UnidentifiedImageError, OSError, _Image.DecompressionBombError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"File không phải ảnh hợp lệ hoặc bị hỏng ({type(e).__name__}).",
        )
    # Pixel limit (PIL có sẵn Image.MAX_IMAGE_PIXELS nhưng check rõ ràng hơn)
    width, height = img.size
    if width * height > max_pixels:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Ảnh quá lớn ({width}x{height} = {width*height} pixel > {max_pixels})."
            ),
        )

    # Chỉ cho phép RGB/A; convert nếu palette/CMYK/etc.
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")
    fmt = "JPEG" if img.mode == "RGB" else "PNG"
    ext = ".jpg" if fmt == "JPEG" else ".png"

    # Tên UUID — KHÔNG dùng timestamp (tránh trùng mili giây)
    name = f"{_uuid.uuid4().hex}{ext}"
    full_path = _os.path.join(student_photos_dir, name)
    # R1 — preflight disk trước khi save (ảnh JPEG ~75% bytes gốc; PNG có thể
    # lớn hơn; dùng max_bytes làm trần dự báo). require_space raise ValueError
    # → caller chuyển HTTPException 507.
    from app.storage_budget import require_space
    try:
        require_space(full_path, expected_bytes=max_bytes + 4 * 1024 * 1024)
    except ValueError as e:
        raise HTTPException(status_code=507, detail=f"không đủ dung lượng: {e}")
    try:
        img.save(full_path, format=fmt, quality=85, strip=True)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Lỗi ghi file: {e}")

    rel_path = f"data/student_photos/{name}"
    # R5 — trả URL media dùng được ở production. /api/media/student-photos/...
    # là route có auth/scope (xem app/api/media.py), KHÔNG dùng /media/...
    # vì production tắt static mount.
    photo_url = f"/api/media/student-photos/{name}"
    return {
        "photo_path": rel_path,
        "photo_url": photo_url,
        "width": width,
        "height": height,
        "format": fmt,
    }


@vehicles_router.post("/upload-photo")
def upload_student_photo(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("admin")),
):
    """UT8 + R5: POST /api/vehicles/upload-photo — admin upload ảnh mặt học sinh.

    R5 thay đổi:
    - Decode ảnh thật qua PIL; reject nếu không phải ảnh hợp lệ.
    - Giới hạn bytes (5MB) + pixel (~16M).
    - Tên file UUID hex (24-32 char) + extension theo format decode.
    - Strip metadata khi save.
    - URL trả về là /api/media/student-photos/... (auth), KHÔNG /media/...
      vì production tắt static mount.
    """
    # Đọc bytes + check size NGAY để tránh nạp file 5GB vào RAM
    raw = file.file.read(_MAX_UPLOAD_BYTES + 1)
    result = _decode_and_save_image(
        raw_bytes=raw,
        original_filename=file.filename,
        student_photos_dir=_STUDENT_PHOTOS_DIR,
    )
    return result


# Roster endpoints (admin only)
@roster_router.get("")
def get_roster(current_user: dict = Depends(require_role("admin"))):
    """GET /api/roster — admin xem danh sách mã số hợp lệ."""
    return list_roster()


@roster_router.post("", status_code=status.HTTP_201_CREATED)
def add_roster(
    body: RosterEntryIn,
    current_user: dict = Depends(require_role("admin")),
):
    """POST /api/roster — admin thêm 1 mã số vào roster."""
    try:
        add_roster_entry(body.student_id, body.student_name, body.student_class)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True}


@roster_router.post("/import")
def import_roster(
    rows: list[RosterEntryIn],
    current_user: dict = Depends(require_role("admin")),
):
    """POST /api/roster/import — bulk thêm nhiều mã số."""
    result = bulk_add_roster([r.model_dump() for r in rows])
    return result


@roster_router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_roster(
    student_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    """DELETE /api/roster/{student_id} — xóa 1 mã số."""
    if not delete_roster_entry(student_id):
        raise HTTPException(status_code=404, detail="Mã số không tồn tại trong roster")
    return None
