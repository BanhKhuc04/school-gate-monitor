"""
FastAPI main application.
Khởi tạo app, pipeline thread, và routers.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import SNAPSHOTS_DIR
import os

from app.api.guard import router as guard_router
from app.api.admin import router as admin_router, vehicles_router, stats_router
from app.api.auth import router as auth_router
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
    """Tạo FastAPI app với Jinja2 templates."""
    app = FastAPI(
        title="School Gate Monitor",
        description="Hệ thống giám sát cổng trường - MVP",
        version="1.0.0",
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

    # Templates
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    app.state.jinja2_env = Jinja2Templates(directory=templates_dir)
    
    # Mount static files nếu có
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    # Routers
    app.include_router(guard_router)
    app.include_router(admin_router)
    app.include_router(auth_router)
    app.include_router(vehicles_router)
    app.include_router(stats_router)

    # Mount snapshots directory
    app.mount("/media", StaticFiles(directory=SNAPSHOTS_DIR), name="media")
    
    return app


# App instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
