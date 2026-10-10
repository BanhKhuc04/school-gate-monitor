"""Task 3 — Baseline Evaluator cho OCR (EasyOCR-based).

ĐÂY LÀ EVALUATOR, KHÔNG PHẢI TRAINER. Docstring này phải rõ ràng:
  - `run_ocr_training_job` là EVALUATOR chạy EasyOCR baseline inference trên holdout.
  - Nó KHÔNG train weights mới — EasyOCR là pretrained và locked.
  - Nó trả `state="completed"` khi evaluation xong, không phải khi training xong.
  - Khi có custom trained OCR model thật, cần thêm `run_ocr_training_job_v2()`
    hoặc tách `run_ocr_trainer_job()` riêng cho fine-tuning.

Hợp đồng runner:
    runner(job, db_path) -> {
        state: "completed" | "pending_data" | "unsupported",
        metrics: {...},   # evaluated holdout metrics
        model_path?: str, # None for baseline evaluator
        model_sha256?: str,
        log_path: str,
    }
"""
from __future__ import annotations

# Marker: đây là evaluator, không phải trainer tối ưu
IS_EVALUATOR = True
EVALUATOR_LABEL = "EasyOCR.baseline.evaluator"

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

from app.training import dataset_repo, evaluator, provenance
from app.training.schemas import SchemaError

LOG = logging.getLogger("task3.ocr_trainer")

OCR_MIN_HOLDOUT = 30


def _load_image_for_eval(asset_root: Path, sample: dict) -> Any | None:
    """Load crop image từ asset_root theo crop_path trong sample.source.

    Trả None nếu không có path / file không tồn tại.
    """
    src = sample.get("source") or {}
    crop_path = src.get("crop_path")
    if not crop_path:
        return None
    p = asset_root / Path(crop_path).name
    if not p.exists():
        # Thử trong asset root theo path relative từ dataset_repo
        p2 = Path(crop_path)
        if not p2.exists():
            return None
        p = p2
    try:
        # Đọc ảnh mà không cần cv2 (có thể chưa có) — dùng Pillow nếu có
        try:
            from PIL import Image  # type: ignore
            import numpy as np
            img = Image.open(p).convert("RGB")
            return np.array(img)[:, :, ::-1]  # RGB→BGR
        except ImportError:
            return None
    except Exception:  # noqa: BLE001
        return None


def _run_inference(engine, image_bgr: Any) -> list[dict]:
    """Chạy OCR engine, trả list[{text, conf}]. Mặc định lấy prediction có conf cao nhất."""
    try:
        results = engine.read(image_bgr)
    except Exception as e:  # noqa: BLE001
        LOG.warning("[task3.ocr_trainer] inference error: %s", e)
        return []
    out = []
    for r in results:
        out.append({"text": r.text, "conf": float(r.confidence)})
    return out


def _canonical(text: str) -> str:
    from app.training import provenance as _prov
    return _prov.normalize_plate_text(text)


def _pick_best_text(results: list[dict]) -> str:
    """EasyOCR EasyOCR .read() trả list; pick text có conf cao nhất (canonical)."""
    if not results:
        return ""
    best = max(results, key=lambda r: r.get("conf", 0.0))
    return _canonical(best.get("text", ""))


