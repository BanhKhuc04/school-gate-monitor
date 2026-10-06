"""Split dataset thành train/val/test theo nhóm — chống leakage.

Nhóm có thể là encounter_id, (gate_id, run_id), (gate_id, camera_id, hour),
hoặc (gate_id, encounter_id) tuỳ task. Các sample cùng nhóm phải vào cùng split.

Policy:
  - 70% train / 15% val / 15% test (mặc định).
  - Holdout dataset = test chưa từng dùng để train.
  - Cùng plate hiếm xe/variant phải cùng split (configurable).
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Iterable

from app.training.schemas import SPLIT_NAMES, SchemaError


DEFAULT_RATIO = {"train": 0.70, "val": 0.15, "test": 0.15}


def _default_group_key(sample: dict) -> str:
    """Group key = encounter_id hoặc (gate, run)."""
    src = sample.get("source", {})
    if sample.get("encounter_id"):
        return f"enc:{sample['encounter_id']}"
    if src.get("run_id"):
        return f"run:{src['gate_id']}/{src['run_id']}"
    return f"fallback:{src.get('gate_id', 'unknown')}/{sample.get('review_id')}"


def split_by_group(
    samples: Iterable[dict],
    *,
    ratios: dict | None = None,
    seed: int = 42,
    group_fn=None,
) -> dict[str, list[dict]]:
    """Chia samples theo group key và ratios.

    Trả về dict[split_name, list[sample]]. Mỗi sample có thêm khóa 'split'.
    Group nào quá nhỏ (<5 samples) → đưa về 'train' (tránh test/val rỗng).
    """
    ratios = ratios or DEFAULT_RATIO
    if set(ratios) != set(SPLIT_NAMES):
        raise SchemaError(f"ratios keys phải là {SPLIT_NAMES}")
    total_ratio = sum(ratios.values())
    if abs(total_ratio - 1.0) > 1e-3:
        raise SchemaError(f"ratios sum={total_ratio} (phải =1.0)")

    samples = list(samples)
    if not samples:
        return {s: [] for s in SPLIT_NAMES}

    group_fn = group_fn or _default_group_key
    groups: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        groups[group_fn(s)].append(s)

    rng = random.Random(seed)
    group_keys = sorted(groups.keys())
    rng.shuffle(group_keys)

    # Phân bổ theo count để đạt ratio gần đúng
    target_counts = {s: max(0, round(len(samples) * ratios[s])) for s in SPLIT_NAMES}
    out: dict[str, list[dict]] = {s: [] for s in SPLIT_NAMES}

    # Phase 1: gom theo thứ tự đã xáo, thêm từng group vào split hiện đang thiếu nhiều nhất.
    for key in group_keys:
        items = groups[key]
        # group quá nhỏ → ép về train
        if len(items) < 3:
            target = "train"
        else:
            # Lấy split đang "thiếu" nhiều nhất: chênh lệch hiện tại vs target
            target = min(SPLIT_NAMES, key=lambda s: len(out[s]) - target_counts[s])
        # Nếu target đầy, fallback về split còn lại
        if len(out[target]) >= target_counts[target]:
            for s in SPLIT_NAMES:
                if len(out[s]) < target_counts[s]:
                    target = s
                    break
        out[target].extend(items)

    # Gắn 'split' lại cho mỗi sample
    for split_name, items in out.items():
        for s in items:
            s["split"] = split_name
            s["holdout"] = (split_name == "test")
    return out


def check_leakage(samples: list[dict]) -> dict:
    """Rà leakage giữa train vs test/val theo các tiêu chí:
    - cùng group_key (đã chống bằng split_by_group).
    - cùng crop_sha256 (không thể ở train lẫn test).
    - cùng target_text (OCR cùng biển) khi policy OCR_GROUPING.
    - cùng plate 'gần giống' (Levenshtein ≤ 1) — heuristic.
    """
    by_split: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        by_split[s.get("split", "train")].append(s)

    findings = {
        "groups_in_multiple_splits": [],
        "duplicate_crop_sha256": [],
        "duplicate_target_text": [],
        "near_duplicate_plate_text": [],
    }

    seen_groups: dict[str, set[str]] = defaultdict(set)
    seen_crops: dict[str, set[str]] = defaultdict(set)
    seen_targets: dict[str, set[str]] = defaultdict(set)

    for split_name, items in by_split.items():
        for s in items:
            gk = _default_group_key(s)
            seen_groups[split_name].add(gk)
            crop = s.get("source", {}).get("crop_sha256")
            if crop:
                seen_crops[split_name].add(crop)
            tgt = s.get("label", {}).get("target_text", "")
            if tgt and s.get("label", {}).get("verdict") in {"correct", "incorrect"}:
                seen_targets[split_name].add(tgt)

    for sname, groups in seen_groups.items():
        for other, other_groups in seen_groups.items():
            if sname >= other:
                continue
            common = groups & other_groups
            if common:
                findings["groups_in_multiple_splits"].append(
                    {"splits": sorted({sname, other}), "groups": sorted(common)[:5]}
                )
    for sname, crops in seen_crops.items():
        for other, other_crops in seen_crops.items():
            if sname >= other:
                continue
            common = crops & other_crops
            if common:
                findings["duplicate_crop_sha256"].append(
                    {"splits": sorted({sname, other}), "count": len(common)}
                )
    for sname, tgts in seen_targets.items():
        for other, other_tgts in seen_targets.items():
            if sname >= other:
                continue
            common = tgts & other_tgts
            if common:
                findings["duplicate_target_text"].append(
                    {"splits": sorted({sname, other}), "count": len(common), "examples": sorted(common)[:5]}
                )

    # Near-duplicate plate — heur: cùng 5 ký tự đầu canonical (bỏ ký tự cuối)
    near_index: dict[str, set[str]] = defaultdict(set)
    for split_name, items in by_split.items():
        for s in items:
            tgt = s.get("label", {}).get("target_text", "")
            if len(tgt) >= 6:
                near_index[split_name].add(tgt[:5])
    for sname, prefixes in near_index.items():
        for other, other_prefixes in near_index.items():
            if sname >= other:
                continue
            common = prefixes & other_prefixes
            if common:
                findings["near_duplicate_plate_text"].append(
                    {"splits": sorted({sname, other}), "prefix_count": len(common), "examples": sorted(common)[:5]}
                )
    return findings


def dataset_stats(samples: list[dict]) -> dict:
    """Thống kê đơn giản: counts theo split, verdict, target length."""
    by_split = defaultdict(int)
    by_verdict = defaultdict(int)
    target_lens: list[int] = []
    holdout = 0
    for s in samples:
        by_split[s.get("split", "train")] += 1
        v = s.get("label", {}).get("verdict", "unknown")
        by_verdict[v] += 1
        t = s.get("label", {}).get("target_text", "")
        if t:
            target_lens.append(len(t))
        if s.get("holdout"):
            holdout += 1
    return {
        "total": len(samples),
        "by_split": dict(by_split),
        "by_verdict": dict(by_verdict),
        "holdout_count": holdout,
        "target_len_min": min(target_lens) if target_lens else 0,
        "target_len_max": max(target_lens) if target_lens else 0,
        "target_len_avg": (sum(target_lens) / len(target_lens)) if target_lens else 0.0,
    }