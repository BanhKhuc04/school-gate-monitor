"""Offline character training must not leak augmented originals across splits."""
import zipfile

import cv2
import numpy as np
import pytest

from scripts.prepare_plate_char_dataset import parse_labels, source_group, prepare
from scripts.plate_char_tools import decode_characters


def test_character_confirmation_never_invents_a_missing_series_letter():
    from scripts.plate_char_tools import confirmed_character_plate
    assert confirmed_character_plate({'full':'59131489','confidence':.99})==''
    assert confirmed_character_plate({'full':'89F123792','confidence':.85})=='89F123792'
    assert confirmed_character_plate({'full':'89F123792','confidence':.65})==''


def test_real_ultralytics_ap_on_numpy_without_trapz(monkeypatch):
    from scripts.train_plate_char import configure_numpy_compatibility
    from ultralytics.utils.metrics import compute_ap
    if not hasattr(np,'trapezoid'):
        # NumPy 1.26 in CI: expose the equivalent current API to simulate
        # the removed alias without changing dependency versions.
        monkeypatch.setattr(np,'trapezoid',np.trapz,raising=False)
    monkeypatch.delattr(np,'trapz',raising=False)
    # Install only inside this training process; pytest restores the alias.
    monkeypatch.setattr(np,'trapz',None,raising=False)
    monkeypatch.delattr(np,'trapz')
    configure_numpy_compatibility()
    ap,_,_=compute_ap(np.array([.5,1.]),np.array([1.,1.]))
    assert .98 < ap <= 1.


def test_augmented_images_share_source_group():
    assert source_group('1xemay645') == source_group('10xemay645')
    assert source_group('2PlateBaza99') == source_group('9PlateBaza99')
    assert source_group('iwt247') != source_group('iwt248')


@pytest.mark.parametrize('line', ['36 .5 .5 .1 .2', '1 nan .5 .1 .2',
                                  '1 .1 .5 .8 .2', '1 .5 .5 0 .2',
                                  '1 .5 .5 .1', '1.2 .5 .5 .1 .2'])
def test_invalid_character_labels_rejected(line):
    with pytest.raises(ValueError):
        parse_labels(line)


def test_decode_two_lines_and_skewed_one_line():
    # class IDs 0..9 and A=10..Z=35; x,y,width,height are normalized.
    two = [(8,.20,.25,.1,.28,.98),(9,.35,.25,.1,.28,.98),
           (15,.60,.25,.1,.28,.98),(1,.75,.25,.1,.28,.98),
           (2,.15,.73,.1,.28,.98),(3,.30,.73,.1,.28,.98),
           (7,.45,.73,.1,.28,.98),(9,.60,.73,.1,.28,.98),
           (2,.75,.73,.1,.28,.98)]
    r = decode_characters(list(reversed(two)))
    assert r['full'] == '89F123792'
    assert r['top_line'] == '89F1' and r['bottom_line'] == '23792'
    one = [(i,.1+i*.12,.15+i*.06,.08,.3,.9) for i in range(6)]
    assert decode_characters(one)['full'] == '012345'
    assert decode_characters(one)['bottom_line'] == ''


def test_conflicting_overlapping_characters_are_not_silently_selected():
    r = decode_characters([(0,.5,.5,.2,.5,.9),(8,.5,.5,.2,.5,.85)])
    assert r['error'] == 'ambiguous_characters' and r['confidence'] == 0


def test_weak_duplicate_character_does_not_erase_strong_observation():
    r=decode_characters([(15,.5,.5,.2,.5,.92),(25,.5,.5,.2,.5,.30)])
    assert r['full']=='F' and r['confidence']==.92


def make_zip(path, names):
    image = np.full((60,100,3),140,np.uint8)
    for i,name in enumerate(names):
        image[0,0] = i
        ok,encoded=cv2.imencode('.jpg',image)
        assert ok
        with zipfile.ZipFile(path,'a') as z:
            z.writestr('dataset/'+name+'.jpg',encoded.tobytes())
            z.writestr('dataset/'+name+'.txt','8 .3 .3 .1 .2\n9 .6 .3 .1 .2')


def test_no_split_leakage_and_repeatable_manifest(tmp_path):
    archive=tmp_path/'data.zip'
    make_zip(archive,['1xemay1','2xemay1','1xemay2','2xemay2','iwt5','iwt6','iwt7','iwt8'])
    report=prepare(archive,tmp_path/'prepared',seed=17)
    rows=report['samples']
    groups={}
    for row in rows:
        assert groups.setdefault(row['group'],row['split']) == row['split']
        assert (tmp_path/'prepared'/'images'/row['split']/row['image']).is_file()
    again=prepare(archive,tmp_path/'prepared2',seed=17)
    assert [(r['image'],r['split']) for r in rows] == [(r['image'],r['split']) for r in again['samples']]
    with pytest.raises(FileExistsError):
        prepare(archive,tmp_path/'prepared')


def test_zip_traversal_rejected_before_any_extraction(tmp_path):
    archive=tmp_path/'evil.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('../outside.txt','data')
    with pytest.raises(ValueError):
        prepare(archive,tmp_path/'prepared')
    assert not (tmp_path/'outside.txt').exists()


def test_windows_case_collisions_rejected(tmp_path):
    archive=tmp_path/'collision.zip'
    make_zip(archive,['Plate1','plate1'])
    with pytest.raises(ValueError,match='colliding'):
        prepare(archive,tmp_path/'prepared')
