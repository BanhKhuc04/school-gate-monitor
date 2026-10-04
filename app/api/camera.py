"""
Cấu hình nguồn camera per-gate (admin).

GET  /api/camera            — danh sách gate + nguồn đang dùng + preset gợi ý
POST /api/camera/{gate_id}  — đổi nguồn camera, lưu DB rồi restart pipeline gate đó

Nguồn lưu ở bảng gate_camera_source (app/db.py) đè lên giá trị env var khi
pipeline được tạo (xem app/cv/pipeline.py::_create_pipeline_locked).
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.auth import require_role
from app.config import GATES, CAMERA_PRESETS
from app.db import get_gate_camera_source, set_gate_camera_source

router = APIRouter(prefix="/api/camera", tags=["camera"])


class CameraSourcePayload(BaseModel):
    source: str = Field(..., min_length=1, max_length=500)


@router.get("")
def list_camera_sources(current_user: dict = Depends(require_role("admin"))):
    gates = []
    for gate_id, cfg in GATES.items():
        saved = get_gate_camera_source(gate_id)
        gates.append({
            "id": gate_id,
            "name": cfg.get("name", gate_id),
            "source": str(saved if saved is not None else cfg.get("source")),
        })
    return {"gates": gates, "presets": CAMERA_PRESETS}


@router.post("/{gate_id}")
def set_camera_source(gate_id: str, payload: CameraSourcePayload,
                      current_user: dict = Depends(require_role("admin"))):
    if gate_id not in GATES:
        raise HTTPException(status_code=404, detail=f"Không có cổng '{gate_id}'")
    source = payload.source.strip()
    if not source:
        raise HTTPException(status_code=400, detail="Nguồn camera không được để trống")

    set_gate_camera_source(gate_id, source)

    # Restart nạp lại model + mở nguồn mới (~vài giây). Môi trường không có CV
    # libs (test) thì chỉ lưu DB — pipeline sẽ dùng nguồn này ở lần khởi động sau.
    restarted = False
    try:
        from app.cv.pipeline import restart_pipeline
        restart_pipeline(gate_id)
        restarted = True
    except ImportError:
        pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Đã lưu nguồn nhưng không khởi động lại được camera: {e}")

    return {"gate_id": gate_id, "source": source, "restarted": restarted}
