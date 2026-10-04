"""A ridden motorcycle scores 0.2-0.4 (rider hides half of it); it must still
be detected and tracked, without lowering the person threshold."""
import numpy as np
from types import SimpleNamespace

from ultralytics.engine.results import Boxes

from app.cv.detector import HelmetPlateDetector


def _detector(rows):
    d = HelmetPlateDetector.__new__(HelmetPlateDetector)
    d.camera_id, d._tracker, d._class_tracker = 'test', None, None
    d.conf_threshold = .4
    d.class_conf = {'motorcycle': .2, 'bicycle': .2}
    d._class_names = {0: 'person', 1: 'bicycle', 3: 'motorcycle'}
    seen = {}

    def model(frame, conf, **kwargs):
        seen['conf'] = conf
        data = np.array([r for r in rows if r[4] >= conf], dtype=np.float32).reshape(-1, 6)
        return [SimpleNamespace(boxes=Boxes(data, (480, 640)))]
    d.model, d.seen = model, seen
    return d


ROWS = [[100, 100, 200, 400, .9, 0],   # person
        [300, 100, 400, 400, .3, 0],   # weak person: below 0.4, dropped
        [110, 250, 190, 420, .3, 3]]   # ridden motorcycle


def test_low_confidence_motorcycle_kept_weak_person_dropped():
    d = _detector(ROWS)
    out = d._infer(np.zeros((480, 640, 3), np.uint8), False)
    assert d.seen['conf'] == .2
    assert sorted((x.class_name, round(x.confidence, 1)) for x in out) == [('motorcycle', .3), ('person', .9)]


def test_tracked_person_and_motorcycle_get_distinct_ids():
    d = _detector(ROWS)
    frame = np.zeros((480, 640, 3), np.uint8)
    for _ in range(3):
        out = d._infer(frame, True)
    ids = {x.class_name: x.track_id for x in out}
    assert set(ids) == {'person', 'motorcycle'}
    assert ids['person'] != ids['motorcycle']


def test_without_class_conf_behaviour_is_unchanged():
    d = _detector(ROWS)
    d.class_conf = {}
    out = d._infer(np.zeros((480, 640, 3), np.uint8), False)
    assert d.seen['conf'] == .4
    assert [x.class_name for x in out] == ['person']
