"""QA launcher — start backend trên cổng riêng với DB/media/backup tạm.

Sử dụng:
    .\\venv\\Scripts\\python.exe -m scripts.qa_launcher start
    .\\venv\\Scripts\\python.exe -m scripts.qa_launcher stop
    .\\venv\\Scripts\\python.exe -m scripts.qa_launcher status

Mặc định:
- BACKEND_PORT=8001
- DB tạm: tasks/task-02/qa/qa.db
- SNAPSHOTS_DIR: tasks/task-02/qa/snapshots
- CLIPS_DIR: tasks/task-02/qa/clips
- STUDENT_PHOTOS_DIR: tasks/task-02/qa/student_photos
- BACKUP_DIR: tasks/task-02/qa/backups
- CLEANUP_ENABLED=0  (test riêng thay vì tự chạy)
- CLEANUP_INTERVAL_HOURS=24
- CLEANUP_RETENTION_DAYS=90
- BACKUP_ENABLED=0  (test riêng)
- BACKUP_INTERVAL_HOURS=24
- BACKUP_KEEP_COUNT=14
- BACKUP_MEDIA_ENABLED=0  (backup DB only ở default)
- PUBLIC_REGISTER_ENABLED=0  (mặc định tắt)
- ENVIRONMENT=development  (cho phép static /media mount)
- JWT_SECRET_KEY=test-secret-not-for-production-use-only-qa-suite
- CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5186

Backend stdout/stderr: tasks/task-02/qa/backend.log
PID file: tasks/task-02/qa/backend.pid

Không ghi đè DB/media/backup vận hành.
"""
from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QA_ROOT = ROOT / "tasks" / "task-02" / "qa"
PID_FILE = QA_ROOT / "backend.pid"
LOG_FILE = QA_ROOT / "backend.log"

# Đảm bảo các thư mục tồn tại
for sub in ("snapshots", "clips", "student_photos", "backups"):
    (QA_ROOT / sub).mkdir(parents=True, exist_ok=True)


def _qa_env_dict(port: int) -> dict[str, str]:
    env = os.environ.copy()
    env["ENVIRONMENT"] = "development"
    env["QA_MODE"] = "1"
    env["CV_PIPELINES_ENABLED"] = "0"
    env["TASK3_TRAINING_WORKER_ENABLED"] = "0"
    env["TASK3_SAMPLE_COLLECTOR_ENABLED"] = "0"
    env["TRAINING_DB_PATH"] = str(QA_ROOT / "training.db")
    env["TASK3_CONTEXT_PATH"] = str(QA_ROOT / "training")
    env["APP_DB_PATH"] = str(QA_ROOT / "qa.db")
    env["SNAPSHOTS_DIR"] = str(QA_ROOT / "snapshots")
    env["CLIPS_DIR"] = str(QA_ROOT / "clips")
    env["STUDENT_PHOTOS_DIR"] = str(QA_ROOT / "student_photos")
    env["BACKUP_DIR"] = str(QA_ROOT / "backups")
    env["BACKEND_PORT"] = str(port)
    # Tắt các worker chạy nền để test sạch; test riêng sẽ trigger.
    env["CLEANUP_ENABLED"] = "0"
    env["BACKUP_ENABLED"] = "0"
    env["BACKUP_MEDIA_ENABLED"] = "0"
    env["BACKUP_INTERVAL_HOURS"] = "24"
    env["BACKUP_KEEP_COUNT"] = "14"
    env["CLEANUP_INTERVAL_HOURS"] = "24"
    env["CLEANUP_RETENTION_DAYS"] = "90"
    env["PUBLIC_REGISTER_ENABLED"] = "0"
    env["CSV_IMPORT_MAX_BYTES"] = str(5 * 1024 * 1024)
    env["CSV_IMPORT_MAX_ROWS"] = "10000"
    # Test secret: KHÔNG dùng cho production. Marker rõ.
    env.setdefault("JWT_SECRET_KEY", "qa-suite-secret-DO-NOT-USE-IN-PROD-0123456789abcdef")
    # CORS rộng để Vite preview các port khác nhau truy cập được.
    env.setdefault(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5174,"
        "http://localhost:5186,http://127.0.0.1:5173,http://127.0.0.1:5174,"
        "http://127.0.0.1:5186",
    )
    return env


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


def start(port: int) -> int:
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            os.kill(old_pid, 0)
            print(f"[qa_launcher] Backend already running pid={old_pid}")
            return old_pid
        except (OSError, ValueError):
            PID_FILE.unlink(missing_ok=True)

    if _port_in_use(port):
        print(f"[qa_launcher] Port {port} already in use; refusing to start.")
        return 0

    env = _qa_env_dict(port)
    log = open(LOG_FILE, "ab", buffering=0)
    # Spawn a small launcher script that sets env then exec uvicorn — guarantees
    # env is present even if `python -m uvicorn` is re-launched separately.
    launcher = QA_ROOT / "_launch_uvicorn.py"
    launcher.write_text("from uvicorn import main\nif __name__ == '__main__': main()\n")
    proc = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
         '--port', str(port), '--log-level', 'info'],
        env=env,
        cwd=str(ROOT),
        stdout=log,
        stderr=log,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    PID_FILE.write_text(str(proc.pid))
    print(f"[qa_launcher] Backend started pid={proc.pid} port={port} log={LOG_FILE}")

    # Wait for HTTP listener up (≤ 15s)
    for _ in range(60):
        if _port_in_use(port):
            print(f"[qa_launcher] Backend listening on http://127.0.0.1:{port}")
            return proc.pid
        time.sleep(0.25)
    print("[qa_launcher] Backend did not bind in time; see log.")
    return 1


def stop() -> bool:
    if not PID_FILE.exists():
        print("[qa_launcher] No PID file; nothing to stop.")
        return True
    try:
        pid = int(PID_FILE.read_text().strip())
    except ValueError:
        PID_FILE.unlink(missing_ok=True)
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    # Đợi tiến trình tắt (≤ 8s)
    for _ in range(32):
        try:
            os.kill(pid, 0)
        except OSError:
            PID_FILE.unlink(missing_ok=True)
            print(f"[qa_launcher] Backend pid={pid} stopped.")
            return True
        time.sleep(0.25)
    # Force kill
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    PID_FILE.unlink(missing_ok=True)
    print(f"[qa_launcher] Backend pid={pid} force-killed.")
    return True


def status(port: int) -> int:
    pid = 0
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except ValueError:
            pass
    listening = _port_in_use(port)
    print(f"[qa_launcher] pid_file={pid or 'none'} listening={listening} port={port}")
    return 0 if listening else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("start", "stop", "status", "wait"))
    p.add_argument("--port", type=int, default=int(os.environ.get("BACKEND_PORT", 8001)))
    args = p.parse_args()

    if args.action == "start":
        return 0 if start(args.port) else 1
    if args.action == "stop":
        return 0 if stop() else 1
    if args.action == "status":
        return status(args.port)
    if args.action == "wait":
        # Wait cho tới khi backend lắng nghe hoặc timeout (≤ 30s)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if _port_in_use(args.port):
                print(f"[qa_launcher] ready on {args.port}")
                return 0
            time.sleep(0.5)
        print("[qa_launcher] timeout waiting for backend")
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
