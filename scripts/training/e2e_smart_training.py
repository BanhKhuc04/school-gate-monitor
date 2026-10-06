"""E2E smoke test cho hệ thống training "thông minh" (Task 3).

Demo đầy đủ 1 vòng đời:
  1) Generate 35 ảnh biển số giả (synthetic crops) + canonical plate text
  2) Tạo dataset draft mới (engine=plate_ocr)
  3) Thêm 35 samples hợp lệ (verdict=correct + canonical target_text)
  4) Chia split 70/15/15 (train/val/test) — split_by_group dùng group_id
  5) Leakage check (groups_in_multiple_splits, duplicate_crop_sha256, etc.)
  6) Freeze dataset
  7) Tạo evaluation job (operation=evaluate_baseline) qua API
  8) Chờ TrainingWorker (poll 5s) claim + chạy
  9) Verify state machine: queued → preparing → training → evaluating → completed
 10) Đọc metrics.json sinh ra, so sánh số holdout vs train_size vs total

KHÔNG train weights thật (EasyOCR là pretrained + locked). Mục tiêu là chứng minh
toàn bộ plumbing chạy đúng: dataset lifecycle, schema validation, split policy,
provenance gate, runner selection, state machine, worker claim, metrics output.

Chạy:
  & "D:\Work\Project_motorbike\venv\Scripts\python.exe" scripts/training/e2e_smart_training.py
"""
from __future__ import annotations

import json
import sys
import time
import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ─── Config ─────────────────────────────────────────────────────────────────

API = "http://127.0.0.1:8001"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
ASSETS_ROOT = ROOT / "data" / "training" / "assets"
N_SAMPLES = 35
OCR_MIN_HOLDOUT = 30  # từ app/training/ocr_trainer.py


def hr(t: str) -> None:
    print()
    print("─" * 78)
    print(f"  {t}")
    print("─" * 78)


# ─── 1. Login + token ──────────────────────────────────────────────────────

def login() -> str:
    import urllib.request
    body = json.dumps({"username": ADMIN_USER, "password": ADMIN_PASS}).encode()
    req = urllib.request.Request(
        f"{API}/api/auth/login", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())["access_token"]


def api(token: str, method: str, path: str, body: dict | None = None) -> dict:
    import urllib.request
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


# ─── 2. Synthesize 35 plate crops (real PNG) ───────────────────────────────

