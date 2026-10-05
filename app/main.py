"""
FastAPI main application.
Khởi tạo app, pipeline thread, và routers.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import SNAPSHOTS_DIR

from app.api.guard import router as guard_router
from app.api.admin import vehicles_router, stats_router, violations_router, roster_router
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.dev import router as dev_router
from app.api.system import router as system_router
from app.api.roi import router as roi_router
from app.api.camera import router as camera_router
from app.api.demo import router as demo_router  # nút chạy video test
from app.api.register import router as register_router  # UT8: public register
from app.api.media import router as media_router  # D6.2: scoped media endpoint
from app.api.recognition_reviews import router as recognition_reviews_router  # FR6: review/feedback
from app.api.training_data import router as training_data_router  # Task 3: datasets/samples/splits
from app.api.training_jobs import router as training_jobs_router  # Task 3: training jobs
from app.api.training_candidates import router as training_candidates_router  # Task 3: candidate promote/rollback
from app.api.training_portable import router as training_portable_router  # Task 3: export/import ZIP
from app.db import init_db

_pipeline_started = False


def _raise_process_priority():
    """Run the gate monitor above desktop apps (PROCESS_PRIORITY=normal to
    opt out). Two cameras at 25 fps on the RTX 3050 laptop: the front AI rate
    dipped to 11.6 fps under Normal while a browser played both streams, and
    held 23.7-24.7 fps under High."""
    level = os.environ.get('PROCESS_PRIORITY', 'high').strip().lower()
    if level == 'normal':
        return
    try:
        import psutil
        windows = {'high': 'HIGH_PRIORITY_CLASS', 'above_normal': 'ABOVE_NORMAL_PRIORITY_CLASS'}
        value = getattr(psutil, windows.get(level, ''), None) if os.name == 'nt' else -5
        if value is not None:
            psutil.Process().nice(value)
            print(f"[App] Process priority: {level}")
    except Exception as e:  # unsupported level, no permission (POSIX), psutil missing
        print(f"[App] Process priority unchanged: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan - start/stop all pipeline threads (lazy import avoids blocking on missing CV libs).

    F4.3 R2 fix: try/finally ensures cleanup ALWAYS runs, even on partial startup
    or exception during initialization. Each component has its own try/except so
    that ImportError or RuntimeError during one component doesn't prevent the
    other components from starting OR cleaning up.

    Structure:
    - try/finally wraps EVERYTHING so finally ALWAYS runs
    - yield is the boundary: before yield = setup, after = teardown
    - Exception in setup propagates through __aenter__ but finally STILL runs
    - FastAPI handles this by calling __aexit__ after __aenter__ raises
    """
    global _pipeline_started

    # Stop functions - set to no-op by default; replaced on successful import
    _stop_maintenance = lambda: None
    _stop_collector = lambda **kw: None
    _stop_training = lambda **kw: None
    _stop_pipelines = lambda: None

    try:
        # Startup
        print("[App] Initializing database...")
        init_db()
        from app.training import dataset_repo
        dataset_repo.init_db()

        # MaintenanceWorker - independent of CV libs, starts before pipelines
        try:
            from app.background import start_maintenance_worker, stop_maintenance_worker
            start_maintenance_worker()
            _stop_maintenance = stop_maintenance_worker
            print("[App] Maintenance worker started.")
        except ImportError as e:
            print(f"[App] Maintenance worker unavailable: {e}")

        # Task 3 collector - independent of CV
        try:
            from app.training.sample_collector import start_collector_task, stop_collector_task
            start_collector_task()
            _stop_collector = stop_collector_task
            print("[App] Task3 sample collector started.")
        except ImportError as e:
            print(f"[App] Task3 collector unavailable: {e}")

        # Task 3 training worker - independent of CV
        try:
            from app.training.worker import start_training_worker, stop_training_worker
            start_training_worker(poll_sec=5.0)
            _stop_training = stop_training_worker
            print("[App] Task3 training worker started.")
        except ImportError as e:
            print(f"[App] Task3 training worker unavailable: {e}")

        # Pipelines - requires CV libs
        try:
            from app.cv.pipeline import start_all_pipelines, stop_all_pipelines
            if os.environ.get('CV_PIPELINES_ENABLED', '1') == '1':
                _raise_process_priority()
                start_all_pipelines()
                _stop_pipelines = stop_all_pipelines
                _pipeline_started = True
                print("[App] Pipeline threads started.")
        except ImportError as e:
            print(f"[App] CV libs not available, skipping pipelines: {e}")

        # Yield control to request handlers
        yield

    finally:
        # R2 FIX: ALWAYS cleanup, even on partial startup or exception.
        # Each component has its own stop function. Components that failed to
        # import get a no-op lambda, so calling them is always safe.
        print("[App] Shutting down...")

        # Pipelines - stop first (started last)
        try:
            print("[App] Stopping pipelines...")
            _stop_pipelines()
        except Exception as e:
            print(f"[App] Pipeline stop error: {e}")

        # Task 3 training worker
        try:
            _stop_training(timeout=5.0)
            print("[App] Task3 training worker stopped.")
        except Exception as e:
            print(f"[App] Training worker stop error: {e}")

        # Task 3 collector
        try:
            _stop_collector(timeout=5.0)
            print("[App] Task3 collector stopped.")
        except Exception as e:
            print(f"[App] Collector stop error: {e}")

        # Maintenance worker - stop last (started first)
        try:
            print("[App] Stopping maintenance worker...")
            _stop_maintenance()
        except Exception as e:
            print(f"[App] Maintenance worker stop error: {e}")


