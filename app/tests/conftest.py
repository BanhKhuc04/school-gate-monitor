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

# Set paths BEFORE any test imports app.config. Never use operational media as
# the implicit source of a backup test; each run starts with empty fixtures.
import tempfile
_QA_ROOT = Path(__file__).resolve().parents[2] / '.qa'
_QA_ROOT.mkdir(exist_ok=True)
_QA_RUN = Path(tempfile.mkdtemp(prefix='pytest-', dir=_QA_ROOT))
for _key, _relative in {
    'APP_DB_PATH': 'app.db', 'TRAINING_DB_PATH': 'training.db',
    'SNAPSHOTS_DIR': 'snapshots', 'CLIPS_DIR': 'clips',
    'STUDENT_PHOTOS_DIR': 'student_photos', 'BACKUP_DIR': 'backups',
    'CONTINUOUS_RECORDING_DIR': 'recordings',
    'TASK3_CONTEXT_PATH': 'training',
}.items():
    os.environ[_key] = str(_QA_RUN / _relative)
for _relative in ('snapshots', 'clips', 'student_photos', 'backups', 'recordings', 'training'):
    (_QA_RUN / _relative).mkdir()
os.environ.update(QA_MODE='1', CV_PIPELINES_ENABLED='0', BACKUP_ENABLED='0',
                  CLEANUP_ENABLED='0', TASK3_TRAINING_WORKER_ENABLED='0',
                  TASK3_SAMPLE_COLLECTOR_ENABLED='0', TASK3_COLLECTOR_ENABLED='0')


@pytest.fixture(scope='session', autouse=True)
def isolated_training_schema():
    from app.training import dataset_repo
    dataset_repo.init_db()


def pytest_configure(config):
    if not config.option.basetemp:
        config.option.basetemp = str(_QA_RUN / 'tmp')


