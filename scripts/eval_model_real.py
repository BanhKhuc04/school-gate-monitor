"""
So sánh model biển số CŨ vs MỚI trên ảnh THẬT (data/snapshots/*.jpg) — không dùng
số liệu val của dataset (dataset ảnh biển số crop sẵn, không giống góc camera
cổng trường thật). Xem PLAN_NEXT_ROUND.md mục (a).

Dùng:
    python scripts/eval_model_real.py --new models/plate_finetune_v1_best.pt
    python scripts/eval_model_real.py --new models/plate_finetune_v1_best.pt --limit 200
"""
import argparse
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from app.config import PLATE_MODEL_PATH, PLATE_CONF_THRESHOLD, SNAPSHOTS_DIR
from app.cv.detector import HelmetPlateDetector


def eval_model(model_path: str, image_paths: list[str]) -> dict:
    detector = HelmetPlateDetector(model_path, conf_threshold=PLATE_CONF_THRESHOLD)
    hits = 0
    for path in image_paths:
        frame = cv2.imread(path)
        if frame is None:
            continue
        if detector.detect(frame):
            hits += 1
    return {"model": model_path, "total": len(image_paths), "hits": hits,
            "hit_rate": round(hits / len(image_paths), 3) if image_paths else 0.0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--new", required=True, help="Đường dẫn best.pt mới tải từ Kaggle")
    parser.add_argument("--old", default=PLATE_MODEL_PATH, help="Model cũ để so sánh (mặc định models/plate_best.pt)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số ảnh test (mặc định: toàn bộ)")
    args = parser.parse_args()

    image_paths = sorted(glob.glob(f"{SNAPSHOTS_DIR}/*.jpg"))
    if args.limit:
        image_paths = image_paths[:args.limit]
    if not image_paths:
        print(f"Không tìm thấy ảnh nào trong {SNAPSHOTS_DIR}")
        return

    print(f"Test trên {len(image_paths)} ảnh thật từ {SNAPSHOTS_DIR}\n")

    old_result = eval_model(args.old, image_paths)
    new_result = eval_model(args.new, image_paths)

    print(f"{'Model':<40} {'Detect được':>12} {'/':>2} {'Tổng':<6} {'Tỉ lệ':>8}")
    for r in (old_result, new_result):
        print(f"{r['model']:<40} {r['hits']:>12} {'/':>2} {r['total']:<6} {r['hit_rate']*100:>7.1f}%")

    if new_result["hit_rate"] > old_result["hit_rate"]:
        print("\n=> Model MỚI tốt hơn — cân nhắc thay vào models/plate_best.pt (nhớ backup bản cũ trước: "
              "cp models/plate_best.pt models/plate_best.pt.bak)")
    else:
        print("\n=> Model mới KHÔNG tốt hơn — chưa nên thay.")


if __name__ == "__main__":
    main()
