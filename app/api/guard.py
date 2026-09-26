"""
Guard API routes.
- GET /guard → guard.html
- GET /guard/video_feed → MJPEG stream
- WS /guard/ws → WebSocket cho cảnh báo vi phạm
"""
import asyncio
import json
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, HTMLResponse
from app.cv.pipeline import get_pipeline

router = APIRouter(prefix="/guard", tags=["guard"])


@router.get("/", response_class=HTMLResponse)
async def guard_page(request: Request):
    """Trả về trang guard.html."""
    return request.app.state.jinja2_env.get_template("guard.html").render()


@router.get("/video_feed")
async def video_feed():
    """
    MJPEG streaming.
    Mỗi lần gửi 1 frame JPEG từ pipeline.
    """
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
    WebSocket endpoint cho cảnh báo vi phạm.
    Mỗi ~200ms kiểm tra queue, có item thì gửi JSON.
    """
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
