import json
import zipfile

from scripts.prepare_mirror_dataset import build_cvat_task, cvat_to_yolo

META = [
    {'file_name': 'a.jpg', 'motorbike_bbox_xyxy': [0, 0, 100, 100], 'source_original_image': 'frame1.jpg'},
    {'file_name': 'b.jpg', 'motorbike_bbox_xyxy': [0, 0, 100, 100], 'source_original_image': 'frame1.jpg'},
    {'file_name': 'c.jpg', 'motorbike_bbox_xyxy': [0, 0, 30, 100], 'source_original_image': 'frame2.jpg'},
    {'file_name': 'd.jpg', 'motorbike_bbox_xyxy': [0, 0, 100, 100], 'source_original_image': 'frame3.jpg'},
]


def _zip(path, images_xml):
    with zipfile.ZipFile(path, 'w') as z:
        for row in META:
            z.writestr(f"images/{row['file_name']}", b'jpg')
        z.writestr('annotations.xml', f'<annotations><version>1.1</version>{images_xml}</annotations>')


def test_cvat_task_tags_small_bikes(tmp_path):
    labels = tmp_path / 'labels.json'
    labels.write_text(json.dumps(META))
    _zip(tmp_path / 'src.zip', ''.join(
        f'<image id="{i}" name="{r["file_name"]}" width="200" height="200"/>' for i, r in enumerate(META)))
    stats = build_cvat_task(str(tmp_path / 'src.zip'), str(labels), str(tmp_path / 'task.zip'))
    assert stats == {'images': 4, 'too_small': 1}
    with zipfile.ZipFile(tmp_path / 'task.zip') as z:
        xml = z.read('annotations.xml').decode()
        assert len([n for n in z.namelist() if n.startswith('images/')]) == 4
    assert xml.count('too_small') == 2      # 1 định nghĩa label + 1 tag trên c.jpg


def test_to_yolo_keeps_source_frames_together_and_skips_unreviewed(tmp_path):
    labels = tmp_path / 'labels.json'
    labels.write_text(json.dumps(META))
    _zip(tmp_path / 'export.zip',
         '<image id="0" name="a.jpg" width="200" height="100"><tag label="mirror_both"/>'
         '<box label="mirror" xtl="10" ytl="10" xbr="30" ybr="30"/><box label="motorbike" xtl="0" ytl="0" xbr="100" ybr="100"/></image>'
         '<image id="1" name="b.jpg" width="200" height="100"><tag label="mirror_none"/></image>'
         '<image id="2" name="c.jpg" width="200" height="100"><tag label="too_small"/></image>'
         '<image id="3" name="d.jpg" width="200" height="100"/>')
    out = tmp_path / 'out'
    stats = cvat_to_yolo(str(tmp_path / 'export.zip'), str(labels), str(out))
    assert stats['train'] + stats['val'] == 2
    assert (stats['skipped'], stats['unlabeled'], stats['mirror_boxes']) == (1, 1, 1)
    a = list(out.glob('labels/*/a.txt'))[0]
    b = list(out.glob('labels/*/b.txt'))[0]
    assert a.parent == b.parent                  # cùng ảnh gốc -> cùng split
    assert a.read_text() == '0 0.100000 0.200000 0.100000 0.200000'
    assert b.read_text() == ''                   # đã duyệt: không có gương = ảnh âm
    assert 'names:\n  0: mirror' in (out / 'data.yaml').read_text()
