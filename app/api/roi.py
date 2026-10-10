"""
Vùng nhận diện (ROI) và đường cắt gate (gate_line) API.

ROI:
  GET  /api/roi/{gate_id}   — lấy vùng đang cấu hình (admin)
  POST /api/roi/{gate_id}   — lưu vùng mới, áp dụng sống nếu pipeline đang chạy (admin)

Gate line (Đợt 4, D4.1):
  GET  /api/roi/{gate_id}/line   — lấy đường cắt đang cấu hình (admin)
  POST /api/roi/{gate_id}/line   — lưu đường cắt mới, áp dụng sống nếu pipeline đang chạy (admin)
  DELETE /api/roi/{gate_id}/line — xóa đường cắt (dùng pose fallback)
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.auth import require_role
from app.db import get_gate_roi, set_gate_roi, get_gate_line, set_gate_line

router = APIRouter(prefix="/api/roi", tags=["roi"])


class RoiPayload(BaseModel):
    points: list[list[float]]


class GateLinePayload(BaseModel):
    """Đường cắt gate: 2 điểm tọa độ chuẩn hóa [0,1].

    Lưu ý: đường cắt là THAY THẾ cho pose-based riding detection.
    Khi chưa cấu hình đường cắt, hệ thống dùng pose fallback cũ.
    """
    line: list[float]  # [x1, y1, x2, y2]


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


# ─── Gate line endpoints (Đợt 4, D4.1) ───────────────────────────────────────

@router.get("/{gate_id}/line")
def read_gate_line(gate_id: str, current_user: dict = Depends(require_role("admin"))):
    """Lấy đường cắt gate đang cấu hình. Trả None nếu chưa cấu hình."""
    return {"gate_id": gate_id, "line": get_gate_line(gate_id)}


@router.post("/{gate_id}/line")
def write_gate_line(gate_id: str, payload: GateLinePayload,
                    current_user: dict = Depends(require_role("admin"))):
    """Lưu đường cắt mới cho gate.

    Khi có đường cắt hợp lệ, pipeline dùng nó thay pose-based riding detection.
    Khi chưa cấu hình (None), dùng pose fallback cũ.
    """
    try:
        set_gate_line(gate_id, payload.line)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Áp dụng sống vào pipeline đang chạy (nếu có)
    try:
        from app.cv.pipeline import get_pipeline
        get_pipeline(gate_id).set_gate_line(payload.line)
    except Exception:
        pass  # Pipeline chưa chạy — DB đã lưu

    return {"gate_id": gate_id, "line": payload.line}


@router.delete("/{gate_id}/line")
def delete_gate_line(gate_id: str, current_user: dict = Depends(require_role("admin"))):
    """Xóa đường cắt gate — hệ thống quay về pose fallback cũ."""
    set_gate_line(gate_id, None)
    try:
        from app.cv.pipeline import get_pipeline
        get_pipeline(gate_id).set_gate_line(None)
    except Exception:
        pass
    return {"gate_id": gate_id, "line": None}
