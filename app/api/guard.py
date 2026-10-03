"""
Guard API routes.
- GET /guard/video_feed → MJPEG stream
- WS /guard/ws → WebSocket cho cảnh báo vi phạm (broadcast)
"""
import asyncio
import json
import os
import time
import jwt as _jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Request, Depends
from fastapi.responses import StreamingResponse, Response

from app.auth import decode_access_token, COOKIE_NAME, require_role

router = APIRouter(prefix="/guard", tags=["guard"])
from app.api.audio_lease import router as audio_router, owns_audio
router.include_router(audio_router, prefix='')


@router.get('/debug_overlay')
def debug_overlay(gate: str = 'main', user: dict = Depends(require_role('admin', 'management'))):
    pipeline = _recognition_pipeline(gate)
    return {'enabled': getattr(pipeline, '_debug_overlay_enabled', True), 'scope': 'camera'}


@router.post('/debug_overlay')
def set_debug_overlay(enabled: bool, gate: str = 'main',
                      user: dict = Depends(require_role('admin', 'management'))):
    pipeline = _recognition_pipeline(gate)
    if pipeline is None:
        raise HTTPException(409, 'camera chưa chạy')
    pipeline._debug_overlay_enabled = enabled
    return {'enabled': enabled, 'scope': 'camera'}


@router.get('/audio/config')
def audio_config(current_user: dict = Depends(require_role('admin', 'security', 'management'))):
    from app.config import TTS_SPEECH_RATE, TTS_VOLUME, DEBUG_ALERT
    return {'engine':'Web Speech API', 'rate':TTS_SPEECH_RATE, 'volume':TTS_VOLUME, 'debug':DEBUG_ALERT}


