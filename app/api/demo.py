"""Nút "Chạy video test": hai cổng cùng phát hai video quay sẵn (app/cv/demo_mode.py)."""
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_role
from app.cv import demo_mode
from app.cv.camera_switch import CameraBusy

router = APIRouter(prefix='/api/demo', tags=['demo'])


def _existing_pipeline(gate_id):
    try:
        from app.cv.pipeline import get_existing_pipeline
    except ImportError:
        return None
    return get_existing_pipeline(gate_id)


@router.get('')
def demo_status(current_user: dict = Depends(require_role('admin', 'security', 'management'))):
    return demo_mode.status()


@router.post('/start')
def demo_start(current_user: dict = Depends(require_role('admin'))):
    try:
        return demo_mode.start(_existing_pipeline)
    except FileNotFoundError as error:
        raise HTTPException(404, f'Không tìm thấy video test: {error}. Chép video vào data/demo_videos/.') from None
    except CameraBusy:
        raise HTTPException(409, 'Camera đang chuyển nguồn, thử lại sau vài giây.') from None
    except RuntimeError:
        raise HTTPException(503, 'Hệ thống camera chưa chạy. Khởi động lại backend rồi thử lại.') from None


@router.post('/stop')
def demo_stop(current_user: dict = Depends(require_role('admin'))):
    try:
        return demo_mode.stop(_existing_pipeline)
    except CameraBusy:
        raise HTTPException(409, 'Camera đang chuyển nguồn, thử lại sau vài giây.') from None
