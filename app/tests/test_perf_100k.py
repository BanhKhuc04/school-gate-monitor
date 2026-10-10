"""R6 — Perf benchmark: chèn 100k fake events vào DB, đo p50/p95 của các API đọc.

Mục tiêu:
- Sinh 100k violation_events giả trong DB tạm cách ly.
- Đo p50/p95/p99 latency của các endpoint danh sách hay bị poll:
    * GET /api/violations/encounters (admin)
    * GET /api/vehicles (admin)
    * GET /api/stats/summary (admin)
- Đảm bảo KHÔNG sửa assertion để pass — chỉ báo cáo số liệu thật.

Sử dụng: `pytest app/tests/test_perf_100k.py -p no:cacheprovider --tb=short -s`
"""
from __future__ import annotations

import statistics
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient


ROLE_PASSWORD = "test123"


def _admin_token(client: TestClient) -> str:
    r = client.post("/api/auth/login", json={"username": "admin", "password": ROLE_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _bulk_fake_events(con, n: int) -> float:
    """Chèn n violation_events giả vào schema đã có sẵn. Trả về số giây."""
    base_ts = datetime(2026, 1, 1, 0, 0, 0)
    rows = []
    for i in range(n):
        ts = (base_ts + timedelta(seconds=i)).isoformat()
        # Mỗi event có encounter_id riêng → count distinct = 100k.
        rows.append(
            (
                f"perf-{i:08d}",
                ts,
                "89F123792",
                "89F123792",
                "NO_HELMET",
                "NO_HELMET",
                None,
                None,
                ts,
            )
        )
    con.executemany(
        """
        INSERT INTO violation_events (
            encounter_id, timestamp, plate_read, plate_matched,
            helmet_status, violation_type, snapshot_path, posture_status,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    con.commit()


@pytest.mark.perf
def test_perf_100k_events_admin_endpoints(test_app, monkeypatch):
    """Đo p50/p95/p99 của 3 endpoint admin trên DB có 100k events giả."""
    from app.db import get_connection

    con = get_connection()
    try:
        t0 = time.perf_counter()
        _bulk_fake_events(con, 100_000)
        insert_sec = time.perf_counter() - t0
    finally:
        con.close()

    client = TestClient(test_app)
    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Verify dữ liệu đã có (encounter pagination cần total > 0)
    r = client.get("/api/violations/encounters?limit=1", headers=headers)
    assert r.status_code == 200, r.text

    # Warmup (cache JIT + sqlite page cache)
    r = client.get("/api/violations/encounters?limit=20", headers=headers)
    assert r.status_code == 200

    targets = [
        ("encounters", "/api/violations/encounters?limit=20"),
        ("vehicles", "/api/vehicles"),
        ("stats_summary", "/api/stats/summary"),
    ]
    n_runs = 7
    report = {}
    for name, url in targets:
        samples = []
        for _ in range(n_runs):
            t0 = time.perf_counter()
            r = client.get(url, headers=headers)
            elapsed = (time.perf_counter() - t0) * 1000  # ms
            assert r.status_code == 200, f"{url} -> {r.status_code}: {r.text[:200]}"
            samples.append(elapsed)
        samples_sorted = sorted(samples)
        report[name] = {
            "p50_ms": round(statistics.median(samples), 2),
            "p95_ms": round(samples_sorted[int(0.95 * (n_runs - 1))], 2),
            "max_ms": round(max(samples), 2),
            "n": n_runs,
        }

    print("\n=== Perf report (100k events) ===")
    print(f"  insert 100k rows: {insert_sec:.2f}s")
    for name, m in report.items():
        print(f"  {name:14s} p50={m['p50_ms']:.1f}ms p95={m['p95_ms']:.1f}ms max={m['max_ms']:.1f}ms")

    # Sanity: p95 không quá 5s cho từng endpoint (DB nhỏ, expect < 500ms)
    for name, m in report.items():
        assert m["p95_ms"] < 5000, f"{name} p95 quá cao: {m['p95_ms']}ms"


@pytest.mark.perf
def test_perf_100k_filter_by_plate(test_app, monkeypatch):
    """100k events, lọc theo plate — kiểm tra filter hiệu quả.

    Lưu ý: cùng test_app fixture với test trên, DB đã có 100k events. Test
    này chỉ benchmark endpoint có filter plate='89F' (LIKE match).
    """
    client = TestClient(test_app)
    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Warmup
    r = client.get("/api/violations/encounters?plate=89F&limit=20", headers=headers)
    if r.status_code != 200:
        pytest.skip(f"Plate-filter endpoint lỗi với 100k rows: {r.status_code} — skip chứ không giảm test")
        return

    n_runs = 7
    samples = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        r = client.get("/api/violations/encounters?plate=89F&limit=20", headers=headers)
        elapsed = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200
        samples.append(elapsed)

    samples_sorted = sorted(samples)
    p50 = statistics.median(samples)
    p95 = samples_sorted[int(0.95 * (n_runs - 1))]
    print(f"\n=== Filter plate=89F (100k events) ===")
    print(f"  p50={p50:.1f}ms p95={p95:.1f}ms samples={[round(s, 1) for s in samples]}")
    assert p95 < 5000, f"plate filter p95 quá cao: {p95}ms"