@router.get('/plate_best/{track_id}')
def plate_best(track_id: int, gate: str = 'main', epoch: int = Query(..., ge=0),
               current_user: dict = Depends(require_role('admin', 'security', 'management'))):
    pipeline = _recognition_pipeline(gate)
    if pipeline is None or epoch != pipeline._source_epoch:
        raise HTTPException(404, 'Ảnh thuộc phiên camera đã hết hạn.')
    store = getattr(pipeline, '_best_plates', None)
    best = store.candidate(track_id) if store else None
    if best is None:
        raise HTTPException(404, 'Chưa có ảnh biển tốt nhất.')
    import cv2
    ok, body = cv2.imencode('.png', best.crop)
    if not ok:
        raise HTTPException(503, 'Không xuất được ảnh biển.')
    return Response(body.tobytes(), media_type='image/png',
        headers={'Content-Disposition':f'attachment; filename="bike-{track_id}-frame-{best.frame_id}.png"',
                 'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})


def _recognition_pipeline(gate):
    from app.config import GATES
    if gate not in GATES:
        raise HTTPException(404, 'Không tìm thấy camera.')
    from app.cv.pipeline import get_existing_pipeline
    return get_existing_pipeline(gate)


@router.get('/recognition_cards')
def recognition_cards(gate: str = 'main',
                      current_user: dict = Depends(require_role('admin', 'security', 'management'))):
    pipeline = _recognition_pipeline(gate)
    store = getattr(pipeline, '_recognition_cards', None)
    if store is None:
        return {'status': 'not_started', 'run_id': None, 'source_epoch': 0, 'cards': [], 'models': {}}
    return {'status': 'running' if pipeline._running else 'stopped',
            **store.snapshot(), 'models': pipeline.recognition_models(),
            'gate_line_configured': bool(getattr(getattr(pipeline, '_crossing_detector', None), 'gate_line', None)),
            'plate_region': {'scans': getattr(pipeline, '_plate_region_scans', 0),
                             'last_ms': round(getattr(pipeline, '_plate_region_scan_ms', 0), 2)}}


@router.get('/recognition_image/{image_id}')
def recognition_image(image_id: str, gate: str = 'main',
                      current_user: dict = Depends(require_role('admin', 'security', 'management'))):
    pipeline = _recognition_pipeline(gate)
    store = getattr(pipeline, '_recognition_cards', None)
    body = store.image(image_id) if store is not None else None
    if body is None:
        raise HTTPException(404, 'Ảnh nhận diện đã hết hạn.')
    return Response(body, media_type='image/jpeg',
                    headers={'Cache-Control': 'private, max-age=10', 'X-Content-Type-Options': 'nosniff'})


@router.get('/recognition_log')
def recognition_log(gate: str = 'main', after_seq: int = Query(0, ge=0),
                    limit: int = Query(50, ge=1, le=100),
                    current_user: dict = Depends(require_role('admin', 'security', 'management'))):
    from app.config import GATES
    if gate not in GATES:
        raise HTTPException(404, 'Không tìm thấy camera.')
    try:
        from app.cv.pipeline import get_existing_pipeline
        pipeline = get_existing_pipeline(gate)
    except ImportError:
        pipeline = None
    if pipeline is None:
        return {'status': 'not_started', 'run_id': None, 'source_epoch': 0,
                'cursor': 0, 'reset': True, 'items': [], 'models': {}, 'camera': {}}
    return {'status': 'running' if pipeline._running else 'stopped',
            **pipeline.recognition_snapshot(after_seq, limit)}

# ─── Allowed origins cho WebSocket (HttpOnly cookie an toàn hơn query token) ───
# Khi dev: localhost các cổng frontend thường gặp.
# Khi triển khai LAN: thêm host LAN của backend. Admin cấu hình qua env
# `WS_ALLOWED_ORIGINS` (csv) hoặc bỏ trống = chấp nhận cùng host.
_ALLOWED_WS_ORIGINS = set(filter(
    lambda s: bool(s),
    (os.environ.get("WS_ALLOWED_ORIGINS") or
     "http://localhost:5173,http://localhost:8001,http://127.0.0.1:5173,http://127.0.0.1:8001").split(","),
))
# Nếu không có env, mặc định chấp nhận cùng host (không có Origin header).


def _origin_allowed(request_or_ws) -> bool:
    """Kiểm tra Origin của request/websocket. True nếu:
    - Không có Origin header (same-origin, non-browser client OK).
    - Origin thuộc _ALLOWED_WS_ORIGINS.
    - Trong dev (ENVIRONMENT=development), chấp nhận mọi Origin nếu _ALLOWED_WS_ORIGINS trống."""
    origin = request_or_ws.headers.get("origin") or request_or_ws.headers.get("Origin") or ""
    if not origin:
        return True  # Same-origin (curl, server-to-server, native app)
    # Browsers always send Origin on a WebSocket, even same-origin. The app
    # served by this backend (START_DEMO opens :8000) must reach its own
    # /guard/ws, or every alert and spoken warning is silently refused.
    from urllib.parse import urlsplit
    host = request_or_ws.headers.get("host") or ""
    if host and urlsplit(origin).netloc == host:
        return True
    configured = os.environ.get("WS_ALLOWED_ORIGINS")
    allowed = {v.strip() for v in configured.split(",")} if configured is not None else _ALLOWED_WS_ORIGINS
    if origin in allowed:
        return True
    return False

# ─── Broadcast manager — per-gate distribution ──────────────────────────────────
# One backend event loop: gate_id → client_id → bounded subscriber queue.
# This eliminates the gate filter inside the send loop and makes it impossible
# to accidentally broadcast to clients subscribed to a different gate.
_gate_clients: dict[str, dict[int, asyncio.Queue]] = {}
_gate_pumps: dict[str, asyncio.Task] = {}


async def _pump_gate_alerts(gate):
    """One queue consumer per gate; each viewer gets its own bounded copy."""
    from app.cv.pipeline import get_pipeline
    try:
        if os.environ.get('CV_PIPELINES_ENABLED', '1') == '0':
            raise RuntimeError('CV pipelines disabled')
        pipeline = get_pipeline(gate_id=gate)
        while _gate_clients.get(gate):
            alert = pipeline.get_alert()
            if alert:
                payload = {**alert, 'gate_id': gate}
                for inbox in tuple(_gate_clients[gate].values()):
                    if inbox.full():
                        while not inbox.empty():
                            inbox.get_nowait()
                        inbox.put_nowait(None)  # slow viewer must reconnect
                    else:
                        inbox.put_nowait(payload)
            await asyncio.sleep(0.05)
    except Exception as exc:
        print(f'[WS] Event source unavailable: {type(exc).__name__}')
        for inbox in tuple(_gate_clients.get(gate, {}).values()):
            while not inbox.empty():
                inbox.get_nowait()
            inbox.put_nowait(None)
    finally:
        if _gate_pumps.get(gate) is asyncio.current_task():
            _gate_pumps.pop(gate, None)


def _subscribe(gate, client_id):
    inbox = asyncio.Queue(maxsize=64)
    _gate_clients.setdefault(gate, {})[client_id] = inbox
    if gate not in _gate_pumps or _gate_pumps[gate].done():
        _gate_pumps[gate] = asyncio.create_task(_pump_gate_alerts(gate))
    return inbox


@router.get("/video_feed")
async def video_feed(
    request: Request,
    token: str = Query(default=None),
    gate: str = Query(default="main"),
):
    """
    MJPEG streaming — yêu cầu role security/admin/management.
    Auth: Bearer header / cookie `gate_session` / query token (fallback).
    Optional `gate` chọn pipeline (mặc định 'main').
    """
    # Origin check (chống cookie replay từ origin khác)
    if not _origin_allowed(request):
        raise HTTPException(status_code=403, detail="Origin not allowed")

    # Token: header cookie (ưu tiên) > Authorization header > query param
    raw_token = request.cookies.get(COOKIE_NAME)
    if not raw_token:
        auth = request.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            raw_token = auth[7:].strip()
    if not raw_token:
        raw_token = token
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = decode_access_token(raw_token)
    except (_jwt.ExpiredSignatureError, _jwt.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("role") not in ("security", "admin", "management"):
        raise HTTPException(status_code=401, detail="Insufficient permissions")

    import cv2
    from app.cv.pipeline import get_pipeline

    if os.environ.get('CV_PIPELINES_ENABLED', '1') == '0':
        raise HTTPException(503, 'Camera runtime đang tắt')

    return StreamingResponse(
        mjpeg_frames(get_pipeline(gate_id=gate)),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


def mjpeg_frames(pipeline, frame_limit=None):
    """Share encoded JPEGs. A finite limit supports isolated stream tests."""
    count = 0
    while frame_limit is None or count < frame_limit:
        started = time.monotonic()
        jpeg = pipeline.get_jpeg()
        if jpeg is not None:
            yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n'
            count += 1
        if frame_limit is not None and count >= frame_limit:
            return
        time.sleep(max(0.05 - (time.monotonic() - started), 0.01))


@router.websocket("/ws")
async def websocket_alerts(websocket: WebSocket, gate: str = "main", client_id: str = ""):
    """
    WebSocket endpoint cho cảnh báo vi phạm — yêu cầu role security/admin/management.
    Optional query param `gate` chọn pipeline (mặc định 'main').

    Auth (theo thứ tự ưu tiên):
      1. Bearer token (header Authorization) — phù hợp cho script/dev.
      2. Cookie `gate_session` (HttpOnly) — khuyến nghị cho browser.
      3. Query `token` — fallback cho client chưa hỗ trợ cookie. Sẽ bị bỏ
         trong tương lai (kế hoạch Đợt 5 — bỏ token khỏi URL).

    Đợt 5 (System Stability): Origin phải thuộc `_ALLOWED_WS_ORIGINS` nếu có
    (bảo vệ chống CSRF/cookie replay từ origin khác). Same-origin (không có
    Origin header) vẫn OK.
    """
    # Origin check (phải làm trước khi accept() để từ chối ngay)
    if not _origin_allowed(websocket):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    raw_token = None
    auth_header = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        raw_token = auth_header[7:].strip()
    if not raw_token:
        # Ưu tiên cookie (HttpOnly) — bảo mật hơn query token
        cookie_token = websocket.cookies.get(COOKIE_NAME)
        if cookie_token:
            raw_token = cookie_token
        else:
            raw_token = websocket.query_params.get("token")
    if not raw_token:
        await websocket.close(code=1008, reason="Missing token")
        return
    try:
        payload = decode_access_token(raw_token)
    except (_jwt.ExpiredSignatureError, _jwt.InvalidTokenError):
        await websocket.close(code=1008, reason="Invalid or expired token")
        return
    if not payload or payload.get("role") not in ("security", "admin", "management"):
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    await websocket.accept()
    speaker_id = client_id
    client_id = id(websocket)
    inbox = _subscribe(gate, client_id)
    async def send_updates():
        while True:
            alert = await inbox.get()
            if alert is None:
                await websocket.close(code=1008, reason='Event stream unavailable or slow; reconnect to resync')
                return
            message = {**alert, 'audio_authorized': owns_audio(gate, payload.get('sub'), speaker_id)}
            await asyncio.wait_for(websocket.send_text(json.dumps(message)), timeout=1.0)

    async def receive_disconnect():
        while True:
            if (await websocket.receive())['type'] == 'websocket.disconnect':
                return

    sender = asyncio.create_task(send_updates())
    receiver = asyncio.create_task(receive_disconnect())
    try:
        completed, _ = await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
        for task in completed:
            task.result()
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        sender.cancel()
        receiver.cancel()
        await asyncio.gather(sender, receiver, return_exceptions=True)
        subscribers = _gate_clients.get(gate, {})
        subscribers.pop(client_id, None)
        if not subscribers:
            _gate_clients.pop(gate, None)
            pump = _gate_pumps.pop(gate, None)
            if pump:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
