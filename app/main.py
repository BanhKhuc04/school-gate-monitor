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
from app.cv.pipeline import start_pipeline, stop_pipeline
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan - start/stop pipeline thread."""
    # Startup
    print("[App] Initializing database...")
    init_db()
    print("[App] Starting pipeline thread...")
    start_pipeline()

    yield

    # Shutdown
    print("[App] Stopping pipeline thread...")
    stop_pipeline()


def create_app() -> FastAPI:
    """Tạo FastAPI app."""
    app = FastAPI(
        title="School Gate Monitor",
        description="Hệ thống giám sát cổng trường - SPA",
        version="2.0.0",
        lifespan=lifespan
    )

    # CORS for SPA frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
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
    from fastapi.responses import FileResponse, JSONResponse

    # Old Jinja HTML routes — return 410 Gone so they don't accidentally
    # get caught by the SPA fallback (which must come AFTER this block)
    @app.get("/admin")
    @app.get("/admin/vehicles/{_}")
    @app.get("/admin/violations")
    async def old_jinja_routes(_: str = ""):
        return JSONResponse({"detail": "Gone — frontend moved to React SPA"}, status_code=410)

    assets_dir = __import__("os").path.join(frontend_dist, "assets")
    if __import__("os").path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        return FileResponse(__import__("os").path.join(frontend_dist, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
