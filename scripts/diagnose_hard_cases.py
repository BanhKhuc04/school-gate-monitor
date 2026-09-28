"""
Chẩn đoán model hiện tại trên bộ ảnh "case khó" người dùng tự sưu tầm
(ảnh internet, KHÔNG dùng để train — chỉ để biết điểm yếu hiện tại).

Chạy: python scripts/diagnose_hard_cases.py [đường dẫn thư mục ảnh]
Mặc định đọc từ C:\\Users\\khucv\\Downloads\\ảnh lái xe\\
"""
import sys
import glob
import os
import cv2

from app.cv.detector import HelmetPlateDetector
from app.config import (
    HELMET_MODEL_PATH, PLATE_MODEL_PATH, PERSON_MODEL_PATH,
    HELMET_CONF_THRESHOLD, PLATE_CONF_THRESHOLD, PERSON_CONF_THRESHOLD,
)

DEFAULT_DIR = r"C:\Users\khucv\Downloads\ảnh lái xe"
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def group_riders_per_vehicle(person_dets, vehicle_dets):
    """Ước lượng nhanh số người khớp gần nhất với mỗi xe (logic giống _group_by_person)."""
    buckets = {}
    for p in person_dets:
        pcx = (p.bbox[0] + p.bbox[2]) / 2
        p_width = p.bbox[2] - p.bbox[0]
        best_dist, best_v = float("inf"), None
        for v in vehicle_dets:
            vcx = (v.bbox[0] + v.bbox[2]) / 2
            dist = abs(vcx - pcx)
            if dist < best_dist and dist <= p_width:
                best_dist, best_v = dist, v
        if best_v is not None:
            buckets.setdefault(best_v.bbox, []).append(p)
    return buckets


def main():
    img_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    paths = sorted(
        p for p in glob.glob(os.path.join(img_dir, "*"))
        if p.lower().endswith(IMG_EXTS)
    )
    print(f"Tìm thấy {len(paths)} ảnh trong {img_dir}\n")

    person_detector = HelmetPlateDetector(PERSON_MODEL_PATH, conf_threshold=PERSON_CONF_THRESHOLD)
    helmet_detector = HelmetPlateDetector(HELMET_MODEL_PATH, conf_threshold=HELMET_CONF_THRESHOLD)
    plate_detector = HelmetPlateDetector(PLATE_MODEL_PATH, conf_threshold=PLATE_CONF_THRESHOLD)

    header = f"{'Ảnh':<55} {'Người':>6} {'Xe máy':>7} {'Xe đạp':>7} {'Mũ':>4} {'Biển số':>8} {'Xe >2 người':>12}"
    print(header)
    print("-" * len(header))

    for path in paths:
        frame = cv2.imread(path)
        if frame is None:
            print(f"{os.path.basename(path):<55} (không đọc được file ảnh)")
            continue

        raw_person = person_detector.detect(frame)
        persons = [d for d in raw_person if d.class_name.lower() == "person"]
        motos = [d for d in raw_person if d.class_name.lower() == "motorcycle"]
        bikes = [d for d in raw_person if d.class_name.lower() == "bicycle"]
        helmets = helmet_detector.detect(frame)
        plates = plate_detector.detect(frame)

        buckets = group_riders_per_vehicle(persons, motos)
        overcrowded = sum(1 for riders in buckets.values() if len(riders) > 2)

        name = os.path.basename(path)
        print(f"{name:<55} {len(persons):>6} {len(motos):>7} {len(bikes):>7} "
              f"{len(helmets):>4} {len(plates):>8} {overcrowded:>12}")

    print("\nGhi chú: đây là báo cáo tham khảo (không ghi log DB, không phải feature mới).")
    print("Cột 'Xe >2 người' đếm theo logic ước lượng nearest-distance, chưa phải")
    print("logic _count_riders_per_vehicle chính thức (việc đó làm ở bước sau).")


if __name__ == "__main__":
    main()
