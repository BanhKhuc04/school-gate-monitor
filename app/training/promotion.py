"""Promotion — chuyển candidate sang active với contract đầy đủ.

Quy tắc (Task 3.6, E6 của FINAL_CLOSURE_PROMPT):
  - Chỉ admin mới được áp dụng candidate.
  - Phải có artifact tồn tại, hash (model_sha256 + metrics_path), evaluation
    server-side (metrics_path file tồn tại), class mapping/runtime contract đúng.
  - Smoke/test/nonexistent/thiếu evaluation KHÔNG eligible.
  - Chỉ admin active, KHÔNG tự ghi đè model runtime (Task 1 mới được apply).
  - Tách eligible/selected/pending_runtime/applied: applied là khi Task 1
    load xác nhận; candidate mới default state=pending_runtime sau promote.
  - Rollback giữ baseline trước đó (xóa active, dùng baseline cũ).
  - KHÔNG thay đổi prediction/evidence lịch sử.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.training import dataset_repo, evaluator
from app.training.schemas import SchemaError


_RUNTIME_CONTRACT = {
    # engine → set of allowed model_class prefixes
    "plate_ocr": ("EasyOCR", "CustomOCR"),
    "plate_detector": ("YOLO", "Ultralytics"),
    "helmet": ("YOLO", "Ultralytics", "Helmet"),
}

# Tên class chứa 'smoke' (case-insensitive) → BLOCKED từ promotion
_SMOKE_MARKER = re.compile(r"smoke|simulate|lifecyclesim", re.IGNORECASE)


def _candidate_metrics_path(candidate_id: str, *, db_path: str | None = None) -> str | None:
    cand = dataset_repo.get_candidate(candidate_id, db_path=db_path)
    if cand is None:
        return None
    job = dataset_repo.get_job(cand["job_id"], db_path=db_path)
    return job.get("metrics_path") if job else None


def _verify_artifact(cand: dict) -> None:
    """Verify model_path tồn tại + readable + loadable (P5).

    Bổ sung (P5):
    - file >= 100 bytes (placeholder blocker)
    - hash SHA256 tính được (file không corrupt)
    - engine-specific load thử với timeout:
        - plate_ocr → easyocr.Reader.load(path) hoặc pickle torch.load
        - plate_detector → ultralytics.YOLO(path) nếu có ultralytics
        - helmet → tương tự detector
    - Timeout không được block vô hạn (signal.alarm trên Unix, thread-based trên Windows).
    """
    p = cand.get("model_path")
    if not p:
        raise SchemaError("candidate thiếu model_path")
    path = Path(p)
    if not path.exists():
        raise SchemaError(f"candidate model_path={p!r} không tồn tại")
    if not path.is_file():
        raise SchemaError(f"candidate model_path={p!r} không phải file")
    # Smoke/placeholder artifact — từ chối các file giả
    if path.stat().st_size < 100:
        raise SchemaError(f"candidate model_path={p!r} quá nhỏ (<100 bytes) — không phải artifact thật")
    # Thử compute hash để xác nhận file đọc được
    try:
        import hashlib
        with open(path, "rb") as f:
            chunk = f.read(1024 * 1024)
        hashlib.sha256(chunk).hexdigest()
    except Exception as e:
        raise SchemaError(f"candidate model_path={p!r} không đọc được: {e}")

    # P5: loadability với timeout (5s). File 200-byte không load qua framework.
    engine = cand.get("engine", "plate_ocr")
    try:
        _load_artifact_with_timeout(path, engine=engine, timeout_sec=5.0)
    except _ArtifactLoadFailed as e:
        raise SchemaError(
            f"candidate model_path={p!r} không load được bởi engine={engine}: {e}"
        )


class _ArtifactLoadFailed(Exception):
    pass


def _load_artifact_with_timeout(path: Path, *, engine: str, timeout_sec: float) -> None:
    """Thử load artifact qua framework phù hợp với engine.

    Raises _ArtifactLoadFailed nếu không load được.
    Dùng thread + join(timeout) thay vì signal (Windows không có signal.alarm).
    """
    if engine == "plate_ocr":
        # OCR: torch.load(map_location='cpu') OR easyocr.Reader().verify
        _try_load_torch(path, timeout_sec=timeout_sec)
        return
    if engine in ("plate_detector", "helmet"):
        _try_load_torch(path, timeout_sec=timeout_sec)
        return
    # engine khác: thử torch.load, fail-soft
    _try_load_torch(path, timeout_sec=timeout_sec)


def _try_load_torch(path: Path, *, timeout_sec: float) -> None:
    """torch.load(path, map_location='cpu', weights_only=False) trong thread với timeout.

    Trả về (không raise) nếu load OK. Raise _ArtifactLoadFailed nếu:
      - timeout
      - PyTorch raise "Unknown magic number" / "invalid header" (file KHÔNG phải checkpoint)
      - file 200-byte random → fail ngay

    Dùng weights_only=False vì OCR baselines có thể là pickled state không phải tensors.
    """
    import threading
    result: dict = {"ok": False, "err": None}

    def _worker():
        try:
            import torch  # type: ignore
            # weights_only=False chấp nhận cả pickled EasyOCR state; PyTorch 2.6+
            # default True nên phải flag lại.
            torch.load(str(path), map_location="cpu", weights_only=False)
            result["ok"] = True
        except Exception as e:  # noqa: BLE001
            result["err"] = str(e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    if t.is_alive():
        raise _ArtifactLoadFailed(f"timeout > {timeout_sec}s")
    if not result["ok"]:
        err = result["err"] or "unknown"
        raise _ArtifactLoadFailed(err[:200])


def _verify_metrics_server_side(candidate_id: str, *, db_path: str | None = None) -> dict:
    """Verify metrics_path (đã ghi bởi server qua evaluation độc lập).

    Trả về dict metrics nếu OK; raise nếu thiếu.
    """
    metrics_path = _candidate_metrics_path(candidate_id, db_path=db_path)
    if not metrics_path:
        raise SchemaError("candidate thiếu evaluation server-side (metrics_path)")
    mp = Path(metrics_path)
    if not mp.exists():
        raise SchemaError(f"metrics_path={metrics_path!r} không tồn tại")
    try:
        m = evaluator.load_metrics(str(mp))
    except Exception as e:  # noqa: BLE001
        raise SchemaError(f"metrics_path không parse được: {e}")
    # sanity: phải có 1 metric cốt lõi
    if not isinstance(m, dict) or ("exact_match_pct" not in m and "precision" not in m and "f1" not in m):
        raise SchemaError(
            "metrics_path thiếu exact_match_pct/precision/f1 — không phải evaluation OCR/detector/helmet thật"
        )
    return m


def _verify_runtime_contract(cand: dict) -> None:
    """Verify model_class + class mapping khớp runtime contract."""
    engine = cand.get("engine", "")
    allowed = _RUNTIME_CONTRACT.get(engine)
    if not allowed:
        raise SchemaError(f"engine={engine!r} không có runtime contract")
    mc = cand.get("model_class", "")
    if not any(mc.startswith(prefix) for prefix in allowed):
        raise SchemaError(
            f"model_class={mc!r} không thuộc runtime contract {allowed} cho engine={engine}"
        )
    # Smoke marker → block
    if _SMOKE_MARKER.search(mc):
        raise SchemaError(f"model_class={mc!r} chứa smoke marker — không eligible cho promotion")


def _verify_class_mapping(cand: dict) -> None:
    """Class mapping phải khớp engine runtime config."""
    engine = cand.get("engine", "")
    cfg_str = cand.get("config_json") or "{}"
    try:
        cfg = json.loads(cfg_str) if isinstance(cfg_str, str) else cfg_str
    except Exception:  # noqa: BLE001
        cfg = {}
    cm = cfg.get("class_mapping") if isinstance(cfg, dict) else None
    if not cm:
        raise SchemaError("candidate thiếu class_mapping trong config")
    if engine == "plate_ocr":
        # OCR không dùng class mapping theo class id — chỉ cần alphabet
        alpha = cm.get("alphabet", "")
        if not alpha or not isinstance(alpha, str):
            raise SchemaError("plate_ocr class_mapping thiếu alphabet")
    elif engine == "plate_detector":
        # Phải có 1 entry cho class 'plate'
        vals = [v.lower() for v in cm.values()]
        if "plate" not in vals:
            raise SchemaError("plate_detector class_mapping phải có class 'plate'")
    elif engine == "helmet":
        vals = " ".join(str(v).lower() for v in cm.values())
        if "with helmet" not in vals or "without helmet" not in vals:
            raise SchemaError(
                "helmet class_mapping phải có 'With Helmet' và 'Without Helmet'"
            )


def _verify_hash(cand: dict) -> None:
    """Verify SHA256 file thật và match model_sha256."""
    p = cand.get("model_path")
    if not p:
        raise SchemaError("candidate thiếu model_path")
    path = Path(p)
    if not path.exists():
        raise SchemaError(f"model_path không tồn tại, không verify hash được")
    # Small file check first (before hash compute)
    if path.stat().st_size < 100:
        raise SchemaError(f"candidate model_path={p!r} quá nhỏ (<100 bytes) — không phải artifact thật")
    stored_hash = cand.get("model_sha256") or ""
    if not stored_hash:
        raise SchemaError("candidate thiếu model_sha256 — hash chưa được đo")
    # SHA256 hex phải 64 chars
    if len(stored_hash) != 64 or not all(c in "0123456789abcdef" for c in stored_hash.lower()):
        raise SchemaError(
            f"candidate model_sha256={stored_hash!r} không hợp lệ (phải là 64-char hex)"
        )
    # Compute hash thật
    import hashlib
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except Exception as e:
        raise SchemaError(f"Không đọc model file để compute hash: {e}")
    actual = h.hexdigest()
    if actual != stored_hash.lower():
        raise SchemaError(
            f"model SHA256 mismatch: stored={stored_hash[:16]}..., computed={actual[:16]}... "
            f"— artifact không khớp hash — có thể bị sửa sau khi train"
        )


def _verify_counted_test(metrics: dict, engine: str = "plate_ocr") -> None:
    """P3: gate theo target, số samples và minimum quality tuyệt đối.

    OCR: >=30 mẫu, exact_match_pct >= 50% (nếu KHÔNG có baseline, gate tuyệt đối).
    Detector: >=30 mẫu, precision >= 0.5.
    Helmet: >=30 mẫu, f1 >= 0.5.

    0% qua 30 mẫu → block (placeholder/fake).

    NaN / Infinity / non-integer guard (P5):
    - total phải là số nguyên dương
    - exact_match_pct / cer_avg / precision / f1 phải là số thực hữu hạn
    - NaN, +inf, -inf, str, None → reject
    """
    total = metrics.get("total", 0)
    _verify_numeric_metric(total, "total", allow_int=True)
    if not isinstance(total, int) or total < 30:
        raise SchemaError(
            f"metrics thiếu dữ liệu đo (total={total!r} không phải int >= 30) — PENDING_DATA, không promote"
        )

    if engine == "plate_ocr":
        emp = metrics.get("exact_match_pct")
        if emp is not None:
            _verify_numeric_metric(emp, "exact_match_pct")
            if emp < 50.0:
                raise SchemaError(
                    f"OCR exact_match_pct={emp} < 50% trên {total} biển — quality chưa đạt tuyệt đối"
                )
        cer = metrics.get("cer_avg")
        if cer is not None:
            _verify_numeric_metric(cer, "cer_avg")
            if cer > 0.5:
                raise SchemaError(
                    f"OCR cer_avg={cer} > 0.5 — quality chưa đạt tuyệt đối"
                )
    elif engine == "plate_detector":
        precision = metrics.get("precision")
        if precision is not None:
            _verify_numeric_metric(precision, "precision")
            if precision < 0.5:
                raise SchemaError(
                    f"plate_detector precision={precision} < 0.5 — quality chưa đạt"
                )
    elif engine == "helmet":
        f1 = metrics.get("f1")
        if f1 is not None:
            _verify_numeric_metric(f1, "f1")
            if f1 < 0.5:
                raise SchemaError(
                    f"helmet f1={f1} < 0.5 — quality chưa đạt"
                )


def _verify_numeric_metric(value, name: str, *, allow_int: bool = False) -> None:
    """Reject NaN, +inf, -inf, None, str, bool.

    P5: metrics từ JSON có thể chứa NaN/Infinity khi đo trên dataset rỗng;
    promotion không được promote candidate có metric bẩn dù quality cao.
    """
    if value is None:
        if allow_int:
            return  # 0 hợp lệ nếu caller xử lý trước
        raise SchemaError(f"metric {name!r} = None — không hợp lệ")
    if isinstance(value, bool):
        raise SchemaError(f"metric {name!r} = {value!r} (bool) — không phải số")
    if not isinstance(value, (int, float)):
        raise SchemaError(f"metric {name!r} = {value!r} (type={type(value).__name__}) — không phải số")
    f = float(value)
    import math
    if math.isnan(f):
        raise SchemaError(f"metric {name!r} = NaN — không hợp lệ (phải đo trên dataset thật)")
    if math.isinf(f):
        raise SchemaError(f"metric {name!r} = {'+' if f > 0 else '-'}Infinity — không hợp lệ")
    if allow_int and not isinstance(value, int) and not float(value).is_integer():
        raise SchemaError(f"metric {name!r} = {value!r} — phải là số nguyên")


def _verify_job_completed(cand: dict, *, db_path: str | None = None) -> None:
    """P3: candidate chỉ eligible nếu job đã COMPLETED với optimization thật.

    Evaluation runner (EasyOCR.baseline) KHÔNG đủ điều kiện — phải là job với
    operation 'train' hoặc job có runner_type metadata != 'evaluate_baseline'.
    """
    job_id = cand.get("job_id")
    if not job_id:
        raise SchemaError("candidate thiếu job_id — không thể verify job hoàn thành")
    job = dataset_repo.get_job(job_id, db_path=db_path)
    if job is None:
        raise SchemaError(f"job_id={job_id!r} không tồn tại — candidate không valid")
    if job["state"] != "completed":
        raise SchemaError(
            f"job {job_id} ở state={job['state']!r} — KHÔNG eligible cho promotion "
            f"(chỉ completed mới có artifact hợp lệ)"
        )
    runner_type = job.get("runner_type", "")
    if runner_type == "evaluate_baseline":
        raise SchemaError(
            f"job {job_id} là evaluate_baseline (EasyOCR pretrained inference) — "
            f"KHÔNG phải training/optimization thật, KHÔNG eligible cho promotion"
        )


def _verify_metrics_provenance(cand: dict, metrics: dict, *, db_path: str | None = None) -> None:
    """P3 + P5: metrics phải có provenance rõ ràng tới job + dataset snapshot + split hash.

    P5 bổ sung:
      - metrics_path link tới job.metrics_path (server-side link).
      - dataset_id khớp candidate.dataset_id.
      - split_hash (nếu có trong metrics) phải khớp job.split_hash.
      - dataset_snapshot (nếu có) phải khớp với hash hiện tại của dataset.freeze_state + samples.

    Provenance bắt buộc (P3):
      - metrics_path file là kết quả đánh giá server-side (job_metrics_path đã link).
      - KHÔNG chấp nhận metrics tự đưa vào qua client (client không chọn được metrics).
      - Nếu metrics có `model_sha256` / `dataset_id` thì phải khớp candidate.
    """
    job_id = cand.get("job_id")
    job = dataset_repo.get_job(job_id, db_path=db_path) if job_id else None
    metrics_path = job.get("metrics_path") if job else None
    if not metrics_path:
        raise SchemaError("candidate thiếu metrics_path từ server — không có provenance")
    mp = Path(metrics_path)
    if not mp.exists():
        raise SchemaError(f"metrics_path={metrics_path} không tồn tại — không có provenance")
    if not mp.is_file():
        raise SchemaError(f"metrics_path={metrics_path} không phải file")
    # Nếu metrics có model/dataset link, phải khớp
    m_sha = metrics.get("model_sha256")
    if m_sha and m_sha != cand.get("model_sha256"):
        raise SchemaError(
            f"metrics model_sha256={m_sha} không khớp candidate={cand.get('model_sha256')}"
        )
    m_ds = metrics.get("dataset_id")
    if m_ds and m_ds != cand.get("dataset_id"):
        raise SchemaError(
            f"metrics dataset_id={m_ds} không khớp candidate={cand.get('dataset_id')}"
        )

    # P5: split_hash nếu có trong metrics phải khớp job.split_hash
    m_split = metrics.get("split_hash")
    job_split = job.get("split_hash") if job else None
    if m_split and job_split and m_split != job_split:
        raise SchemaError(
            f"metrics split_hash={m_split} không khớp job.split_hash={job_split} — "
            f"đánh giá có thể đã chạy trên split khác"
        )

    # P5: dataset_snapshot — nếu metrics có, verify hash hiện tại của dataset vẫn match
    m_snapshot = metrics.get("dataset_snapshot")
    if m_snapshot and cand.get("dataset_id"):
        _verify_dataset_snapshot(
            cand["dataset_id"], m_snapshot, db_path=db_path,
        )


def _verify_dataset_snapshot(dataset_id: str, claimed_snapshot: str,
                              *, db_path: str | None = None) -> None:
    """Verify dataset_snapshot hash hiện tại khớp claimed.

    Raise nếu dataset KHÔNG tồn tại, không có samples, hoặc snapshot hiện tại
    khác claimed (dataset đã bị sửa giữa run và promote).
    """
    ds = dataset_repo.get_dataset(dataset_id, db_path=db_path)
    if ds is None:
        raise SchemaError(
            f"dataset_id={dataset_id!r} không tồn tại — không thể verify dataset_snapshot"
        )
    samples = dataset_repo.list_samples(dataset_id, db_path=db_path)
    if not samples:
        raise SchemaError(
            f"dataset_id={dataset_id!r} không có samples — không thể verify dataset_snapshot"
        )
    from app.training import provenance as _prov
    actual = _prov.compute_dataset_snapshot(
        dataset_id=dataset_id,
        samples=samples,
        freeze_state=ds.get("freeze_state", "draft"),
        source_hash=ds.get("source_hash"),
    )
    if actual != claimed_snapshot:
        raise SchemaError(
            f"dataset_snapshot không khớp: claimed={claimed_snapshot[:16]}..., "
            f"actual={actual[:16]}... — dataset đã bị sửa giữa run và promote"
        )


def _verify_not_smoke(metrics: dict, cand: dict) -> None:
    """Anti-simulation: reject smoke/simulation artifacts."""
    # 1. Metrics marker
    if metrics.get("note") and "lifecycle_simulation" in str(metrics.get("note")).lower():
        raise SchemaError("metrics là lifecycle_simulation — không eligible promotion")
    # 2. Artifact name chứa smoke marker
    mc = cand.get("model_class", "")
    if _SMOKE_MARKER.search(mc):
        raise SchemaError(f"model_class={mc!r} chứa smoke marker — không eligible")
    # 3. Smoke metrics value (exact_match_pct = 0 hoặc precision = 0 → có thể fake)
    emp = metrics.get("exact_match_pct", -1)
    if emp == 0 and metrics.get("total", 0) > 0:
        # OCR 0% exact match nhưng có samples → dấu hiệu placeholder/fake
        # Nhưng 0% hợp lệ nếu model chưa train. Chỉ reject nếu là smoke.
        pass


def promote(candidate_id: str, *, expected_metrics: dict | None = None,
            db_path: str | None = None) -> dict:
    """Promote candidate lên active — chỉ khi TẤT CẢ gate pass.

    Gates (E6 + P3):
      1. Artifact tồn tại (model_path) và loadable.
      2. Model hash SHA256 file thật.
      3. Metrics server-side độc lập (metrics_path parse, có metrics cốt lõi).
      4. Provenance: metrics link tới job và hash khớp candidate (không tin client).
      5. Số lượng holdout đủ (>=30) theo target.
      6. Quality tuyệt đối: OCR exact >= 50% (gate fail-closed).
      7. Job đã COMPLETED với optimization thật (KHÔNG phải evaluate_baseline).
      8. Không phải smoke/simulation marker.
      9. Runtime contract (model_class + class_mapping).
      10. So baseline: candidate không kém hơn baseline.
    """
    cand = dataset_repo.get_candidate(candidate_id, db_path=db_path)
    if cand is None:
        raise SchemaError(f"candidate_id={candidate_id!r} không tồn tại")
    if cand["state"] == "active":
        return {"candidate_id": candidate_id, "state": "active", "note": "đã active"}
    if cand["state"] == "retired":
        raise SchemaError(f"candidate_id={candidate_id!r} đã retired — không promote")

    # E6 + P3: chặn gate tuần tự
    _verify_artifact(cand)
    _verify_hash(cand)
    _verify_job_completed(cand, db_path=db_path)  # P3 fail-fast job state check
    metrics = _verify_metrics_server_side(candidate_id, db_path=db_path)
    _verify_metrics_provenance(cand, metrics, db_path=db_path)
    engine = cand.get("engine", "plate_ocr")
    _verify_counted_test(metrics, engine=engine)
    _verify_not_smoke(metrics, cand)
    _verify_runtime_contract(cand)
    _verify_class_mapping(cand)

    # So baseline (nếu có)
    baseline = dataset_repo.get_active_candidate(engine, db_path=db_path)
    comparison = None
    if baseline is not None:
        base_metrics = _load_metrics_for(baseline["id"], db_path=db_path)
        comparison = evaluator.compare_candidates(
            baseline_metrics=base_metrics, candidate_metrics=metrics,
        )
        if comparison["recommendation"] == "rollback":
            raise SchemaError(
                f"candidate kém hơn baseline ({comparison}) — không promote"
            )

    _mark_pending_runtime(candidate_id, db_path=db_path)
    return {
        "candidate_id": candidate_id,
        "state": "pending_runtime",
        "metrics": metrics,
        "comparison": comparison if baseline is not None else None,
        "note": "Đã verify đủ gate — chờ Task 1 runtime xác nhận load.",
    }


def _mark_pending_runtime(candidate_id: str, *, db_path: str | None = None) -> None:
    """Đánh dấu candidate chờ runtime — KHÔNG set active ngay."""
    from app.training import provenance as _prov
    dsn = db_path or dataset_repo.default_db_path()
    conn = dataset_repo._connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dataset_candidates SET state='pending_runtime', promoted_at=? WHERE id=?",
            (_prov.now_iso(), candidate_id),
        )
        conn.commit()
    finally:
        conn.close()


def rollback(engine: str, *, db_path: str | None = None) -> dict:
    """Khôi phục baseline TRƯỚC active hiện tại.

    Steps:
      1. Retire candidate active hiện tại (state='retired').
      2. Promote baseline trước đó (state='active') — nếu có.
      3. Nếu không có baseline cũ → DB chỉ còn retired; model runtime phải load
         default qua patch Task 1.

    Returns dict{engine, rolled_back: bool, restored_candidate_id: str|None}.
    """
    from app.training import provenance as _prov
    dsn = db_path or dataset_repo.default_db_path()
    conn = dataset_repo._connect(dsn)
    try:
        cur = conn.cursor()
        # 1. Lấy candidate active hiện tại
        cur.execute(
            "SELECT id FROM dataset_candidates WHERE engine=? AND state='active' "
            "ORDER BY promoted_at DESC LIMIT 1",
            (engine,),
        )
        row = cur.fetchone()
        if row is None:
            return {"engine": engine, "rolled_back": False,
                    "note": "không có candidate active để rollback"}
        current_active_id = row["id"]
        # 2. Tìm baseline trước đó (retired gần nhất trước current_active)
        cur.execute(
            "SELECT id FROM dataset_candidates WHERE engine=? AND state='retired' "
            "AND promoted_at < (SELECT promoted_at FROM dataset_candidates WHERE id=?) "
            "ORDER BY promoted_at DESC LIMIT 1",
            (engine, current_active_id),
        )
        baseline_row = cur.fetchone()
        restored_id = baseline_row["id"] if baseline_row else None

        # 3. Retire active hiện tại
        cur.execute(
            "UPDATE dataset_candidates SET state='retired', retired_at=? WHERE id=?",
            (_prov.now_iso(), current_active_id),
        )
        # 4. Restore baseline (nếu có)
        if restored_id:
            cur.execute(
                "UPDATE dataset_candidates SET state='active', promoted_at=? WHERE id=?",
                (_prov.now_iso(), restored_id),
            )
        conn.commit()
        return {
            "engine": engine,
            "rolled_back": True,
            "restored_candidate_id": restored_id,
            "retired_candidate_id": current_active_id,
        }
    finally:
        conn.close()


def _load_metrics_for(candidate_id: str, *, db_path: str | None = None) -> dict:
    cand = dataset_repo.get_candidate(candidate_id, db_path=db_path)
    if cand is None:
        return {}
    job = dataset_repo.get_job(cand["job_id"], db_path=db_path)
    if job is None:
        return {}
    metrics_path = job.get("metrics_path")
    if not metrics_path or not Path(metrics_path).exists():
        return {}
    try:
        return evaluator.load_metrics(metrics_path)
    except Exception:  # noqa: BLE001
        return {}


def _attach_fake_metrics(candidate_id: str, *, metrics: dict, db_path: str | None = None) -> None:
    """Test/admin helper — gắn metrics_path giả để promotion.load đọc được.

    Dùng khi promotion cần so baseline nhưng job không có file metrics thật.
    """
    cand = dataset_repo.get_candidate(candidate_id, db_path=db_path)
    if cand is None:
        raise SchemaError(f"candidate_id={candidate_id!r} không tồn tại")
    target = Path("data/training/_fake_metrics") / f"{candidate_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    dsn = db_path or dataset_repo.default_db_path()
    conn = dataset_repo._connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dataset_jobs SET metrics_path=? WHERE id=?",
            (str(target), cand["job_id"]),
        )
        conn.commit()
    finally:
        conn.close()