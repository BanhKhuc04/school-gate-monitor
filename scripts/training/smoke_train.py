"""CLI: smoke training job (no real GPU) — sinh candidate, đo holdout trống.

Mục đích: chứng minh hạ tầng jobs / evaluator / candidate lifecycle hoạt động
khi có dữ liệu thật (≥1 sample verified). KHÔNG phải bằng chứng training thật.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Smoke training job")
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--target", choices=["plate_ocr", "plate_detector", "helmet"],
                   default="plate_ocr")
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--imgsz", type=int, default=320)
    args = p.parse_args()

    from app.training import dataset_repo, evaluator, jobs, provenance

    samples = dataset_repo.list_samples(args.dataset_id)
    holdout = [s for s in samples if s.get("holdout") or s.get("split") == "test"]
    train_samples = [s for s in samples if not (s.get("holdout") or s.get("split") == "test")]
    if not holdout:
        print("[smoke] dataset chưa có holdout → dùng 20% cuối làm holdout")
        holdout = samples[len(samples) * 4 // 5:]
        train_samples = samples[:len(samples) * 4 // 5]

    # Runner adapter (no real training): simulate candidate với baseline-like metrics
    job_id = jobs.create_job(dataset_id=args.dataset_id, target=args.target,
                              config={"epochs": args.epochs, "imgsz": args.imgsz})
    print(f"[smoke] job_id={job_id}")

    # Chạy job (chuyển state queued → preparing → training → evaluating → completed)
    def _simulate_train(job, db_path):
        import traceback
        print(f"[smoke runner] enter, db_path={db_path!r}")
        print(f"[smoke runner] job={job['id']} state={job['state']}")
        # Dùng metrics giả từ holdout (đo trên bản thân dataset freeze — chỉ để verify hạ tầng)
        predictions = {s["target_id"]: s.get("label", {}).get("target_text", "") for s in holdout}
        if args.target == "plate_ocr":
            metrics = evaluator.evaluate_ocr(holdout, predictions=predictions)
        else:
            metrics = {"total": len(holdout), "exact_match_pct": 0, "cer_avg": 1.0,
                      "note": "smoke — không đo detector/helmet thật"}
        # Tạo candidate
        candidate_id = dataset_repo.create_candidate(
            job_id=job["id"], engine=args.target, target=args.target,
            model_class="EasyOCR.Smoke",
            model_path="/tmp/smoke.pt", config={"epochs": args.epochs},
        )
        # Gắn metrics vào job
        metrics_path = f"data/training/_smoke_metrics_{candidate_id}.json"
        Path(metrics_path).parent.mkdir(parents=True, exist_ok=True)
        Path(metrics_path).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        from app.training import dataset_repo as _repo
        dsn = db_path or _repo.default_db_path()
        import sqlite3 as _sqlite3
        conn = _repo._connect(dsn) if os.path.dirname(dsn) else _repo._connect(dsn)
        try:
            cur = conn.cursor()
            cur.execute("UPDATE dataset_jobs SET metrics_path=? WHERE id=?",
                        (metrics_path, job["id"]))
            conn.commit()
        finally:
            conn.close()
        return {"candidate_id": candidate_id, "metrics": metrics, "holdout_size": len(holdout)}

    result = jobs.run_training_job(job_id, runner=_simulate_train)
    print(f"[smoke] job result: {result['state']}")
    if result.get("result"):
        print(f"[smoke] candidate_id={result['result']['candidate_id']}")
        print(f"[smoke] metrics={result['result']['metrics']}")
    return 0 if result["state"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())