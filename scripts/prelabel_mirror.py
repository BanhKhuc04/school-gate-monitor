"""
Gán NHÁP nhãn gương bằng model vừa train, để nạp ngược vào CVAT rồi duyệt/sửa.

    python scripts/prelabel_mirror.py --model best.pt \
        --cvat export_cvat11.zip --images 1_anh_xe_may.zip \
        --labels VN_street_motorbike_300_image_labels.json \
        --out prelabel_cvat11.zip

--cvat là file export MỚI NHẤT từ CVAT ("CVAT for images 1.1"). CVAT "Upload
annotations" GHI ĐÈ toàn bộ nhãn của task, nên file đầu ra giữ nguyên MỌI nhãn
đã có và chỉ THÊM box gương nháp vào ảnh:
  - chưa gắn tag trạng thái (chưa duyệt),
  - không phải ảnh `too_small`,
  - KHÔNG thuộc đề thi (tập val) — đề thi luôn gán tay 100%, nếu không điểm
    model sẽ đẹp giả vì chấm trên chính nhãn do nó tự sinh.
Ngưỡng --conf để thấp (mặc định 0.15): xóa box thừa nhanh hơn vẽ box bị sót.
"""
from __future__ import annotations

import argparse
import io
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_mirror_dataset import SKIP_TAGS, STATE_TAGS, Source, _load_meta, split_of  # noqa: E402


def images_to_prelabel(root: ET.Element, meta: dict) -> list[str]:
    out = []
    for image in root.iter('image'):
        name = Path(image.get('name')).name
        tags = {t.get('label') for t in image.findall('tag')}
        if tags & (SKIP_TAGS | set(STATE_TAGS)) or split_of(name, meta) == 'val':
            continue
        out.append(name)
    return out


def merge_predictions(root: ET.Element, predictions: dict) -> int:
    """predictions: {tên ảnh: [(x1, y1, x2, y2, conf), ...]}. Xóa box gương
    nháp cũ (source="auto") của ảnh đó rồi thêm box mới. Trả số box đã thêm."""
    added = 0
    for image in root.iter('image'):
        boxes = predictions.get(Path(image.get('name')).name)
        if boxes is None:
            continue
        for old in [b for b in image.findall('box') if b.get('label') == 'mirror' and b.get('source') == 'auto']:
            image.remove(old)
        for x1, y1, x2, y2, _conf in boxes:
            ET.SubElement(image, 'box', {
                'label': 'mirror', 'source': 'auto', 'occluded': '0', 'z_order': '0',
                'xtl': f'{x1:.2f}', 'ytl': f'{y1:.2f}', 'xbr': f'{x2:.2f}', 'ybr': f'{y2:.2f}'})
            added += 1
    return added


def predict(model_path: str, pictures: Source, names: list[str], conf: float) -> dict:
    import cv2
    import numpy as np
    from ultralytics import YOLO
    model = YOLO(model_path)
    out = {}
    for name in names:
        frame = cv2.imdecode(np.frombuffer(pictures.read(name), np.uint8), cv2.IMREAD_COLOR)
        result = model.predict(frame, conf=conf, imgsz=320, verbose=False)[0]
        out[name] = [(*map(float, b.xyxy[0].tolist()), float(b.conf[0])) for b in result.boxes]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--model', required=True)
    parser.add_argument('--cvat', required=True, help='export CVAT 1.1 mới nhất')
    parser.add_argument('--images', required=True, help='zip/thư mục ảnh (1_anh_xe_may.zip)')
    parser.add_argument('--labels', required=True, help='VN_street_motorbike_300_image_labels.json')
    parser.add_argument('--out', default='prelabel_cvat11.zip')
    parser.add_argument('--conf', type=float, default=0.15)
    args = parser.parse_args()

    root = ET.fromstring(Source(args.cvat).read('annotations.xml'))
    names = images_to_prelabel(root, _load_meta(args.labels))
    added = merge_predictions(root, predict(args.model, Source(args.images), names, args.conf))
    buf = io.BytesIO()
    ET.ElementTree(root).write(buf, encoding='utf-8', xml_declaration=True)
    with zipfile.ZipFile(args.out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('annotations.xml', buf.getvalue())
    print({'images_prelabeled': len(names), 'mirror_boxes_added': added, 'out': args.out})


if __name__ == '__main__':
    main()
