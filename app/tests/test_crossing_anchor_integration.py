"""VideoPipeline._update_crossing() must feed the CrossingDetector the
vehicle's bottom-center anchor, not the bbox center — and _make_crossing_detector
must wire the CROSSING_* config constants through."""
from app.cv.pipeline import VideoPipeline
from app.cv.crossing import CrossingDetector
from app.cv.detector import Detection


def _pipeline():
    p = VideoPipeline.__new__(VideoPipeline)
    p._frame_seq = 1
    return p


def test_make_crossing_detector_wires_config():
    import app.config as config
    p = _pipeline()
    detector = p._make_crossing_detector([0.2, 0.5, 0.8, 0.5])
    assert detector.edge_margin == config.CROSSING_EDGE_MARGIN
    assert detector.min_frames_per_side == config.CROSSING_MIN_FRAMES_PER_SIDE
    assert detector.rearm_distance == config.CROSSING_REARM_DISTANCE
    assert detector.cooldown_sec == config.CROSSING_COOLDOWN_SEC
    assert detector.allowed_direction == config.CROSSING_ALLOWED_DIRECTION


def test_update_crossing_uses_bottom_center_not_bbox_center():
    """Vehicle bbox spans y=60..100 on a 100-tall frame: bottom-center lands
    at y=100 (normalized 1.0, clearly BELOW a line at y=0.9), while the bbox
    CENTER would land at y=80 (normalized 0.8, clearly ABOVE that same line).
    Only the bottom-center reading is correct per spec."""
    p = _pipeline()
    p._crossing_detector = CrossingDetector([0.0, 0.9, 1.0, 0.9], min_frames_per_side=1)
    vehicle = Detection('motorcycle', 0.9, (0, 60, 100, 100))
    group = {'track_id': 1, 'vehicle_track_id': 1, '_vehicle': vehicle}
    p._update_crossing(group, frame_w=100, frame_h=100)
    state = p._crossing_detector._tracks[1]
    assert state.stable_side == 1  # BELOW — matches bottom-center (y=100), not center (y=80)