def pytest_sessionfinish(session, exitstatus):
    import json, shutil
    size = sum(p.stat().st_size for p in _QA_RUN.rglob('*') if p.is_file())
    (_QA_RUN/'completed.json').write_text(json.dumps({'bytes': size, 'exitstatus': int(exitstatus)}))
    if size > 1024**3:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        print('QA quota exceeded: run artifacts > 1 GiB')
    completed = sorted((p for p in _QA_ROOT.glob('pytest-*') if (p/'completed.json').exists()),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    for old in completed[3:]:
        resolved = old.resolve()
        if resolved.is_relative_to(_QA_ROOT.resolve()) and not old.is_symlink():
            shutil.rmtree(resolved)


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
    # Seed users — generated with: bcrypt.hashpw(b'test123', bcrypt.gensalt(rounds=12))
    # To regenerate: python -c "import bcrypt; print(bcrypt.hashpw(b'test123', bcrypt.gensalt(rounds=12)).decode())"
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

    # Build app
    app = FastAPI(title="School Gate Monitor — Test")
    from app.api.guard import router as guard_router
    from app.api.admin import vehicles_router, stats_router, violations_router, roster_router
    from app.api.auth import router as auth_router
    from app.api.users import router as users_router
    from app.api.dev import router as dev_router
    from app.api.system import router as system_router
    from app.api.roi import router as roi_router
    from app.api.register import router as register_router
    from app.api.media import router as media_router  # D6.2
    from app.api.camera import router as camera_router  # Đợt 1 multi-camera mapping
    from app.api.recognition_reviews import router as recognition_reviews_router  # FR6
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
    app.include_router(roster_router)
    app.include_router(register_router)
    app.include_router(media_router)  # D6.2
    app.include_router(camera_router)  # Đợt 1 multi-camera mapping
    app.include_router(recognition_reviews_router)  # FR6

    from app.api.training_data import router as training_data_router
    from app.api.training_jobs import router as training_jobs_router
    from app.api.training_candidates import router as training_candidates_router
    from app.api.training_portable import router as training_portable_router
    app.include_router(training_data_router)
    app.include_router(training_jobs_router)
    app.include_router(training_candidates_router)
    app.include_router(training_portable_router)

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


# ─── Production-mode app factory (D6.2: verify static mount disabled) ───────────
@pytest.fixture(scope="module")
def test_app_env_prod(request, tmp_path_factory):
    """
    Like test_app but with ENVIRONMENT=production so static /media mount is
    disabled and media API must be used instead.
    """
    import os
    original_environment = os.environ.get("ENVIRONMENT")
    os.environ["ENVIRONMENT"] = "production"

    from app import config as cfg
    import app.db as db_module
    import sqlite3

    orig_db_path = cfg.DB_PATH
    orig_db_module_path = db_module.DB_PATH
    orig_get_conn = db_module.get_connection
    orig_env = original_environment

    tmp_dir = tmp_path_factory.mktemp(f"test_prod_{request.module.__name__}")
    test_db = tmp_dir / "test.db"
    test_db_str = str(test_db)
    cfg.DB_PATH = test_db_str
    db_module.DB_PATH = test_db_str

    def _test_get_connection():
        conn = sqlite3.connect(test_db_str, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    db_module.get_connection = _test_get_connection

    from app.db import init_db, _write_lock
    init_db()

    _hashes = {
        "admin":     "$2b$12$iMil5hjWKqKoNExSr3cmKO8tKj1JxtvjU8Cjas.scaF6gaESf5eUK",
        "security":   "$2b$12$pygxhjlHqMlw4x0gLEvA1udNz7PXivNDcq6fPzbhmcILbBZKGIZEW",
        "management": "$2b$12$3IE1QRdoRyE7UosWWwP9Newy0i7p2grD7jm7fv9WlhcXmf596wvHW",
        "teacher":    "$2b$12$Ma0RVUosHJJVmZkv3unBBOB2.32IuKB.xaOA5g.fWHkAG0wOgvCSW",
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

    app = FastAPI(title="School Gate Monitor — Test Prod")
    from app.api.guard import router as guard_router
    from app.api.admin import vehicles_router, stats_router, violations_router, roster_router
    from app.api.auth import router as auth_router
    from app.api.users import router as users_router
    from app.api.dev import router as dev_router
    from app.api.system import router as system_router
    from app.api.roi import router as roi_router
    from app.api.register import router as register_router
    from app.api.media import router as media_router
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(guard_router)
    app.include_router(auth_router)
    app.include_router(vehicles_router)
    app.include_router(violations_router)
    app.include_router(stats_router)
    app.include_router(users_router)
    app.include_router(dev_router)
    app.include_router(system_router)
    app.include_router(roi_router)
    app.include_router(roster_router)
    app.include_router(register_router)
    app.include_router(media_router)

    yield app

    cfg.DB_PATH = orig_db_path
    db_module.DB_PATH = orig_db_module_path
    db_module.get_connection = orig_get_conn
    if orig_env is not None:
        os.environ["ENVIRONMENT"] = orig_env
    else:
        os.environ.pop("ENVIRONMENT", None)
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


# ─── S10/F02: test isolation fixture ─────────────────────────────────────────
# Khi cần test code mà import cv2 nhưng env không có cv2, ta gán
# `sys.modules["cv2"] = SimpleNamespace()` rồi test chạy được. Nhưng nếu quên
# xoá → test kế tiếp nhận stub rỗng → crash không liên quan. Fixture này
# lưu lại snapshot của sys.modules trước test, hoàn trả sau test.
@pytest.fixture
def restore_sys_modules():
    """Snapshot sys.modules + env vars ở setup, hoàn trả khi teardown.

    Dùng cho test vừa gán `sys.modules["cv2"]` (hoặc module nặng khác)
    để tránh ô nhiễm các test khác chạy cùng session. Cũng khôi phục
    `os.environ` keys bị test set/add trong quá trình chạy.
    """
    import sys as _sys
    import os as _os
    saved_modules = dict(_sys.modules)
    # Chỉ lưu các key test thường động vào; tránh snapshot toàn bộ env (nhiều
    # biến app khác có thể thay đổi ngoài ý muốn).
    _ENV_KEYS_TO_TRACK = (
            "WS_ALLOWED_ORIGINS", "ENVIRONMENT", "DB_PATH",
            "ALLOWED_ORIGINS", "CORS_ORIGINS", "TESTING",
    )
    saved_env = {k: _os.environ.get(k) for k in _ENV_KEYS_TO_TRACK}
    try:
        yield
    finally:
        # Khôi phục sys.modules: xoá các key mới được thêm vào trong test,
        # khôi phục các key đã bị gán đè về giá trị ban đầu.
        import types
        for key, value in list(_sys.modules.items()):
            if key not in saved_modules and isinstance(value, types.SimpleNamespace):
                _sys.modules.pop(key, None)
        for key, prev_value in saved_modules.items():
            current = _sys.modules.get(key)
            # Nếu identity thay đổi (bị gán đè) → khôi phục
            if current is not prev_value:
                _sys.modules[key] = prev_value
        # Khôi phục env keys
        for k, prev in saved_env.items():
            if prev is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = prev


def stub_cv2_module():
    """Helper an toàn để stub cv2 khi env thiếu. KHÔNG ghi đè nếu cv2 đã có
    trong sys.modules (kể cả khi là real cv2 — stub sẽ phá)."""
    import sys as _sys
    import types as _types
    if "cv2" not in _sys.modules:
        _sys.modules["cv2"] = _types.SimpleNamespace()


@pytest.fixture(autouse=True)
def isolated_guard_stream(request, monkeypatch):
    """Guard route tests never create models, RTSP streams or endless bodies."""
    if request.module.__name__.split(".")[-1] not in {"test_guard", "test_guard_origin"}:
        return
    from types import SimpleNamespace
    import app.cv.pipeline as pipelines
    import app.api.guard as guard
    fake = SimpleNamespace(get_jpeg=lambda: b"\xff\xd8fixture\xff\xd9", get_alert=lambda: None)
    monkeypatch.setattr(pipelines, "get_pipeline", lambda gate_id="main": fake)
    original = guard.mjpeg_frames
    monkeypatch.setattr(guard, "mjpeg_frames", lambda pipeline: original(pipeline, frame_limit=1))


# ─── T4 FIX: Per-test isolated DB cho pipeline tests ────────────────────────────
@pytest.fixture
def pipeline_test_env(tmp_path, monkeypatch):
    """Isolated DB + init cho pipeline tests (test_camera_pipeline.py và các
    test khác touch production DB). Lý do: gate_roi table không tồn tại
    trên real DB, gây sqlite3.OperationalError khi pipeline tests chạy."""
    import sqlite3
    import app.config as cfg
    import app.db as db_module

    test_db = tmp_path / "pipeline_test.db"
    test_db_str = str(test_db)

    monkeypatch.setattr(cfg, "DB_PATH", test_db_str)
    monkeypatch.setattr(db_module, "DB_PATH", test_db_str)

    def _conn():
        conn = sqlite3.connect(test_db_str, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    monkeypatch.setattr(db_module, "get_connection", _conn)

    from app.db import init_db
    init_db()
    yield