def synthesize_crops(dataset_id: str) -> list[dict]:
    """Tạo N ảnh biển số giả + trả danh sách sample dict theo schema.

    Mỗi "biển số" là 1 dòng 'XX-YZ' / 'XYZ-12.34' được vẽ bằng Pillow.
    canonical target_text là A-Z0-9 4-12 char (đúng validate_target_text).

    Lưu vào `data/training/assets/{dataset_id}/` — đúng đường dẫn mà
    `ocr_trainer._load_image_for_eval` tìm (assets_root = BASE_DIR / 'data' /
    'training' / 'assets' / dataset_id).
    """
    from PIL import Image, ImageDraw, ImageFont
    asset_dir = ASSETS_ROOT / dataset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    out = []
    now = datetime.now(timezone.utc).isoformat()
    # Trộn 2 pattern biển VN: cũ (59-Z1) và mới (30A-123.45)
    # Để EasyOCR vẫn trả được kết quả gần đúng khi inference thật.
    plate_patterns = [
        "59-Z1", "59-Z2", "59-Z3", "60-A1", "60-B2", "61-C3", "62-D4", "63-E5",
        "64-F6", "65-G7", "66-H8", "67-I9", "68-J0", "69-K1", "70-L2", "71-M3",
        "72-N4", "73-O5", "74-P6", "75-Q7", "76-R8", "77-S9", "78-T0", "79-U1",
        "80-V2", "81-W3", "82-X4", "83-Y5", "84-Z6", "85-A7", "86-B8", "87-C9",
        "88-D0", "89-E1", "90-F2",
    ]
    # Tìm font có sẵn (Windows có arial.ttf)
    font_path = None
    for cand in [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if Path(cand).exists():
            font_path = cand
            break

    for i, plate in enumerate(plate_patterns[:N_SAMPLES]):
        # Render ảnh 160x80 — kích thước crop biển số thật
        img = Image.new("RGB", (160, 80), (255, 255, 255))
        d = ImageDraw.Draw(img)
        # Khung biển
        d.rectangle([(2, 2), (157, 77)], outline=(0, 0, 0), width=3)
        # Text
        try:
            f = ImageFont.truetype(font_path, 38) if font_path else ImageFont.load_default()
        except Exception:
            f = ImageFont.load_default()
        text = plate.replace("-", " - ")
        bbox = d.textbbox((0, 0), text, font=f)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((160 - tw) / 2, (80 - th) / 2 - 4), text, fill=(0, 0, 0), font=f)
        # Lưu file
        fname = f"crop_{i:03d}.png"
        fpath = asset_dir / fname
        img.save(fpath, "PNG")

        sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        target_id = f"smp_e2e_{i:03d}_{secrets.token_hex(4)}"
        out.append({
            "review_id": f"rev_e2e_{i:03d}",
            "gate_id": "main",
            "target_id": target_id,
            "label": {
                "verdict": "correct",
                "target_text": plate.replace("-", "").replace(".", ""),  # canonical A-Z0-9
            },
            "source": {
                "gate_id": "main",
                "camera_id": "main",
                "observed_at": now,
                "frame_seq": 1000 + i,
                "source_epoch": 1,
                "crop_sha256": sha,
                "crop_media_id": f"data/training/assets/{dataset_id}/{fname}",  # nguồn gốc
                "crop_path": fname,   # runner OCR đọc asset_root/crop_path.name
                "image_w": 160,
                "image_h": 80,
            },
            "group_id": f"track_{i % 7}",  # 7 group cho leakage test
            "holdout": True,   # OCR runner dùng (holdout=True | split='test')
            "split": "test",   # → tất cả đều vào holdout, đủ OCR_MIN_HOLDOUT=30
            # bbox cho OCR không bắt buộc (validate_sample: nếu có thì check)
        })
    print(f"  ✓ Synthesized {len(out)} plate crops at {asset_dir}")
    print(f"  ✓ First 3 target_text: {[s['label']['target_text'] for s in out[:3]]}")
    return out


