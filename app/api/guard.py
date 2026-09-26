"""
Guard API routes.
- GET /guard/video_feed → MJPEG stream
- WS /guard/ws → WebSocket cho cảnh báo vi phạm
"""
import asyncio
import json
import jwt as _jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.cv.pipeline import get_pipeline
from app.auth import decode_access_token

router = APIRouter(prefix="/guard", tags=["guard"])


@router.get("/video_feed")
async def video_feed(token: str = Query(default=None)):
    """
    MJPEG streaming — requires token with role security or admin.
    """
    # Auth
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = decode_access_token(token)
    except (_jwt.ExpiredSignatureError, _jwt.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("role") not in ("security", "admin"):
        raise HTTPException(status_code=401, detail="Insufficient permissions")

    import cv2

    def generate():
        pipeline = get_pipeline()

        while True:
            frame = pipeline.get_frame()

            if frame is None:
                continue

            # Encode JPEG
            ret, jpeg = cv2.imencode('.jpg', frame)
            if not ret:
                continue

            # MJPEG multipart format
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' +
                   jpeg.tobytes() +
                   b'\r\n')

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.websocket("/ws")
async def websocket_alerts(websocket: WebSocket):
    """
    WebSocket endpoint cho cảnh báo vi phạm — requires token with role security or admin.
    """
    # Auth before accepting
    raw_token = websocket.query_params.get("token")
    if not raw_token:
        await websocket.close(code=1008, reason="Missing token")
        return
    payload = decode_access_token(raw_token)
    if not payload or payload.get("role") not in ("security", "admin"):
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    await websocket.accept()
    print("[WS] Client connected")

    try:
        while True:
            pipeline = get_pipeline()
            alert = pipeline.get_alert()

            if alert:
                await websocket.send_text(json.dumps(alert))
                print(f"[WS] Sent alert: {alert}")

            # Ngủ 200ms trước khi kiểm tra lại
            await asyncio.sleep(0.2)

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Error: {e}")
