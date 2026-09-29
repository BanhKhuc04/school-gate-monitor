"""
pytest fixtures for app-level integration tests.
"""
from __future__ import annotations

import sys, os, time, glob
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ─── Per-module app factory ─────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def test_app(request, tmp_path_factory):
    """
    Create a FastAPI test app WITHOUT starting the CV pipeline.
    Each module gets its own temp DB, initialized with tables + seed users.
    """
    from app import config as cfg
    import app.db as db_module
    import sqlite3

    # Save originals — BOTH config and db_module have separate DB_PATH bindings
    orig_db_path = cfg.DB_PATH
    orig_db_module_path = db_module.DB_PATH
    orig_get_conn = db_module.get_connection

    # Module-unique temp DB
    tmp_dir = tmp_path_factory.mktemp(f"test_db_{request.module.__name__}")
    test_db = tmp_dir / "test.db"
    test_db_str = str(test_db)
    # Patch BOTH config.DB_PATH AND db_module.DB_PATH (they are separate bindings)
    cfg.DB_PATH = test_db_str
    db_module.DB_PATH = test_db_str

    def _test_get_connection():
        conn = sqlite3.connect(test_db_str, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    db_module.get_connection = _test_get_connection

    # Init tables
    from app.db import init_db, _write_lock
    init_db()

    # Seed users
    test_hash = "$2b$12$2IuvqWKAkJTVchQraU3G9eY.My/ANMrJ2shrbMGuvCHQTnOSFwReW"
    with _write_lock:
        conn = db_module.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()[0] == 0:
                now = int(time.time())
                cur.executemany(
                    "INSERT INTO users (username, password_hash, role, homeroom_class, created_at) VALUES (?, ?, ?, ?, ?)",
                    [("admin", test_hash, "admin", None, now),
                     ("security", test_hash, "security", None, now),
                     ("management", test_hash, "management", None, now),
                     ("teacher", test_hash, "teacher", "10A1", now)],
                )
                conn.commit()
        finally:
            conn.close()

    # Build app
    app = FastAPI(title="School Gate Monitor — Test")
    from app.api.guard import router as guard_router
    from app.api.admin import vehicles_router, stats_router, violations_router
    from app.api.auth import router as auth_router
    from app.api.users import router as users_router
    from app.api.dev import router as dev_router
    from app.api.system import router as system_router
    from app.api.roi import router as roi_router
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from app.config import SNAPSHOTS_DIR
    if os.path.exists(SNAPSHOTS_DIR):
        from fastapi.staticfiles import StaticFiles
        app.mount("/media", StaticFiles(directory=SNAPSHOTS_DIR), name="media")
    app.include_router(guard_router)
    app.include_router(auth_router)
    app.include_router(vehicles_router)
    app.include_router(violations_router)
    app.include_router(stats_router)
    app.include_router(users_router)
    app.include_router(dev_router)
    app.include_router(system_router)
    app.include_router(roi_router)

    yield app

    # Restore — patch BOTH bindings
    cfg.DB_PATH = orig_db_path
    db_module.DB_PATH = orig_db_module_path
    db_module.get_connection = orig_get_conn
    for pat in [test_db_str + "-wal", test_db_str + "-shm"]:
        for p in glob.glob(pat):
            try:
                os.unlink(p)
            except OSError:
                pass


# ─── Hook to close all DB connections between test modules ─────────────────────
# This prevents test_smoke.py from leaving a lock on the test_vehicles.py DB
@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Before each test, ensure no lingering connections exist."""
    # Force garbage collection to close any abandoned connections
    import gc
    gc.collect()


# ─── TestClient fixture (function-scoped) ───────────────────────────────────────
@pytest.fixture(scope="function")
def client(test_app) -> TestClient:
    """Function-scoped so each test gets a fresh HTTP connection."""
    with TestClient(test_app) as c:
        yield c


# ─── Auth helpers ─────────────────────────────────────────────────────────────
ROLE_PASSWORD = "test123"


def get_token(client: TestClient, username: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": ROLE_PASSWORD})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.json()}"
    return resp.json()["access_token"]


def auth_headers(client: TestClient, role: str = "admin") -> dict:
    return {"Authorization": f"Bearer {get_token(client, role)}"}