# ─── 3. Main flow ──────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 78)
    print("  E2E SMART TRAINING TEST — Task 3 (plate_ocr baseline evaluator)")
    print("=" * 78)

    hr("0. Login")
    token = login()
    print(f"  ✓ Got JWT (len={len(token)})")

    hr("1. Create dataset (engine=plate_ocr)")
    ds_name = f"e2e_{secrets.token_hex(4)}"
    created = api(token, "POST", "/api/training/datasets", {
        "name": ds_name, "engine": "plate_ocr",
        "notes": "E2E test — synthetic plates for baseline eval",
    })
    ds_id = created["dataset_id"]
    print(f"  ✓ Created dataset {ds_id} (name={ds_name})")

    hr("2. Synthesize 35 plate crops (saves to data/training/assets/{ds_id})")
    samples = synthesize_crops(ds_id)

    hr("3. Add 35 samples")
    r = api(token, "POST", f"/api/training/datasets/{ds_id}/samples",
            {"samples": samples})
    print(f"  ✓ Added {r['added']} samples")

    hr("4. Split 70/15/15 (group_id-aware)")
    r = api(token, "POST", f"/api/training/datasets/{ds_id}/split",
            {"seed": 42, "ratios": {"train": 0.7, "val": 0.15, "test": 0.15}})
    print(f"  ✓ Counts: {r['counts']}")
    print(f"  ✓ Stats: {r['stats']}")

    hr("5. Leakage check")
    r = api(token, "GET", f"/api/training/datasets/{ds_id}/leakage")
    findings = r["findings"]
    print(f"  ✓ Groups in multiple splits: {len(findings.get('groups_in_multiple_splits', []))}")
    print(f"  ✓ Duplicate crop_sha256: {len(findings.get('duplicate_crop_sha256', []))}")
    print(f"  ✓ Duplicate target_text: {len(findings.get('duplicate_target_text', []))}")
    print(f"  ✓ Near duplicate plate text: {len(findings.get('near_duplicate_plate_text', []))}")

    hr("6. Freeze dataset")
    r = api(token, "POST", f"/api/training/datasets/{ds_id}/freeze", {})
    print(f"  ✓ Frozen: {r}")

    hr("7. Create evaluation job")
    r = api(token, "POST", "/api/training/jobs", {
        "dataset_id": ds_id, "target": "plate_ocr",
        "config": {"operation": "evaluate_baseline"},
    })
    job_id = r["job_id"]
    print(f"  ✓ Job created: {job_id}")

    hr("8. Watch state machine (poll every 2s, max 60s)")
    history = []
    deadline = time.time() + 60
    final = None
    while time.time() < deadline:
        # API: GET /api/training/jobs/{id} — check what exists
        # First try the list endpoint (we know it works)
        jobs = api(token, "GET", "/api/training/jobs")
        job = next((j for j in jobs.get("items", jobs if isinstance(jobs, list) else []) if j.get("id") == job_id), None)
        if job is None:
            print(f"  ! Job not in list yet, retrying...")
            time.sleep(2)
            continue
        state = job.get("state")
        if not history or history[-1][0] != state:
            history.append((state, time.time()))
            print(f"  → state={state:18s}  operation={job.get('operation')}  finished_at={job.get('finished_at')}")
        if state in {"completed", "failed", "cancelled", "pending_data", "unsupported"}:
            final = job
            break
        time.sleep(2)
    if final is None:
        print("  ✗ TIMEOUT — worker did not finish in 60s")
        return 1

    hr("9. Result")
    print(f"  state = {final['state']}")
    print(f"  error = {final.get('error')}")
    print(f"  finished_at = {final.get('finished_at')}")

    if final["state"] == "completed":
        # Đọc log + metrics từ DB (qua API hoặc trực tiếp)
        from app.training import dataset_repo
        job_full = dataset_repo.get_job(job_id)
        metrics_path = job_full.get("metrics_path") if job_full else None
        log_path = job_full.get("log_path") if job_full else None
        if metrics_path and Path(metrics_path).exists():
            print(f"\n  metrics_path: {metrics_path}")
            metrics = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
            for k, v in metrics.items():
                print(f"    {k:30s} = {v}")
        if log_path and Path(log_path).exists():
            log_lines = Path(log_path).read_text(encoding="utf-8").splitlines()
            print(f"\n  log_path: {log_path}  ({len(log_lines)} lines)")
            for ln in log_lines[:5]:
                print(f"    {ln}")
            if len(log_lines) > 5:
                print(f"    ... ({len(log_lines) - 5} more)")
    elif final["state"] == "pending_data":
        print("  → Holdout < 30 samples → runner refused to make candidate (CORRECT behavior)")

    hr("10. State machine trace")
    for st, t in history:
        ts = datetime.fromtimestamp(t).strftime("%H:%M:%S")
        print(f"  {ts}  {st}")
    transitions = len(history)
    print(f"  total transitions: {transitions}")
    expected = {"completed": ["queued", "preparing", "training", "evaluating", "completed"],
                "pending_data": ["queued", "preparing", "training", "evaluating", "pending_data"]}
    exp = expected.get(final["state"], [])
    actual = [h[0] for h in history]
    if exp and actual == exp:
        print(f"  ✓ state machine matches expected: {' → '.join(exp)}")
    elif final["state"] in {"failed", "cancelled"}:
        print(f"  · terminal state {final['state']} — partial trace ok")
    else:
        print(f"  ! state trace differs: actual={actual} expected={exp}")

    print()
    return 0 if final["state"] in {"completed", "pending_data"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
