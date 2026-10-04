"""Đóng gói ảnh camera thật (plate_review) thành dataset YOLO để fine-tune plate detector.

Nhãn lấy từ datasets/cvat_review/plate_review_reviewed.json (đã duyệt tay):
  plate     -> box nhãn 'plate'
  reject    -> không ghi gì: ảnh thành mẫu âm (biển báo đỏ, đèn hậu... model cũ hay bắt nhầm)
  uncertain -> che xám vùng đó, model không bị dạy sai theo hướng nào

Chia train/val THEO VIDEO GỐC (cùng 1 video = cùng split) để val không bị rò.
Ngoài khung hình đầy đủ còn sinh crop vuông quanh biển (256-640px) — cùng tỉ lệ
mà pipeline thấy khi quét lại vùng xe (_scan_plate_region).

    python scripts/training/build_real_plate_dataset.py
    -> datasets/real_plate_review.zip (upload làm Input trên Kaggle)
"""
import json
import random
import shutil
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'datasets' / 'cvat_review'
OUT = ROOT / 'datasets' / 'real_plate_review'
# v3, v5, v13 (+ b2_*): 66/240 biển, đủ kiểu (gần/xa, ô tô đỏ, nắng). Video
# 2026-10-01 18-33-23.mp4 không có trong plate_review nên cũng là video test sạch.
VAL_VIDEOS = ('1790578609473', '1790578808519', '1790589989047')
CROPS_PER_PLATE = 2
GRAY = (114, 114, 114)  # màu letterbox của Ultralytics


def yolo_line(box, w, h):
    x1, y1, x2, y2 = box
    return f'0 {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}'


def mask(img, box):
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    cv2.rectangle(img, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), GRAY, -1)


def write(split, name, img, plates):
    h, w = img.shape[:2]
    cv2.imwrite(str(OUT / 'images' / split / f'{name}.jpg'), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    (OUT / 'labels' / split / f'{name}.txt').write_text(''.join(yolo_line(b, w, h) + '\n' for b in plates))


def crop_around(img, box, plates, rng):
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box
    side = min(rng.randint(256, 640), w, h)
    side = max(side, int(max(x2 - x1, y2 - y1)) + 8)
    cx = rng.uniform(max(0, x2 - side), min(x1, w - side))
    cy = rng.uniform(max(0, y2 - side), min(y1, h - side))
    cx, cy = int(max(0, cx)), int(max(0, cy))
    crop = img[cy:cy + side, cx:cx + side].copy()
    keep = []
    for b in plates:
        bx1, by1, bx2, by2 = b[0] - cx, b[1] - cy, b[2] - cx, b[3] - cy
        ix1, iy1, ix2, iy2 = max(0, bx1), max(0, by1), min(side, bx2), min(side, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            continue
        inside = (ix2 - ix1) * (iy2 - iy1) / ((bx2 - bx1) * (by2 - by1))
        if inside >= .6:
            keep.append((ix1, iy1, ix2, iy2))
        else:  # biển bị cắt mất nửa: không phải dương cũng không phải âm
            mask(crop, (ix1, iy1, ix2, iy2))
    return crop, keep


def main():
    doc = json.loads((SRC / 'plate_review_reviewed.json').read_text())
    if OUT.exists():
        shutil.rmtree(OUT)
    for split in ('train', 'val'):
        (OUT / 'images' / split).mkdir(parents=True)
        (OUT / 'labels' / split).mkdir(parents=True)
    rng = random.Random(42)
    stats = {s: {'frames': 0, 'crops': 0, 'plates': 0, 'negative_frames': 0} for s in ('train', 'val')}
    for name, items in sorted(doc['images'].items()):
        split = 'val' if doc['source_video'][name].startswith(VAL_VIDEOS) else 'train'
        img = cv2.imread(str(SRC / 'plate_review' / name))
        for it in items:
            if it['status'] == 'uncertain':
                mask(img, it['box'])
        plates = [it['box'] for it in items if it['status'] == 'plate']
        stem = Path(name).stem
        write(split, stem, img, plates)
        st = stats[split]
        st['frames'] += 1
        st['plates'] += len(plates)
        st['negative_frames'] += not plates
        for i, box in enumerate(plates):
            for j in range(CROPS_PER_PLATE):
                crop, keep = crop_around(img, box, plates, rng)
                write(split, f'{stem}_c{i}{j}', crop, keep)
                st['crops'] += 1
    meta = {'name': 'real_plate_review', 'val_videos': VAL_VIDEOS, 'stats': stats}
    (OUT / 'real_plate_meta.json').write_text(json.dumps(meta, indent=1))
    zip_path = shutil.make_archive(str(OUT), 'zip', OUT)
    print(json.dumps(stats, indent=1))
    print('->', zip_path)


if __name__ == '__main__':
    main()
