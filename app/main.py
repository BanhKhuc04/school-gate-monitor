"""
FastAPI main application.
Khởi tạo app, pipeline thread, và routers.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import SNAPSHOTS_DIR

from app.api.guard import router as guard_router
from app.api.admin import vehicles_router, stats_router, violations_router
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.dev import router as dev_router
from app.api.system import router as system_router
from app.api.roi import router as roi_router
from app.api.camera import router as camera_router
from app.db import init_db, seed_default_users_if_empty

_pipeline_started = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan - start/stop all pipeline threads (lazy import avoids blocking on missing CV libs)."""
    global _pipeline_started
    # Startup
    print("[App] Initializing database...")
    init_db()
    created = seed_default_users_if_empty()
    if created:
        print(f"[App] DB mới — đã tạo tài khoản mặc định: {', '.join(created)} "
              f"(mật khẩu xem README, ĐỔI NGAY trước khi dùng thật)")
    # Đợt 2, Bước 4: MaintenanceWorker không phụ thuộc CV libs — start ĐỘC LẬP
    # với pipeline để DB-test env (không có ultralytics) vẫn chạy được worker,
    # và để nếu CV import lỗi thì cleanup tự động vẫn chạy (chỉ mất camera).
    try:
        from app.background import start_maintenance_worker, stop_maintenance_worker
        print("[App] Starting maintenance worker...")
        start_maintenance_worker()
    except ImportError as e:
        print(f"[App] Maintenance worker unavailable: {e}")
        stop_maintenance_worker = lambda: None  # noqa: E731 — shutdown no-op
    try:
        from app.cv.pipeline import start_all_pipelines, stop_all_pipelines
        print("[App] Starting all pipeline threads...")
        start_all_pipelines()
        _pipeline_started = True
    except ImportError as e:
        print(f"[App] CV libs not available, skipping pipeline start: {e}")
        yield
        stop_maintenance_worker()
        return
    else:
        yield
        # Shutdown (only if pipelines were started)
        print("[App] Stopping all pipeline threads...")
        stop_all_pipelines()
        print("[App] Stopping maintenance worker...")
        stop_maintenance_worker()
        return
    yield  # fallback for when _pipeline_started is False (shouldn't reach here)


def create_app() -> FastAPI:
    """Tạo FastAPI app."""
    app = FastAPI(
        title="School Gate Monitor",
        description="Hệ thống giám sát cổng trường - SPA",
        version="2.0.0",
        lifespan=lifespan
    )

    # CORS for SPA frontend — allow both possible dev ports
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:5174"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files if present
    static_dir = __import__("os").path.join(__import__("os").path.dirname(__file__), "static")
    if __import__("os").path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Mount snapshots dir for violation images
    if __import__("os").path.exists(SNAPSHOTS_DIR):
        app.mount("/media", StaticFiles(directory=SNAPSHOTS_DIR), name="media")

    # Routers
    app.include_router(guard_router)
    app.include_router(auth_router)
    app.include_router(vehicles_router)
    app.include_router(violations_router)
    app.include_router(stats_router)
    app.include_router(users_router)
    app.include_router(system_router)
    app.include_router(roi_router)
    app.include_router(camera_router)

    return app


# App instance
app = create_app()

# ─── Dev/test endpoints ───────────────────────────────────────────────────────
app.include_router(dev_router)

# ─── SPA fallback — must be last, after all routers/mounts ──────────────────
frontend_dist = __import__("os").path.join(
    __import__("os").path.dirname(__import__("os").path.dirname(__file__)),
    "frontend", "dist"
)
if __import__("os").path.exists(frontend_dist):
    from fastapi.responses import FileResponse

    # (Đã bỏ handler trả 410 cho các route Jinja cũ /admin, /admin/violations...:
    # đó giờ chính là route của React SPA — mở thẳng/F5 trang Nhật ký vi phạm
    # bị trả JSON "Gone" thay vì giao diện.)

    assets_dir = __import__("os").path.join(frontend_dist, "assets")
    if __import__("os").path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    _dist_root = __import__("os").path.realpath(frontend_dist)

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # File tĩnh ở gốc dist (favicon.svg, icons.svg...) phải trả đúng file —
        # trước đây mọi đường dẫn đều trả index.html nên logo bị vỡ ảnh.
        # realpath + so tiền tố: chặn ../ đọc file ngoài thư mục dist.
        os_ = __import__("os")
        candidate = os_.path.realpath(os_.path.join(_dist_root, full_path))
        if full_path and candidate.startswith(_dist_root + os_.sep) and os_.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os_.path.join(frontend_dist, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
