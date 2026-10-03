"""Admin camera selection. Accepted changes are verified by the capture thread."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictInt, StrictStr

from app.auth import require_role
from app.config import CAMERA_PRESETS, GATES
from app.cv.camera_sources import display_source, normalize_source, validate_source
from app.cv.camera_switch import CameraBusy
from app.db import (
    get_gate_camera_source,
    upsert_camera, get_camera, list_cameras_for_gate, delete_camera,
)
import app.db as db_module

router = APIRouter(prefix='/api/camera', tags=['camera'])


class CameraSourcePayload(BaseModel):
    source: StrictStr | StrictInt | None = None
    preset_id: StrictStr | None = None


class CameraMappingPayload(BaseModel):
    """Đợt 1 (System Stability): mapping 1 camera vào 1 gate + vai trò.
    Đây là nền tảng cho cấu hình nhiều camera thuộc cùng 1 cổng vật lý
    (vd. Imou trước + Imou sau cho cổng chính)."""
    camera_id: StrictStr
    role: StrictStr  # 'front' | 'rear' | 'aux'
    source: StrictStr | StrictInt
    enabled: int = 1


def _gate(gate_id):
    if gate_id not in GATES:
        raise HTTPException(404, 'Không tìm thấy cổng camera.')
    return GATES[gate_id]


def _get_pipeline(gate_id):
    try:
        from app.cv.pipeline import get_existing_pipeline
        return get_existing_pipeline(gate_id)
    except ImportError:
        return None


def _camera_status(gate_id, pipeline):
    config = _gate(gate_id)
    if pipeline is not None:
        source = pipeline.camera_switch.source
        change = pipeline.camera_switch.status()
        health = pipeline.get_status()
    else:
        saved = get_gate_camera_source(gate_id)
        source = saved if saved is not None else config['source']
        change = {'current': display_source(source), 'pending': '', 'state': 'idle', 'error': None}
        health = {'running': False, 'thread_alive': False, 'camera_open': False, 'last_frame_age_sec': None}
    current_preset = next((f'preset-{i}' for i, preset in enumerate(CAMERA_PRESETS)
                           if str(normalize_source(preset['source'])) == str(source)), None)
    return {
        'gate_id': gate_id, 'name': config.get('name', gate_id), **change,
        'current_preset_id': current_preset,
        'presets': [{'id': f'preset-{i}', 'label': p['label'], 'source': display_source(p['source'])}
                    for i, p in enumerate(CAMERA_PRESETS)],
        'health': health,
    }


@router.get('')
def list_camera_gates(current_user: dict = Depends(require_role('admin'))):
    return {'gates': [{'id': key, 'name': value.get('name', key)} for key, value in GATES.items()]}


@router.get('/{gate_id}')
def read_camera_source(gate_id: str, current_user: dict = Depends(require_role('admin'))):
    _gate(gate_id)
    return _camera_status(gate_id, _get_pipeline(gate_id))


@router.post('/{gate_id}', status_code=202)
def write_camera_source(gate_id: str, payload: CameraSourcePayload,
                        current_user: dict = Depends(require_role('admin'))):
    _gate(gate_id)
    if (payload.source is None) == (payload.preset_id is None):
        raise HTTPException(422, 'Chọn một nguồn có sẵn hoặc nhập một nguồn tùy chỉnh.')
    source = payload.source
    if payload.preset_id is not None:
        preset = next((p for i, p in enumerate(CAMERA_PRESETS) if payload.preset_id == f'preset-{i}'), None)
        if preset is None:
            raise HTTPException(422, 'Nguồn có sẵn không hợp lệ. Vui lòng tải lại danh sách.')
        source = preset['source']
    try:
        source = validate_source(source)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    pipeline = _get_pipeline(gate_id)
    health = pipeline.get_status() if pipeline else {}
    if not health.get('thread_alive') or not health.get('running'):
        raise HTTPException(503, 'Pipeline chưa chạy. Kiểm tra trạng thái hệ thống và khởi động backend.')
    online = health.get('camera_open', False) and (health.get('last_frame_age_sec') or 0) < 5
    try:
        pipeline.camera_switch.request(source, camera_online=online)
    except CameraBusy as error:
        raise HTTPException(409, str(error)) from None
    return _camera_status(gate_id, pipeline)


# ─── Đợt 1: Multi-camera mapping (1 gate ↔ nhiều camera) ────────────────
# Endpoint dưới đây cho phép admin cấu hình nhiều camera cùng 1 cổng. Mỗi
# camera có `camera_id` ổn định và vai trò front/rear/aux. Pipeline sẽ
# chọn camera phù hợp theo từng giai đoạn (front cho hành vi/mũ/crossing,
# rear cho biển số + crop OCR — theo plan).

def _mask_camera_source(cam: dict) -> dict:
    """Che credentials khi trả về camera ra API."""
    if not cam:
        return cam
    masked = dict(cam)
    if cam.get('source'):
        masked['source'] = display_source(cam['source'])
    return masked


@router.get('/{gate_id}/cameras')
def list_gate_cameras(gate_id: str,
                      current_user: dict = Depends(require_role('admin'))):
    """Liệt kê camera thuộc cổng vật lý (che credentials)."""
    _gate(gate_id)
    cams = list_cameras_for_gate(gate_id, only_enabled=False)
    return {'gate_id': gate_id, 'cameras': [_mask_camera_source(c) for c in cams]}


@router.post('/{gate_id}/cameras', status_code=201)
def add_gate_camera(gate_id: str, payload: CameraMappingPayload,
                    current_user: dict = Depends(require_role('admin'))):
    """Tạo/cập nhật mapping camera ↔ gate + role. Idempotent — POST cùng
    `camera_id` sẽ UPSERT, không tạo row trùng. Trả về 201 nếu tạo mới,
    200 nếu cập nhật (qua header convention; backend hiện trả 201 cho cả 2
    để đơn giản — frontend kiểm tra theo `upserted` field)."""
    _gate(gate_id)
    if payload.role not in {'front', 'rear', 'aux'}:
        raise HTTPException(422, "role phải là 'front', 'rear' hoặc 'aux'.")
    try:
        validated_source = validate_source(payload.source)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    existing = get_camera(payload.camera_id)
    upserted = upsert_camera(
        camera_id=payload.camera_id,
        gate_id=gate_id,
        role=payload.role,
        source=validated_source,
        enabled=int(payload.enabled),
    )
    new_row = get_camera(payload.camera_id)
    return {'status': 'ok', 'upserted': upserted,
            'created': existing is None,
            'camera': _mask_camera_source(new_row)}


@router.delete('/{gate_id}/cameras/{camera_id}', status_code=200)
def remove_gate_camera(gate_id: str, camera_id: str,
                        current_user: dict = Depends(require_role('admin'))):
    """Xóa camera khỏi cổng. Trả 404 nếu camera không thuộc gate này."""
    _gate(gate_id)
    cam = get_camera(camera_id)
    if cam is None or cam.get('gate_id') != gate_id:
        raise HTTPException(404, 'Không tìm thấy camera trong cổng này.')
    delete_camera(camera_id)
    return {'status': 'ok', 'deleted_camera_id': camera_id}
