"""
Vùng nhận diện (ROI) API.

GET  /api/roi/{gate_id}   — lấy vùng đang cấu hình (admin)
POST /api/roi/{gate_id}   — lưu vùng mới, áp dụng sống nếu pipeline đang chạy (admin)
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.auth import require_role
from app.db import get_gate_roi, set_gate_roi

router = APIRouter(prefix="/api/roi", tags=["roi"])


class RoiPayload(BaseModel):
    points: list[list[float]]


@router.get("/{gate_id}")
def read_roi(gate_id: str, current_user: dict = Depends(require_role("admin"))):
    return {"gate_id": gate_id, "points": get_gate_roi(gate_id)}


@router.post("/{gate_id}")
def write_roi(gate_id: str, payload: RoiPayload, current_user: dict = Depends(require_role("admin"))):
    from app.cv.roi import parse_points

    try:
        points = parse_points(payload.points)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # pipeline.set_roi() vừa lưu DB vừa áp dụng sống. Nếu pipeline gate này
    # chưa chạy được (vd. môi trường test không có ultralytics/camera thật),
    # ghi thẳng xuống DB để vẫn lưu được cấu hình.
    try:
        from app.cv.pipeline import get_pipeline
        get_pipeline(gate_id).set_roi(points)
    except Exception:
        set_gate_roi(gate_id, points or [])

    return {"gate_id": gate_id, "points": points}