def create_app() -> FastAPI:
    """Tạo FastAPI app."""
    app = FastAPI(
        title="School Gate Monitor",
        description="Hệ thống giám sát cổng trường - SPA",
        version="2.0.0",
        lifespan=lifespan
    )

    # CORS — dev: localhost:5173/5174; production: read from env
    _cors_origins = os.environ.get("CORS_ORIGINS", "")
    if _cors_origins:
        _allowed_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
    else:
        _allowed_origins = [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files if present
    static_dir = __import__("os").path.join(__import__("os").path.dirname(__file__), "static")
    if __import__("os").path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # D6.2: in production, replace static /media mount with scoped API endpoint
    # (app/api/media.py) so that auth + class-scope is enforced server-side.
    # Keep static mount only in dev so existing <img src="/media/..."> refs still work.
    _is_prod = os.environ.get("ENVIRONMENT", "development") == "production"
    if not _is_prod:
        # Dev: mount /media/snapshots, /media/clips, /media/student_photos
        if __import__("os").path.exists(SNAPSHOTS_DIR):
            app.mount("/media", StaticFiles(directory=SNAPSHOTS_DIR), name="media")
        # UT8: mount thư mục ảnh hồ sơ học sinh (dev only)
        _sp_dir = __import__("os").path.join(os.path.dirname(SNAPSHOTS_DIR), "student_photos")
        if __import__("os").path.exists(_sp_dir):
            app.mount("/media/student_photos", StaticFiles(directory=_sp_dir), name="student-photos")

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
    app.include_router(demo_router)
    app.include_router(roster_router)
    app.include_router(register_router)
    app.include_router(media_router)
    app.include_router(recognition_reviews_router)
    # Task 3: training routers (admin-only; gated inside each module)
    app.include_router(training_data_router)
    app.include_router(training_jobs_router)
    app.include_router(training_candidates_router)
    app.include_router(training_portable_router)

    return app


# App instance
app = create_app()

# ─── Dev/test endpoints ───────────────────────────────────────────────────────
app.include_router(dev_router)

# ─── SPA fallback — must be last, after all routers/mounts ──────────────────
# R2 — production deep link: phải trả index.html cho route SPA thực có
# (vd. /admin/violations, /teacher/violations), và KHÔNG trả HTML cho /api/*
# (phải trả JSON 404 đúng HTTP status). Tách thành helper để create_app()
# cũng có thể đính vào — đây là lỗi codex review F03 nhắc: test_app dựng
# app riêng nên không thấy 410 ở production app.
frontend_dist = __import__("os").path.join(
    __import__("os").path.dirname(__import__("os").path.dirname(__file__)),
    "frontend", "dist"
)


def _attach_spa_fallback(app: FastAPI, dist_dir: str) -> None:
    """Đính SPA fallback cho app. Phải gọi SAU CÙNG sau include_router/mount.

    Hành vi:
      - "/" và path SPA không có extension, không bắt đầu "api/" hay "media/"
        → FileResponse index.html (200) — đây là deep link admin/teacher
          (vd. /admin/violations) mà codex review F03 yêu cầu.
      - path "api/..." hoặc "media/..." hoặc có "." (file assets) → 404 JSON.
        Trước đây SPA fallback trả index.html cho /api/khong-ton-tai (lỗi
        codex review F03); nay bảo và cách ly.
    """
    if not __import__("os").path.exists(dist_dir):
        return
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    assets_dir = __import__("os").path.join(dist_dir, "assets")
    if __import__("os").path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    spa_index = __import__("os").path.join(dist_dir, "index.html")

    @app.get("/", include_in_schema=False)
    async def spa_root():
        return FileResponse(spa_index, media_type="text/html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Bảo vệ namespace API khỏi SPA fallback (F03)
        if full_path.startswith("api/") or full_path.startswith("media/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        # Có extension (file tĩnh) → KHÔNG fallback index. File thật ở gốc
        # dist (favicon.svg, icons.svg, logo/banner từ public/) phải phục vụ
        # được, nếu không logo trang đăng nhập/landing bị vỡ ảnh.
        if "." in full_path.split("/")[-1]:
            import os as _os
            root = _os.path.realpath(dist_dir)
            candidate = _os.path.realpath(_os.path.join(root, full_path))
            if _os.path.commonpath([root, candidate]) == root and _os.path.isfile(candidate):
                return FileResponse(candidate)
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(spa_index, media_type="text/html")


# Đính SPA fallback cho app global — bỏ các route 410 cũ (F03).
_attach_spa_fallback(app, frontend_dist)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
