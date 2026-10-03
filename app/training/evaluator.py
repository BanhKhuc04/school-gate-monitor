"""Evaluator — đo candidate trên cùng holdout + baseline + regression.

Các metric:
  - OCR exact whole-plate accuracy (% canonical match).
  - CER (character error rate).
  - Read rate / Abstain rate / Wrong-association rate.
  - Detector: precision/recall mAP (approximate by IoU 0.5).
  - Helmet: precision/recall mAP.
  - Runtime: 2 camera FPS/latency nếu adapter sẵn (PENDING runtime integration).

KHÔNG dùng raw_nonempty_reads hoặc confidence làm accuracy — plan cấm.

Quan trọng: candidate phải đo trên CÙNG holdout + cùng input. KHÔNG lấy số từ
dataset khác hay candidate khác.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.training import dataset_repo
from app.training.schemas import SchemaError


def _normalize(s: str) -> str:
    return (s or "").strip().upper()


def _cer(ref: str, hyp: str) -> float:
    """Levenshtein distance / len(ref). 0..1.0+."""
    if not ref:
        return 1.0 if hyp else 0.0
    if not hyp:
        return 1.0
    ref = ref.upper()
    hyp = hyp.upper()
    n, m = len(ref), len(hyp)
    if n == 0:
        return float(m)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        new = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            new[j] = min(dp[j] + 1, new[j - 1] + 1, dp[j - 1] + cost)
        dp = new
    return dp[m] / n


def evaluate_ocr(samples: list[dict], *, predictions: dict[str, str]) -> dict:
    """samples: holdout samples có label.target_text canonical.
    predictions: dict{target_id: prediction_text}.

    Trả về:
      total, exact_match, exact_match_pct,
      cer_avg, read_rate, abstain_rate, wrong_assoc_rate (no error mean)
    """
    total = 0
    correct = 0
    abstains = 0
    no_label = 0
    wrong_assoc = 0
    cer_sum = 0.0
    cer_count = 0
    for s in samples:
        sid = s.get("target_id")
        gt_text = (s.get("label", {}) or {}).get("target_text") or ""
        if s.get("label", {}).get("verdict") not in {"correct", "incorrect"}:
            no_label += 1
            continue
        total += 1
        pred = predictions.get(sid, "")
        if not pred:
            abstains += 1
            cer_sum += _cer(gt_text, "")
            cer_count += 1
            continue
        if _normalize(pred) == _normalize(gt_text):
            correct += 1
        else:
            cer_sum += _cer(gt_text, pred)
            cer_count += 1
            if s.get("label", {}).get("verdict") == "wrong_association":
                wrong_assoc += 1
    return {
        "total": total,
        "skipped_no_label": no_label,
        "exact_match": correct,
        "exact_match_pct": round((correct / total) * 100, 2) if total else 0.0,
        "cer_avg": round(cer_sum / cer_count, 4) if cer_count else 0.0,
        "read_rate": round(((total - abstains) / total) * 100, 2) if total else 0.0,
        "abstain_rate": round((abstains / total) * 100, 2) if total else 0.0,
        "wrong_assoc_count": wrong_assoc,
    }


def evaluate_detector(samples: list[dict], *, predictions: dict[str, list[dict]]) -> dict:
    """samples có bbox (target_id → list of expected {class_id, bbox_xyxy}).
    predictions: target_id → list of {class_id, bbox_xyxy, conf}.
    """
    tp = 0
    fp = 0
    fn = 0
    for s in samples:
        sid = s.get("target_id")
        expected = predictions.get(sid, {}).get("expected") if isinstance(predictions.get(sid), dict) else None
        predicted = predictions.get(sid) if not isinstance(predictions.get(sid), dict) else predictions[sid].get("predicted")
        if expected is None or predicted is None:
            # caller phải chuẩn bị predicted vs expected
            continue
        matched_expected = set()
        for p in predicted:
            best_iou = 0.0
            best_idx = -1
            for i, e in enumerate(expected):
                if i in matched_expected:
                    continue
                iou = _iou_xyxy(p["bbox_xyxy"], e["bbox_xyxy"])
                if iou > best_iou:
                    best_iou = iou
                    best_idx = i
            if best_iou >= 0.5 and p["class_id"] == expected[best_idx]["class_id"]:
                tp += 1
                matched_expected.add(best_idx)
            else:
                fp += 1
        fn += len(expected) - len(matched_expected)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0,
    }


def _iou_xyxy(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union else 0.0


def compare_candidates(*, baseline_metrics: dict, candidate_metrics: dict) -> dict:
    """So sánh baseline vs candidate. KHÔNG promote nếu chỉ nhớ crop vừa sửa.

    Returns dict với deltas + recommendation 'promote'/'hold'/'rollback'.
    """
    base_ocr_pct = baseline_metrics.get("exact_match_pct", 0.0)
    cand_ocr_pct = candidate_metrics.get("exact_match_pct", 0.0)
    base_cer = baseline_metrics.get("cer_avg", 1.0)
    cand_cer = candidate_metrics.get("cer_avg", 1.0)

    ocr_improved = cand_ocr_pct - base_ocr_pct
    cer_improved = base_cer - cand_cer  # lower better
    if ocr_improved > 0 and cer_improved >= 0:
        rec = "promote"
    elif ocr_improved >= -0.5 and cer_improved >= -0.005:
        rec = "hold"
    else:
        rec = "rollback"

    return {
        "ocr_exact_pct_delta": round(ocr_improved, 3),
        "cer_delta": round(cand_cer - base_cer, 4),
        "recommendation": rec,
    }


def write_metrics(path: str, payload: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_metrics(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def quality_pending(metrics: dict, *, thresholds: dict | None = None) -> tuple[bool, list[str]]:
    """Trả về (PENDING_DATA, list_reasons) theo ngưỡng plan đã chốt."""
    thresholds = thresholds or {}
    min_plates = thresholds.get("min_clear_plates", 30)
    min_viol = thresholds.get("min_violations", 50)
    min_clean = thresholds.get("min_clean", 50)
    reasons = []
    test_total = metrics.get("total", 0)
    if test_total < min_plates:
        reasons.append(f"số biển holdout {test_total} < {min_plates}")
    viol = metrics.get("violation_count")
    clean = metrics.get("clean_count")
    if viol is not None and viol < min_viol:
        reasons.append(f"số vi phạm {viol} < {min_viol}")
    if clean is not None and clean < min_clean:
        reasons.append(f"số clean {clean} < {min_clean}")
    return (bool(reasons), reasons)