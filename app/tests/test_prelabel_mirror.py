import xml.etree.ElementTree as ET

from scripts.prelabel_mirror import images_to_prelabel, merge_predictions
from scripts.prepare_mirror_dataset import split_of

XML = '''<annotations>
<image id="0" name="reviewed.jpg"><tag label="mirror_both"/><box label="mirror" source="manual" xtl="1" ytl="1" xbr="2" ybr="2"/></image>
<image id="1" name="small.jpg"><tag label="too_small"/></image>
<image id="2" name="todo.jpg"><box label="motorbike" source="manual" xtl="0" ytl="0" xbr="9" ybr="9"/>
  <box label="mirror" source="auto" xtl="5" ytl="5" xbr="6" ybr="6"/><box label="mirror" source="manual" xtl="7" ytl="7" xbr="8" ybr="8"/></image>
</annotations>'''


def _meta_for(names, want):
    """Tìm tên ảnh gốc rơi đúng vào split mong muốn (split chia theo hash)."""
    meta = {}
    for name, split in zip(names, want):
        i = 0
        while split_of(name, {name: {'source_original_image': f'src{i}'}}) != split:
            i += 1
        meta[name] = {'source_original_image': f'src{i}'}
    return meta


def test_only_unreviewed_non_exam_images_are_prelabeled():
    root = ET.fromstring(XML.replace('todo.jpg', 'todo.jpg') + '')
    root.append(ET.fromstring('<image id="3" name="exam.jpg"/>'))
    meta = _meta_for(['reviewed.jpg', 'small.jpg', 'todo.jpg', 'exam.jpg'], ['train', 'train', 'train', 'val'])
    assert images_to_prelabel(root, meta) == ['todo.jpg']


def test_merge_replaces_old_auto_boxes_and_keeps_manual_ones():
    root = ET.fromstring(XML)
    added = merge_predictions(root, {'todo.jpg': [(1.0, 2.0, 3.0, 4.0, .9), (5.0, 5.0, 6.0, 6.0, .2)]})
    image = root.find("image[@name='todo.jpg']")
    mirrors = [(b.get('source'), b.get('xtl')) for b in image.findall("box[@label='mirror']")]
    assert added == 2
    assert sorted(mirrors) == [('auto', '1.00'), ('auto', '5.00'), ('manual', '7')]
    assert image.find("box[@label='motorbike']") is not None
    assert len(root.find("image[@name='reviewed.jpg']").findall('box')) == 1