def run_ocr_training_job(
    *,
    dataset_id: str,
    job_id: str,
    target: str = "plate_ocr",
    epochs: int = 1,
    gpu: bool = False,
    db_path: str | None = None,
    output_root: str | None = None,
) -> dict:
    """Runner OCR thật: holdout inference bằng EasyOCR baseline.

    Đây KHÔNG phải training thật (EasyOCR là pretrained + locked). Đây là
    EVALUATION thật của baseline EasyOCR trên dataset của Task 3. Khi có custom
    trained model (qua trainer OCR riêng), sẽ thêm vào đây.

    Returns dict có:
      - state: "completed" | "pending_data" | "unsupported"
      - metrics: dict đo trên holdout
      - model_path: đường dẫn artifact (EasyOCR không tạo weights mới → để None)
      - model_sha256: "" (baseline không có)
      - log_path: file log
      - holdout_size, train_size
    """
    from app.config import BASE_DIR

    # 1. Lấy samples
    samples = dataset_repo.list_samples(dataset_id, db_path=db_path)
    holdout = [s for s in samples if s.get("holdout") or s.get("split") == "test"]
    train_samples = [s for s in samples if not (s.get("holdout") or s.get("split") == "test")]
    if len(holdout) < OCR_MIN_HOLDOUT:
        return {
            "state": "pending_data",
            "note": f"holdout {len(holdout)} < {OCR_MIN_HOLDOUT} — PENDING_DATA, không tạo candidate",
            "holdout_size": len(holdout),
            "train_size": len(train_samples),
        }

    # 2. Setup asset root và output
    assets_root = BASE_DIR / "data" / "training" / "assets" / dataset_id
    if not assets_root.exists():
        return {
            "state": "pending_data",
            "note": "asset root không tồn tại — chưa import dataset, không inference được",
            "holdout_size": len(holdout),
            "train_size": len(train_samples),
        }
    if output_root is None:
        output_root = str(BASE_DIR / "data" / "training" / "candidates" / job_id)
    out_p = Path(output_root)
    out_p.mkdir(parents=True, exist_ok=True)
    log_path = out_p / "log.txt"

    # 3. Chọn engine EasyOCR
    try:
        from app.training import ocr_engine
        engine = ocr_engine.select_ocr_engine("easyocr", gpu=gpu)
        engine.load()
    except SchemaError as e:
        LOG.warning("[task3.ocr_trainer] EasyOCR không khả dụng: %s", e)
        return {
            "state": "unsupported",
            "note": f"EasyOCR import/run thất bại: {e}",
            "holdout_size": len(holdout),
            "train_size": len(train_samples),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "state": "unsupported",
            "note": f"engine load error: {type(e).__name__}: {e}",
            "holdout_size": len(holdout),
            "train_size": len(train_samples),
        }

    # 4. Inference trên holdout
    predictions: dict[str, str] = {}
    log_lines: list[str] = []
    start = time.time()
    for s in holdout:
        sid = s.get("target_id")
        img = _load_image_for_eval(assets_root, s)
        if img is None:
            log_lines.append(f"{sid}: SKIP no image")
            predictions[sid] = ""
            continue
        results = _run_inference(engine, img)
        text = _pick_best_text(results)
        predictions[sid] = text
        log_lines.append(f"{sid}: pred={text!r} conf={max([r.get('conf', 0.0) for r in results], default=0.0):.3f}")
    elapsed = time.time() - start

    # 5. Evaluate
    metrics = evaluator.evaluate_ocr(holdout, predictions=predictions)
    metrics["total_dataset"] = len(samples)
    metrics["holdout_size"] = len(holdout)
    metrics["train_size"] = len(train_samples)
    metrics["inference_sec"] = round(elapsed, 2)
    metrics["engine"] = "EasyOCR.baseline"
    metrics["note"] = "E5 runner: EasyOCR baseline inference trên holdout (KHÔNG training)"

    # 6. Ghi log + metrics
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    metrics_path = out_p / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    # 7. Update job
    _update_job_metrics(job_id, str(metrics_path), db_path=db_path)

    return {
        "state": "completed",
        "metrics": metrics,
        "model_path": None,  # baseline không tạo weights
        "model_sha256": "",
        "log_path": str(log_path),
        "holdout_size": len(holdout),
        "train_size": len(train_samples),
        "note": metrics["note"],
    }


def _update_job_metrics(job_id: str, metrics_path: str, *, db_path: str | None = None) -> None:
    dsn = db_path or dataset_repo.default_db_path()
    conn = dataset_repo._connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dataset_jobs SET metrics_path=? WHERE id=?",
            (metrics_path, job_id),
        )
        conn.commit()
    finally:
        conn.close()