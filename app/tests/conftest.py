"""
pytest fixtures for app-level integration tests.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# ─── Patch config DB_PATH BEFORE any app imports ──────────────────────────────
_original_db_path = None


@pytest.fixture(scope="session", autouse=True)
def patch_db_path(tmp_path_factory):
    """Redirect DB to a temporary directory for all tests."""
    global _original_db_path
    from app import config
    _original_db_path = config.DB_PATH

    tmp_dir = tmp_path_factory.mktemp("test_db")
    test_db = tmp_dir / "test.db"
    config.DB_PATH = str(test_db)

    yield test_db  # return the path so tests can reference it if needed

    # Restore original path after session
    config.DB_PATH = _original_db_path


# ─── Test app factory (no pipeline) ─────────────────────────────────────────
@pytest.fixture(scope="module")
def test_app(patch_db_path):
    """Create a FastAPI test app WITHOUT starting the CV pipeline."""
    from app.db import init_db, create_user, _write_lock

    # Fully initialise the test database
    init_db()

    # Seed 3 role users (password: "test123")
    # bcrypt hash of "test123" — pre-computed for speed
    test_password_hash = "$2b$12$R2hoQMs7Xn4h1QhSIZg/Hu0ag7RZydcXRSR/EagSpIcEbKeM9o5aa"

    # Only seed if not already seeded (init_db doesn't seed in test env)
    with _write_lock:
        conn = __import__("app.db", fromlist=["get_connection"]).get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
            if count == 0:
                conn.close()
                conn = __import__("app.db", fromlist=["get_connection"]).get_connection()
                cur = conn.cursor()
                import time
                now = int(time.time())
                cur.executemany(
                    "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                    [
                        ("admin", test_password_hash, "admin", now),
                        ("security", test_password_hash, "security", now),
                        ("management", test_password_hash, "management", now),
                    ],
                )
                conn.commit()
        finally:
            conn.close()

    # Build app WITHOUT lifespan (skip pipeline start/stop)
    app = FastAPI(title="School Gate Monitor — Test")

    # Import routers
    from app.api.guard import router as guard_router
    from app.api.admin import vehicles_router, stats_router, violations_router
    from app.api.auth import router as auth_router
    from app.api.users import router as users_router
    from app.api.dev import router as dev_router

    # CORS
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount snapshots dir
    from app.config import SNAPSHOTS_DIR
    if os.path.exists(SNAPSHOTS_DIR):
        from fastapi.staticfiles import StaticFiles
        app.mount("/media", StaticFiles(directory=SNAPSHOTS_DIR), name="media")

    # Routers
    app.include_router(guard_router)
    app.include_router(auth_router)
    app.include_router(vehicles_router)
    app.include_router(violations_router)
    app.include_router(stats_router)
    app.include_router(users_router)
    app.include_router(dev_router)

    return app


# ─── TestClient fixture ───────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client(test_app) -> TestClient:
    """Shared TestClient for all tests in a module."""
    with TestClient(test_app) as c:
        yield c


# ─── Auth helpers ─────────────────────────────────────────────────────────────
ROLE_PASSWORD = "test123"  # matches seeded hash in conftest


def get_token(client: TestClient, username: str) -> str:
    """Login and return a JWT access token."""
    resp = client.post("/api/auth/login", json={"username": username, "password": ROLE_PASSWORD})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.json()}"
    return resp.json()["access_token"]


def auth_headers(client: TestClient, role: str = "admin") -> dict:
    """Return headers dict with Bearer token for the given role."""
    token = get_token(client, role)
    return {"Authorization": f"Bearer {token}"}
