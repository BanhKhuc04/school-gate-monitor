"""Train-only augmentation — KHÔNG sinh target mới từ ảnh mờ / đoán format.

Quy tắc:
  - Augmentation chỉ áp dụng lên ảnh training (split=train), không bao giờ lên
    val/test (giữ evaluation trên ảnh gốc).
  - Mỗi augmented sample phải đi kèm label gốc — KHÔNG tự ý gán chuỗi biển từ
    crop mất chi tiết.
  - Augmentation không đổi bbox normalized theo transform affine (nếu dùng).
"""
from __future__ import annotations

import random
from typing import Any


def is_train_only(sample: dict) -> bool:
    return sample.get("split") == "train" or sample.get("split") is None


def jitter_quality(sample: dict, *, rng: random.Random | None = None) -> list[dict]:
    """Sinh thêm các bản blur/contrast của cùng target — KHÔNG đổi label.

    Trả về list các bản sao (mỗi bản có augmentation_provenance).
    Caller tự quyết định có ghi lại metadata augmentation (vì không có ảnh thật
    để tạo pixel mới — chỉ sinh descriptor).

    Đây là descriptor-only: caller dùng engine thật (EasyOCR/ultralytics) để áp
    augment khi train. Augmentation thực tế (cv2/PIL) được thực hiện trong trainer
    của từng engine.
    """
    rng = rng or random.Random()
    if not is_train_only(sample):
        return [sample]  # không augment val/test
    label = sample.get("label", {})
    base = {
        **sample,
        "augmentation_provenance": {
            "parent_target_id": sample.get("target_id"),
            "transforms": [],
        },
    }
    out = [sample]
    # Descriptor các phép biến đổi hợp lệ. Caller sẽ áp dụng khi train.
    candidates = [
        ("blur_light", {"kernel": 3, "sigma": 0.6}),
        ("blur_medium", {"kernel": 5, "sigma": 1.0}),
        ("contrast_low", {"alpha": 0.7, "beta": 0}),
        ("contrast_high", {"alpha": 1.3, "beta": 8}),
        ("noise_low", {"stddev": 6.0}),
        ("perspective_small", {"max_warp_frac": 0.04}),
    ]
    rng.shuffle(candidates)
    for name, params in candidates[:2]:  # tối đa 2 phiên bản augment / sample
        new_target_id = f"{sample.get('target_id', 'smp')}__{name}"
        out.append({
            **base,
            "target_id": new_target_id,
            "is_augmented": True,
            "augmentation_provenance": {
                "parent_target_id": sample.get("target_id"),
                "transforms": [{"name": name, **params}],
            },
            "label": dict(label),  # KHÔNG đổi label
        })
    return out


def validate_no_fake_target(sample: dict) -> None:
    """Kiểm tra không có target được sinh từ ảnh mờ/đoán — chỉ đảm bảo
    augmentation_provenance trỏ về target gốc có label người duyệt.
    """
    if sample.get("is_augmented"):
        prov = sample.get("augmentation_provenance", {})
        if not prov.get("parent_target_id"):
            raise ValueError("augmented sample thiếu parent_target_id")
        if sample.get("label", {}).get("verdict") not in {"correct", "incorrect"}:
            raise ValueError("augmented sample không có human-verified verdict")