"""Test conftest cho Task 3 — tạo FastAPI app riêng với Task 3 routers.

KHÔNG đụng app/tests/conftest.py (Task 1/2 giữ). Module này tạo app mới để test
Task 3 độc lập.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def task03_app(request, tmp_path_factory):
    """Build FastAPI app with Task 3 routers — không start pipeline runtime."""
    tmp_dir = tmp_path_factory.mktemp(f"task03_app_{request.module.__name__}")
    test_db = tmp_dir / "test.db"
    test_db_str = str(test_db)
    training_db = str(tmp_dir / "training.db")
    os.environ["APP_DB_PATH"] = test_db_str
    os.environ["TRAINING_DB_PATH"] = training_db

    # Patch DB_PATH
    from app import config as cfg
    import app.db as db_module
    import sqlite3

    orig_db_path = cfg.DB_PATH
    orig_db_module_path = db_module.DB_PATH
    orig_get_conn = db_module.get_connection
    orig_training_db = os.environ.get("TRAINING_DB_PATH")

    cfg.DB_PATH = test_db_str
    db_module.DB_PATH = test_db_str

    def _test_get_connection():
        conn = sqlite3.connect(test_db_str, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn
    db_module.get_connection = _test_get_connection

    # Init runtime DB
    from app.db import init_db, _write_lock
    init_db()

    # Seed users
    _hashes = {
        "admin":      "$2b$12$iMil5hjWKqKoNExSr3cmKO8tKj1JxtvjU8Cjas.scaF6gaESf5eUK",
        "security":    "$2b$12$pygxhjlHqMlw4x0gLEvA1udNz7PXivNDcq6fPzbhmcILbBZKGIZEW",
        "management":  "$2b$12$3IE1QRdoRyE7UosWWwP9Newy0i7p2grD7jm7fv9WlhcXmf596wvHW",
        "teacher":     "$2b$12$Ma0RVUosHJJVmZkv3unBBOB2.32IuKB.xaOA5g.fWHkAG0wOgvCSW",
    }
    with _write_lock:
        conn = db_module.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()[0] == 0:
                now = int(time.time())
                cur.executemany(
                    "INSERT INTO users (username, password_hash, role, homeroom_class, created_at) VALUES (?, ?, ?, ?, ?)",
                    [("admin", _hashes["admin"], "admin", None, now),
                     ("security", _hashes["security"], "security", None, now),
                     ("management", _hashes["management"], "management", None, now),
                     ("teacher", _hashes["teacher"], "teacher", "10A1", now)],
                )
                conn.commit()
        finally:
            conn.close()

    # Init training DB
    from app.training import dataset_repo
    dataset_repo.init_db(db_path=training_db)

    # Build app
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    app = FastAPI(title="School Gate Monitor — Task 3 Test")

    # Auth API
    from app.api.auth import router as auth_router
    # Task 3 routers
    from app.api.training_data import router as training_data_router
    from app.api.training_jobs import router as training_jobs_router
    from app.api.training_candidates import router as training_candidates_router
    from app.api.training_portable import router as training_portable_router

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(training_data_router)
    app.include_router(training_jobs_router)
    app.include_router(training_candidates_router)
    app.include_router(training_portable_router)

    yield app

    # Cleanup
    cfg.DB_PATH = orig_db_path
    db_module.DB_PATH = orig_db_module_path
    db_module.get_connection = orig_get_conn
    if orig_training_db is not None:
        os.environ["TRAINING_DB_PATH"] = orig_training_db
    else:
        os.environ.pop("TRAINING_DB_PATH", None)
    for ext in ("-wal", "-shm"):
        p = test_db_str + ext
        try:
            os.unlink(p)
        except OSError:
            pass


@pytest.fixture(scope="function")
def task03_client(task03_app):
    from fastapi.testclient import TestClient
    with TestClient(task03_app) as c:
        yield c


def get_token(client, username: str) -> str:
    resp = client.post("/api/auth/login",
                       json={"username": username, "password": "test123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(client, username: str = "admin") -> dict:
    return {"Authorization": f"Bearer {get_token(client, username)}"}