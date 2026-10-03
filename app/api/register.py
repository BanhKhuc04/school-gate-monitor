"""
UT8: Public registration endpoints — không yêu cầu đăng nhập.

- GET  /api/register/lookup?student_id=... : tra cứu học sinh trong roster
- POST /api/register/upload-photo : upload ảnh mặt (trước khi submit form)
- POST /api/register : tạo xe đăng ký (student_id phải có trong roster,
                        đồng thời chưa đăng ký xe nào)

T2.5: gate toàn bộ endpoint qua PUBLIC_REGISTER_ENABLED (mặc định TẮT).
Khi tắt trả 503 {enabled: false, detail}; KHÔNG lộ roster/biển đã đăng ký.
"""
import os
import time

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from fastapi.responses import JSONResponse
from app.config import SNAPSHOTS_DIR, PUBLIC_REGISTER_ENABLED
from app.db import (
    get_roster_entry,
    get_vehicle_by_student_id,
    add_vehicle,
)
from app.schemas import PublicRegisterIn

router = APIRouter(prefix="/api/register", tags=["register"])

_STUDENT_PHOTOS_DIR = os.path.join(os.path.dirname(SNAPSHOTS_DIR), "student_photos")
os.makedirs(_STUDENT_PHOTOS_DIR, exist_ok=True)

# Endpoint không cần auth (public) — giới hạn kích thước file để tránh bị
# spam làm đầy ổ đĩa, admin upload không bị giới hạn này (đã đăng nhập).
_MAX_PUBLIC_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB


def _disabled_response():
    """Helper: trả 503 khi public register bị tắt."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Đăng ký công khai đang tạm đóng.", "enabled": False},
    )


@router.post("/upload-photo")
def public_upload_photo(file: UploadFile = File(...)):
    """POST /api/register/upload-photo — học sinh tự upload ảnh mặt, không cần đăng nhập.
    Trả về photo_path để đính kèm vào body POST /api/register.
    T2.5: gate theo PUBLIC_REGISTER_ENABLED — khi tắt trả 503, không lộ thông tin.
    R5: dùng helper _decode_and_save_image (decode PIL thật + giới hạn bytes/pixel +
    UUID filename + strip metadata); KHÔNG dùng MIME/extension client gửi."""
    if not PUBLIC_REGISTER_ENABLED:
        return _disabled_response()
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File phải là ảnh (image/*)")
    # Đọc bytes + check size NGAY
    raw = file.file.read(_MAX_PUBLIC_UPLOAD_BYTES + 1)
    # Tái sử dụng helper của admin (cùng giới hạn) — vì logic giống nhau
    from app.api.admin import _decode_and_save_image
    result = _decode_and_save_image(
        raw_bytes=raw,
        original_filename=file.filename,
        student_photos_dir=_STUDENT_PHOTOS_DIR,
        max_bytes=_MAX_PUBLIC_UPLOAD_BYTES,
    )
    return result


def _normalize_plate(s: str) -> str | None:
    if not s:
        return None
    import re
    s = s.upper().replace("Đ", "D")
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s if len(s) >= 4 else None


@router.get("/lookup")
def lookup_student(student_id: str):
    """GET /api/register/lookup?student_id=X — frontend gọi khi user nhập
    student_id, trả về tên + lớp từ roster (nếu có) + trạng thái đã đăng ký xe.
    T2.5: gate theo PUBLIC_REGISTER_ENABLED — khi tắt trả 503, không lộ roster."""
    if not PUBLIC_REGISTER_ENABLED:
        return _disabled_response()
    sid = (student_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Vui lòng nhập mã số")
    entry = get_roster_entry(sid)
    if entry is None:
        # Trả 200 với found=False để frontend phân biệt "không tồn tại" với
        # lỗi server — UX tốt hơn 404.
        return {"found": False}
    existing = get_vehicle_by_student_id(sid)
    return {
        "found": True,
        "student_id": entry["student_id"],
        "student_name": entry["student_name"],
        "student_class": entry["student_class"],
        "already_registered": existing is not None,
        "existing_plate": existing["plate_number"] if existing else None,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def public_register(body: PublicRegisterIn):
    """POST /api/register — submit form đăng ký xe. KHÔNG cần auth.

    Quy tắc:
    - student_id phải có trong roster (verified ở lookup trước, double-check ở đây)
    - student_id chưa đăng ký xe (mỗi học sinh chỉ có 1 xe — nếu cần đổi,
      liên hệ admin)
    T2.5: gate theo PUBLIC_REGISTER_ENABLED — khi tắt trả 503, không lộ dữ liệu.
    """
    if not PUBLIC_REGISTER_ENABLED:
        return _disabled_response()
    sid = (body.student_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Thiếu mã số học sinh")

    entry = get_roster_entry(sid)
    if entry is None:
        raise HTTPException(
            status_code=403,
            detail="Mã số không có trong danh sách hợp lệ. Vui lòng liên hệ quản trị.",
        )

    if get_vehicle_by_student_id(sid) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Mã số {sid} đã đăng ký xe. Vui lòng liên hệ quản trị để thay đổi.",
        )

    plate = _normalize_plate(body.plate_number)
    if not plate:
        raise HTTPException(status_code=400, detail="Biển số không hợp lệ")

    try:
        new_id = add_vehicle(
            plate,
            entry["student_name"],
            entry["student_class"],
            photo_path=body.photo_path,
            dob=body.dob,
            phone=body.phone,
            student_id=sid,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {
        "ok": True,
        "vehicle_id": new_id,
        "plate_number": plate,
        "student_name": entry["student_name"],
        "student_class": entry["student_class"],
    }