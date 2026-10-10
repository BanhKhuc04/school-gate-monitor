"""Đo ảnh hưởng lề crop biển số tới OCR trên video thật có biển đã biết.

Làm đúng như camera sau (ocr_only): resize về VIDEO_WIDTH/HEIGHT -> detect biển
trên khung DETECT_WIDTH -> quy đổi box về ảnh GỐC -> cắt (thêm lề) -> OCR.

    python scripts/eval_plate_crop.py --video D:/Work/gate_recordings/dongbo_camera_sau.mp4 --plate 89F123792
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from app.config import DETECT_HEIGHT, DETECT_WIDTH, PLATE_CONF_THRESHOLD, PLATE_MODEL_PATH, VIDEO_HEIGHT, VIDEO_WIDTH
from app.cv.best_plate import make_candidate, resolve_plate
from app.cv.detector import HelmetPlateDetector
from app.cv.ocr import normalize_plate, read_plate_detailed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--plate', required=True, help='biển thật, viết liền không dấu, vd 89F123792')
    ap.add_argument('--pads', default='0,0.05,0.1,0.15,0.2')
    ap.add_argument('--step', type=int, default=2)
    ap.add_argument('--model', default=PLATE_MODEL_PATH)
    ap.add_argument('--detect-width', type=int, default=DETECT_WIDTH, help='kích thước detect (imgsz)')
    ap.add_argument('--min-conf', default='0.70', help='ngưỡng tin cậy OCR, nhiều giá trị cách nhau dấu phẩy')
    args = ap.parse_args()
    import app.cv.detector as detector_module
    detector_module.DETECT_WIDTH = args.detect_width
    pads = [float(p) for p in args.pads.split(',')]
    thresholds = [float(t) for t in args.min_conf.split(',')]
    detector = HelmetPlateDetector(args.model, conf_threshold=PLATE_CONF_THRESHOLD)
    cap = cv2.VideoCapture(args.video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    stats = {p: Counter() for p in pads}
    for index in range(total):
        if not cap.grab():
            cap.release()
            cap = cv2.VideoCapture(args.video)
            cap.set(cv2.CAP_PROP_POS_FRAMES, index + 1)
            continue
        if index % args.step:
            continue
        ok, raw = cap.retrieve()
        if not ok:
            continue
        h, w = raw.shape[:2]
        scale = min(1., VIDEO_WIDTH / w, VIDEO_HEIGHT / h)
        frame = cv2.resize(raw, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        fh, fw = frame.shape[:2]
        ds = min(1., args.detect_width / fw, args.detect_width * DETECT_HEIGHT / DETECT_WIDTH / fh)
        small = cv2.resize(frame, (round(fw * ds), round(fh * ds)))
        for det in detector.detect_tracked(small):
            sx, sy = w / small.shape[1], h / small.shape[0]
            x1, y1, x2, y2 = det.bbox[0] * sx, det.bbox[1] * sy, det.bbox[2] * sx, det.bbox[3] * sy
            for pad in pads:
                px, py = (x2 - x1) * pad, (y2 - y1) * pad
                cand = make_candidate(raw, (x1 - px, y1 - py, x2 + px, y2 + py), det.confidence, index, 0)
                if cand is None:
                    continue
                raw_read = read_plate_detailed(cand.crop)
                text = normalize_plate(raw_read.get('full', ''))
                s = stats[pad]
                s['boxes'] += 1
                s['exact_any'] += text == args.plate
                for mc in thresholds:
                    confident = resolve_plate(raw_read, mc).text
                    s[f'confident@{mc}'] += bool(confident)
                    s[f'right@{mc}'] += confident == args.plate
                    s[f'wrong@{mc}'] += bool(confident) and confident != args.plate
    for pad in pads:
        s = stats[pad]
        n = max(1, s['boxes'])
        print(f"pad {pad:4.2f}: boxes={s['boxes']:4d} đọc đúng (thô)={s['exact_any']/n:6.1%}")
        for mc in thresholds:
            print(f"   ngưỡng {mc:.2f}: chắc chắn&đúng={s[f'right@{mc}']:4d}  chắc chắn&SAI={s[f'wrong@{mc}']:3d}")

if __name__ == '__main__':
    main()
