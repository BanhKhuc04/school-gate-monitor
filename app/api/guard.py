"""
Guard API routes.
- GET /guard/video_feed → MJPEG stream
- WS /guard/ws → WebSocket cho cảnh báo vi phạm (broadcast)
"""
import asyncio
import json
import time
import jwt as _jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.auth import decode_access_token

router = APIRouter(prefix="/guard", tags=["guard"])

# ─── Broadcast manager ────────────────────────────────────────────────────────
# Key: WebSocket object id, Value: WebSocket
_connected_clients: dict[int, WebSocket] = {}
# asyncio.Lock, không phải threading.Lock: lock này chỉ bao giờ được acquire
# từ coroutine chạy trên event loop (không có thread nào khác đụng vào
# _connected_clients). threading.Lock().acquire() là lời gọi blocking THẬT
# (không nhường event loop) — nếu 2 client cùng lúc broadcast (mỗi client 1
# coroutine `websocket_alerts`) và coroutine giữ lock đang `await
# ws.send_text(...)`, coroutine thứ 2 gọi `with _clients_lock` sẽ treo cứng
# toàn bộ event loop (không chỉ riêng request đó) cho tới khi coroutine đầu
# được chính event loop đó lên lịch lại để nhả lock — nhưng event loop đang
# bị chặn nên không bao giờ xảy ra → deadlock toàn bộ server, không riêng gì
# WebSocket. asyncio.Lock nhường event loop đúng cách khi phải chờ.
_clients_lock = asyncio.Lock()


@router.get("/video_feed")
async def video_feed(
    token: str = Query(default=None),
    gate: str = Query(default="main"),
):
    """
    MJPEG streaming — requires token with role security, admin, or management.
    Optional query param `gate` selects which camera pipeline (default: "main").
    """
    # Auth
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = decode_access_token(token)
    except (_jwt.ExpiredSignatureError, _jwt.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("role") not in ("security", "admin", "management"):
        raise HTTPException(status_code=401, detail="Insufficient permissions")

    import cv2
    from app.cv.pipeline import get_pipeline

    def generate():
        pipeline = get_pipeline(gate_id=gate)

        # Giới hạn tốc độ xuất MJPEG — TRƯỚC ĐÂY vòng lặp này không có sleep,
        # chạy hết tốc lực: liên tục copy frame (có lock, ~2.7MB/lần ở 1280x720)
        # + cv2.imencode hàng trăm-hàng nghìn lần/giây, chiếm trọn 1 CPU core và
        # tranh giành CPU trực tiếp với các luồng YOLO detect trong pipeline nền
        # — đây là nguyên nhân chính khiến hệ thống lag dù pipeline detect vẫn
        # chạy bình thường. 20 FPS là đủ mượt cho giám sát qua trình duyệt.
        target_interval = 1.0 / 20

        while True:
            loop_start = time.monotonic()
            frame = pipeline.get_frame()

            if frame is not None:
                ret, jpeg = cv2.imencode('.jpg', frame)
                if ret:
                    # MJPEG multipart format
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' +
                           jpeg.tobytes() +
                           b'\r\n')

            elapsed = time.monotonic() - loop_start
            time.sleep(max(target_interval - elapsed, 0.01))

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.websocket("/ws")
async def websocket_alerts(websocket: WebSocket, gate: str = "main"):
    """
    WebSocket endpoint cho cảnh báo vi phạm — requires token with role security, admin, or management.
    Optional query param `gate` selects which camera pipeline (default: "main").
    Uses broadcast pattern: every connected client receives every alert.
    """
    # Auth before accepting
    raw_token = websocket.query_params.get("token")
    if not raw_token:
        await websocket.close(code=1008, reason="Missing token")
        return
    try:
        payload = decode_access_token(raw_token)
    except (_jwt.ExpiredSignatureError, _jwt.InvalidTokenError):
        # decode_access_token raises on bad/expired token thay vì trả None — nếu
        # không catch ở đây, exception văng thẳng ra khỏi handler và đóng kết nối
        # một cách không rõ ràng (client chỉ thấy WS đóng đột ngột, không rõ vì sao,
        # rồi lặp lại reconnect timer 3s của AlertBanner mà không bao giờ vào được).
        await websocket.close(code=1008, reason="Invalid or expired token")
        return
    if payload.get("role") not in ("security", "admin", "management"):
        await websocket.close(code=1008, reason="Insufficient permissions")
        return

    await websocket.accept()
    client_id = id(websocket)
    async with _clients_lock:
        _connected_clients[client_id] = websocket
    print(f"[WS] Client connected: id={client_id}, gate={gate}, total={len(_connected_clients)}")

    try:
        while True:
            from app.cv.pipeline import get_pipeline
            pipeline = get_pipeline(gate_id=gate)
            alert = pipeline.get_alert()

            if alert:
                # Broadcast to ALL connected clients
                disconnected = []
                async with _clients_lock:
                    for cid, ws in _connected_clients.items():
                        try:
                            await ws.send_text(json.dumps(alert))
                            print(f"[WS] Sent alert to client {cid}")
                        except Exception:
                            disconnected.append(cid)
                    # Remove dead clients
                    for cid in disconnected:
                        del _connected_clients[cid]
                        print(f"[WS] Removed dead client {cid}")

            # Ngủ 200ms trước khi kiểm tra lại
            await asyncio.sleep(0.2)

    except WebSocketDisconnect:
        print(f"[WS] Client {client_id} disconnected")
    except Exception as e:
        print(f"[WS] Error with client {client_id}: {e}")
    finally:
        async with _clients_lock:
            _connected_clients.pop(client_id, None)
        print(f"[WS] Cleaned up client {client_id}, remaining={len(_connected_clients)}")
