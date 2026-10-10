"""Đo phân loại NGỒI XE / DẮT XE trên video quay thật so với đáp án gán tay.

Chạy đúng các bước của pipeline camera trước (profile full): resize về
VIDEO_WIDTH/HEIGHT -> detect người+xe có tracking trên khung DETECT_WIDTH ->
ghép người-xe (_group_by_person) -> pose batch -> SideViewRiding + temporal.
Ghi lại toàn bộ đặc trưng từng khung để dò ngưỡng offline (--dump).

    python scripts/eval_riding_video.py --video D:/Work/gate_recordings/dongbo_camera_truoc.mp4 \\
        --truth D:/Work/gate_recordings/dongbo_ground_truth.json --dump riding_dump.json
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from app.config import (DETECT_HEIGHT, DETECT_WIDTH, PERSON_CONF_THRESHOLD, PERSON_MODEL_PATH,
                        VEHICLE_CONF_THRESHOLD, VIDEO_HEIGHT, VIDEO_WIDTH)
from app.cv.detector import HelmetPlateDetector
from app.cv.pipeline import VideoPipeline
from app.cv.pose import PostureDetector, RidingTemporalState, SideViewRiding


def truth_label(truth: dict, second: int):
    for label, spans in truth.items():
        if isinstance(spans, list) and any(a <= second <= b for a, b in spans):
            return label
    return None


def run(video, step):
    person_det = HelmetPlateDetector(PERSON_MODEL_PATH, conf_threshold=PERSON_CONF_THRESHOLD,
                                     class_conf={'motorcycle': VEHICLE_CONF_THRESHOLD, 'bicycle': VEHICLE_CONF_THRESHOLD})
    grouper = VideoPipeline.__new__(VideoPipeline)
    pose, scorer, temporal = PostureDetector(), SideViewRiding(), RidingTemporalState()
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 20
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    rows, index = [], -1
    while index + 1 < total:
        index += 1
        if not cap.grab():  # transient decode hiccup: reopen at the next frame
            cap.release()
            cap = cv2.VideoCapture(video)
            cap.set(cv2.CAP_PROP_POS_FRAMES, index + 1)
            continue
        if index % step:
            continue
        ok, raw = cap.retrieve()
        if not ok:
            continue
        t = index / fps
        h, w = raw.shape[:2]
        scale = min(1., VIDEO_WIDTH / w, VIDEO_HEIGHT / h)
        frame = cv2.resize(raw, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else raw
        fh, fw = frame.shape[:2]
        ds = min(DETECT_WIDTH / fw, DETECT_HEIGHT / fh)
        small = cv2.resize(frame, (round(fw * ds), round(fh * ds)))
        dets = VideoPipeline._rescale_dets(person_det.detect_tracked(small), fw / small.shape[1], fh / small.shape[0])
        people = [d for d in dets if d.class_name == 'person']
        vehicles = [d for d in dets if d.class_name in ('motorcycle', 'bicycle')]
        groups, _ = grouper._group_by_person(people, [], [], vehicles)
        pending = []
        vlist = [[d.class_name, round(d.confidence, 3), list(d.bbox), d.track_id] for d in vehicles]
        for g in groups:
            if g['_vehicle'] is None:
                rows.append({'t': t, 'person': list(g['_person'].bbox), 'bike': None, 'state': 'NO_BIKE',
                             'vehicles': vlist, 'reasons': g['association_reasons']})
                continue
            x1, y1, x2, y2 = (int(v) for v in g['_person'].bbox)
            x1, y1, x2, y2 = max(0, x1), max(0, y1), min(fw, x2), min(fh, y2)
            crop = frame[y1:y2, x1:x2]
            if crop.shape[0] < 30 or crop.shape[1] < 30:
                rows.append({'t': t, 'person': list(g['_person'].bbox), 'bike': list(g['_vehicle'].bbox), 'state': 'TINY'})
                continue
            pending.append((g, (x1, y1), crop))
        for (g, offset, _), kps in zip(pending, pose.detect_pose_batch([c for _, _, c in pending])):
            feat = temporal.observe(g['track_id'], g['vehicle_track_id'], 0, g['_person'].bbox, g['_vehicle'].bbox, t)
            res = scorer.evaluate(kps, bike_bbox=g['_vehicle'].bbox, person_bbox=g['_person'].bbox, offset=offset,
                                  temporal_score=feat.temporal_score, motion_score=feat.motion_score)
            rows.append({'t': t, 'person': list(g['_person'].bbox), 'bike': list(g['_vehicle'].bbox),
                         'person_id': g['track_id'], 'bike_id': g['vehicle_track_id'], 'offset': list(offset),
                         'keypoints': [[round(k['x'], 1), round(k['y'], 1), round(k['confidence'], 3)] for k in kps],
                         'state': res.state, 'score': round(res.score, 3),
                         'features': {k: (None if v is None else round(v, 3)) for k, v in res.features.items()},
                         'frame_size': [fw, fh]})
    return rows


def report(rows, truth, classify=lambda r: r['state']):
    table = defaultdict(Counter)
    for r in rows:
        label = truth_label(truth, int(r['t']))
        if label in ('ride', 'walk'):
            table[label][classify(r)] += 1
    for label in ('ride', 'walk'):
        total = sum(table[label].values())
        print(f'  GT {label:5s} ({total} quan sát): ' + ', '.join(f'{k}={v}' for k, v in table[label].most_common()))
    return table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--truth', required=True)
    ap.add_argument('--step', type=int, default=2, help='xử lý 1/step khung (pipeline thật ~10-17 khung/s)')
    ap.add_argument('--dump')
    args = ap.parse_args()
    truth = json.loads(Path(args.truth).read_text(encoding='utf-8'))[Path(args.video).name]
    rows = run(args.video, args.step)
    print(f'{args.video}: {len(rows)} quan sát người')
    report(rows, truth)
    if args.dump:
        Path(args.dump).write_text(json.dumps(rows))


if __name__ == '__main__':
    main()
