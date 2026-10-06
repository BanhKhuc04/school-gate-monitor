"""Gộp dữ liệu train detector mũ bảo hiểm (2 lớp: With Helmet / Without Helmet).

Nguồn:
  1. EdgeVision (CC BY 4.0, datasets/edgevision_helmet, đã đổi lớp) — ảnh công khai.
  2. datasets/cvat_review/helmet_review + helmet_review_reviewed.json — khung hình
     camera cổng trường, duyệt tay: background giữ làm nền (áp phích ATGT vẽ người
     đội mũ, đồ vật), uncertain che xám.
  3. Video camera trước 04/10 (người đầu trần suốt video): box đầu dựng từ pose
     khi thấy rõ mặt (>= 60% đầu trong khung) — mẫu "tóc đen không phải mũ".
  4. Hai video selfie đầu trần (cvat_review/selfie_bare_heads.json): đầu cúi/ngửa/
     nghiêng, lộ đỉnh tóc — model cũ gọi "có mũ" 4/54 khung. Video A (người khác) làm val.

Val chia theo VIDEO GỐC (giống build_real_plate_dataset.py) để không rò.

    python scripts/training/build_helmet_dataset.py
"""
import json
import random
import re
import shutil
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / 'datasets' / 'cvat_review'
EDGE = ROOT / 'datasets' / 'edgevision_helmet'
OUT = ROOT / 'datasets' / 'helmet_mix'
BARE_HEAD_VIDEO = Path('D:/Work/gate_recordings/dongbo_camera_truoc.mp4')
SELFIE_DIR = Path.home() / 'Downloads'  # video của selfie_bare_heads.json
# Giây có người trên xe/dắt xe trong video trên (dongbo_ground_truth.json).
BARE_HEAD_TRAIN = [(64, 123)]
BARE_HEAD_VAL = [(124, 167)]
VAL_GROUPS = {'v3', 'v5', 'v13'}  # cùng video với val của biển số
CLASSES = {'With Helmet': 0, 'Without Helmet': 1}
GRAY = (114, 114, 114)


def yolo(box, w, h, cls):
    x1, y1, x2, y2 = box
    return f'{cls} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}'


def write(split, name, img, rows):
    cv2.imwrite(str(OUT / 'images' / split / f'{name}.jpg'), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    (OUT / 'labels' / split / f'{name}.txt').write_text(''.join(r + '\n' for r in rows))


def review_frames(stats):
    doc = json.loads((REVIEW / 'helmet_review_reviewed.json').read_text())
    for name, items in sorted(doc['images'].items()):
        group = re.sub(r'^b2_', '', re.sub(r'_\d+\.jpg$', '', name))
        split = 'val_real' if group in VAL_GROUPS else 'train'
        img = cv2.imread(str(REVIEW / 'helmet_review' / name))
        h, w = img.shape[:2]
        rows = []
        for it in items:
            x1, y1, x2, y2 = (int(round(v)) for v in it['box'])
            if it['status'] == 'uncertain':
                cv2.rectangle(img, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), GRAY, -1)
            elif it['status'] in CLASSES:
                rows.append(yolo(it['box'], w, h, CLASSES[it['status']]))
                stats[split][it['status']] += 1
        write(split, 'rv_' + Path(name).stem, img, rows)
        stats[split]['images'] += 1


def head_box(kps, conf=.5):
    """Head box from nose/eyes/ears (COCO 0-4); None when too few are visible."""
    pts = [(x, y) for x, y, c in kps[:5] if c >= conf]
    if len(pts) < 3:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    width = max(max(xs) - min(xs), 1) * 1.6
    cx, cy = (max(xs) + min(xs)) / 2, sum(ys) / len(ys)
    return cx - width / 2, cy - width * .75, cx + width / 2, cy + width * .55


def bare_head_frames(stats, fps_sample=2):
    from ultralytics import YOLO
    pose = YOLO('yolo11n-pose.pt')
    cap = cv2.VideoCapture(str(BARE_HEAD_VIDEO))
    fps = cap.get(cv2.CAP_PROP_FPS) or 20
    step = max(1, round(fps / fps_sample))
    for index in range(int(cap.get(cv2.CAP_PROP_FRAME_COUNT))):
        if not cap.grab():
            break
        t = index / fps
        split = ('train' if any(a <= t <= b for a, b in BARE_HEAD_TRAIN)
                 else 'val_real' if any(a <= t <= b for a, b in BARE_HEAD_VAL) else None)
        if split is None or index % step:
            continue
        ok, frame = cap.retrieve()
        if not ok:
            continue
        h, w = frame.shape[:2]
        result = pose.predict(frame, imgsz=640, conf=.4, verbose=False)[0]
        rows = []
        for box, kps in zip(result.boxes.xyxy.tolist(), result.keypoints.data.tolist()):
            head = head_box(kps)
            # This camera always cuts the top of the head; a clearly seen face
            # still proves a bare head. Keep it when >= 60% of the head is in view.
            if head is None or min(kps[0][2], max(kps[1][2], kps[2][2])) < .6:
                continue
            if (head[3] - max(0, head[1])) < .6 * (head[3] - head[1]):
                continue
            rows.append(yolo((max(0, head[0]), max(0, head[1]), min(w, head[2]), min(h, head[3])), w, h, 1))
        if rows:
            write(split, f'bare_{index:05d}', frame, rows)
            stats[split]['images'] += 1
            stats[split]['Without Helmet'] += len(rows)


def selfie_frames(stats):
    doc = json.loads((REVIEW / 'selfie_bare_heads.json').read_text())
    for tag, video in doc['videos'].items():
        cap = cv2.VideoCapture(str(SELFIE_DIR / video['file']))
        for index, box in sorted(video['frames'].items(), key=lambda kv: int(kv[0])):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = cap.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            write(video['split'], f'selfie{tag}_{int(index):04d}', frame, [yolo(box, w, h, 1)])
            stats[video['split']]['images'] += 1
            stats[video['split']]['Without Helmet'] += 1


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    for split in ('train', 'val_real', 'val_public'):
        (OUT / 'images' / split).mkdir(parents=True)
        (OUT / 'labels' / split).mkdir(parents=True)
    stats = {s: {'images': 0, 'With Helmet': 0, 'Without Helmet': 0} for s in ('train', 'val_real', 'val_public')}
    for split, target in (('train', 'train'), ('val', 'val_public')):
        for img in sorted((EDGE / 'images' / split).glob('*.jpg')):
            shutil.copy2(img, OUT / 'images' / target / img.name)
            label = EDGE / 'labels' / split / (img.stem + '.txt')
            shutil.copy2(label, OUT / 'labels' / target / label.name)
            stats[target]['images'] += 1
            for line in label.read_text().splitlines():
                stats[target]['With Helmet' if line.startswith('0 ') else 'Without Helmet'] += 1
    review_frames(stats)
    if BARE_HEAD_VIDEO.exists():
        bare_head_frames(stats)
    selfie_frames(stats)
    for val in ('val_real', 'val_public'):
        (OUT / f'data_{val}.yaml').write_text(
            f"path: {OUT.as_posix()}\ntrain: images/train\nval: images/{val}\nnc: 2\n"
            "names: ['With Helmet', 'Without Helmet']\n")
    (OUT / 'helmet_mix_meta.json').write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == '__main__':
    random.seed(42)
    main()
