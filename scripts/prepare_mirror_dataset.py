"""
Chuẩn bị dữ liệu gương chiếu hậu (Phần B, docs/PLAN_GUONG_VA_NHIEU_NGUOI_VAO_RA.md).

Bước 1: tạo task CVAT để gán nhãn gương từ bộ VN_street_motorbike_300
    python scripts/prepare_mirror_dataset.py cvat-task \
        --zip VN_street_motorbike_300_CVAT_1.1.zip \
        --labels VN_street_motorbike_300_image_labels.json \
        --out datasets/vn_mirror/vn_mirror_cvat_task.zip

    -> Import zip vào CVAT (Create task -> upload ảnh; Actions -> Upload
       annotations -> "CVAT 1.1"). Trong CVAT:
       * Vẽ box `mirror` quanh MẶT GƯƠNG (không vẽ cả cần gương).
       * Gắn đúng 1 tag trạng thái cho mỗi ảnh: mirror_both, mirror_only_left,
         mirror_only_right, mirror_none, mirror_occluded. Trái/phải theo NGƯỜI
         LÁI: ảnh chụp phía trước xe thì gương trái người lái nằm bên PHẢI ảnh.
       * Ảnh xe quá nhỏ đã được gắn sẵn tag `too_small` — bỏ qua, không vẽ.

Bước 2: sau khi gán nhãn xong, export "CVAT for images 1.1" rồi chuyển sang YOLO
    python scripts/prepare_mirror_dataset.py to-yolo \
        --cvat exported_cvat.zip \
        --labels VN_street_motorbike_300_image_labels.json \
        --out datasets/vn_mirror

    -> datasets/vn_mirror/{images,labels}/{train,val} + data.yaml (1 lớp: mirror).
       Chia train/val theo ẢNH GỐC (source_original_image): 2 crop cắt từ cùng
       1 khung hình luôn nằm cùng 1 phía, tránh "học thuộc" làm điểm val đẹp giả.

Nguồn: Kaggle "Transportation in Ho Chi Minh City" (khoakait), giấy phép CC BY 4.0
— phải ghi nguồn khi dùng/công bố model.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

MIN_BIKE_WIDTH_PX = 60
STATE_TAGS = ['mirror_both', 'mirror_only_left', 'mirror_only_right', 'mirror_none', 'mirror_occluded']
SKIP_TAGS = {'too_small'}
VAL_PERCENT = 15


def _load_meta(labels_path: str) -> dict:
    return {row['file_name']: row for row in json.loads(Path(labels_path).read_text(encoding='utf-8'))}


def _labels_xml(parent: ET.Element, labels: list[tuple[str, str]]) -> None:
    node = ET.SubElement(parent, 'labels')
    for name, kind in labels:
        label = ET.SubElement(node, 'label')
        ET.SubElement(label, 'name').text = name
        ET.SubElement(label, 'type').text = kind
        ET.SubElement(label, 'attributes')


def build_cvat_task(src_zip: str, labels_path: str, out_zip: str) -> dict:
    meta = _load_meta(labels_path)
    with zipfile.ZipFile(src_zip) as zin:
        source = ET.fromstring(zin.read('annotations.xml'))
        root = ET.Element('annotations')
        ET.SubElement(root, 'version').text = '1.1'
        task = ET.SubElement(ET.SubElement(root, 'meta'), 'task')
        ET.SubElement(task, 'name').text = 'VN_mirror_labeling'
        _labels_xml(task, [('motorbike', 'rectangle'), ('mirror', 'rectangle')]
                    + [(t, 'tag') for t in STATE_TAGS + sorted(SKIP_TAGS)]
                    + [('front_or_front_oblique', 'tag'), ('side_or_side_oblique', 'tag'),
                       ('rear_or_rear_oblique', 'tag')])
        stats = {'images': 0, 'too_small': 0}
        for image in source.iter('image'):
            out = ET.SubElement(root, 'image', dict(image.attrib))
            for child in image:
                out.append(child)
            name = Path(image.get('name')).name
            x1, _, x2, _ = meta.get(name, {}).get('motorbike_bbox_xyxy', (0, 0, 1e9, 0))
            if x2 - x1 < MIN_BIKE_WIDTH_PX:
                ET.SubElement(out, 'tag', {'label': 'too_small', 'source': 'auto'})
                stats['too_small'] += 1
            stats['images'] += 1
        Path(out_zip).parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.namelist():
                if item.startswith('images/') and not item.endswith('/'):
                    zout.writestr(item, zin.read(item))
            buf = io.BytesIO()
            ET.ElementTree(root).write(buf, encoding='utf-8', xml_declaration=True)
            zout.writestr('annotations.xml', buf.getvalue())
    return stats


def _split(group_key: str) -> str:
    digest = int(hashlib.sha1(group_key.encode('utf-8')).hexdigest(), 16)
    return 'val' if digest % 100 < VAL_PERCENT else 'train'


def cvat_to_yolo(cvat_zip: str, labels_path: str, out_dir: str) -> dict:
    meta = _load_meta(labels_path)
    out = Path(out_dir)
    stats = {'train': 0, 'val': 0, 'skipped': 0, 'mirror_boxes': 0, 'unlabeled': 0}
    with zipfile.ZipFile(cvat_zip) as zin:
        names = {Path(n).name: n for n in zin.namelist() if not n.endswith('/')}
        root = ET.fromstring(zin.read('annotations.xml'))
        for image in root.iter('image'):
            name = Path(image.get('name')).name
            tags = {t.get('label') for t in image.findall('tag')}
            if tags & SKIP_TAGS:
                stats['skipped'] += 1
                continue
            if not tags & set(STATE_TAGS):
                # Chưa gán trạng thái = chưa duyệt -> không đưa vào train
                # (ảnh không box sẽ bị hiểu nhầm là "chắc chắn không có gương").
                stats['unlabeled'] += 1
                continue
            w, h = float(image.get('width')), float(image.get('height'))
            lines = []
            for box in image.findall('box'):
                if box.get('label') != 'mirror':
                    continue
                x1, y1, x2, y2 = (float(box.get(k)) for k in ('xtl', 'ytl', 'xbr', 'ybr'))
                lines.append(f'0 {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} '
                             f'{(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}')
            split = _split(meta.get(name, {}).get('source_original_image', name))
            (out / 'images' / split).mkdir(parents=True, exist_ok=True)
            (out / 'labels' / split).mkdir(parents=True, exist_ok=True)
            (out / 'images' / split / name).write_bytes(zin.read(names[name]))
            (out / 'labels' / split / (Path(name).stem + '.txt')).write_text('\n'.join(lines))
            stats[split] += 1
            stats['mirror_boxes'] += len(lines)
    (out / 'data.yaml').write_text(
        f'path: {out.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: mirror\n',
        encoding='utf-8')
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    task = sub.add_parser('cvat-task')
    task.add_argument('--zip', required=True)
    task.add_argument('--labels', required=True)
    task.add_argument('--out', default='datasets/vn_mirror/vn_mirror_cvat_task.zip')
    yolo = sub.add_parser('to-yolo')
    yolo.add_argument('--cvat', required=True)
    yolo.add_argument('--labels', required=True)
    yolo.add_argument('--out', default='datasets/vn_mirror')
    args = parser.parse_args()
    if args.cmd == 'cvat-task':
        print(build_cvat_task(args.zip, args.labels, args.out))
    else:
        print(cvat_to_yolo(args.cvat, args.labels, args.out))


if __name__ == '__main__':
    main()
