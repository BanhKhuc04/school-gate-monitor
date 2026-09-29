"""
Verify Bước 3 (ghép 2 camera) bằng 2 video training thật, KHÔNG qua browser.

- Set CAMERA_SOURCE / CAMERA_SOURCE_SECONDARY trỏ 2 file mp4 khác nhau
  từ C:\\Users\\khucv\\Downloads\\tranning\\ (camera cổng trường thật).
- Chạy pipeline trong N giây, đọc DB xem:
  + Có violation mới không?
  + Có 2 event từ 2 gate khác nhau trong cùng cửa sổ ±15s không?
  + Sau khi insert, correlation có chạy không? (linked_violation_id có khác NULL không?)

Script chỉ chạy verify, không phải test — output JSON đọc được.
"""
import json
import os
import subprocess
import sys
import time
import signal
from pathlib import Path

# Set env TRƯỚC khi import app
TRANNING_DIR = Path(r"C:\Users\khucv\Downloads\tranning")
VIDEO_A = TRANNING_DIR / "1790578609446_6349341119162671419_6349341119162671419.mp4"
VIDEO_B = TRANNING_DIR / "1790578669818_6349341119162671419_6349341119162671419.mp4"
RUN_SECONDS = 60  # chạy pipeline 60s rồi tắt


def main():
    if not VIDEO_A.exists() or not VIDEO_B.exists():
        print(json.dumps({"error": "missing videos", "A": str(VIDEO_A), "B": str(VIDEO_B)}, indent=2, ensure_ascii=False))
        sys.exit(1)

    env = os.environ.copy()
    env["CAMERA_SOURCE"] = str(VIDEO_A)
    env["CAMERA_SOURCE_SECONDARY"] = str(VIDEO_B)
    env["CAMERA_LOOP"] = "1"
    env["GATE_SECONDARY_LOOP"] = "1"
    # Khởi động app — lifespan sẽ start pipeline threads
    cmd = ["./venv/Scripts/python.exe", "-m", "uvicorn", "app.main:app",
           "--host", "127.0.0.1", "--port", "8765", "--log-level", "warning"]
    print(f"[verify] Starting uvicorn with CAMERA_SOURCE={VIDEO_A.name}, CAMERA_SOURCE_SECONDARY={VIDEO_B.name}")
    proc = subprocess.Popen(cmd, env=env, cwd=str(Path(__file__).parent.parent),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(RUN_SECONDS)
        print(f"[verify] {RUN_SECONDS}s elapsed, stopping uvicorn...")
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            stdout, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, _ = proc.communicate()

    # Đọc DB để kiểm tra
    sys.path.insert(0, str(Path(__file__).parent.parent))
    # Tránh lifespan init pipeline lần nữa
    os.environ["CAMERA_SOURCE"] = ""
    os.environ["CAMERA_SOURCE_SECONDARY"] = ""
    from app.db import get_connection, init_db
    init_db()
    conn = get_connection()
    try:
        # Lấy violations trong 2 phút gần nhất (đủ bao quát 60s chạy + buffer)
        rows = conn.execute(
            """SELECT id, timestamp, gate_id, plate_read, plate_matched,
                      violation_type, status, linked_violation_id, correlation_status
               FROM violation_events
               WHERE timestamp >= datetime('now', '-5 minutes')
               ORDER BY timestamp DESC"""
        ).fetchall()
        # Group theo gate để biết phân bổ
        by_gate = {}
        for r in rows:
            by_gate.setdefault(r["gate_id"] or "null", []).append(dict(r))

        summary = {
            "total_new_violations": len(rows),
            "by_gate_count": {k: len(v) for k, v in by_gate.items()},
            "linked_count": sum(1 for r in rows if r["linked_violation_id"] is not None),
            "correlation_status_breakdown": {
                "matched": sum(1 for r in rows if r["correlation_status"] == "matched"),
                "needs_review": sum(1 for r in rows if r["correlation_status"] == "needs_review"),
                "unmatched": sum(1 for r in rows if r["correlation_status"] == "unmatched"),
                "null": sum(1 for r in rows if r["correlation_status"] is None),
            },
            "violations": [dict(r) for r in rows[:20]],  # 20 dòng đầu để xem chi tiết
            "uvicorn_tail": stdout[-2000:] if stdout else "",  # log cuối
        }
    finally:
        conn.close()
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
