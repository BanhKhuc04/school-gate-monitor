"""Test-video mode: both gates play the two synced recordings at once.

Nothing is saved: Stop, or restarting the app, returns every gate to its live
camera with its own gate line and detection zone. Sources change through each
gate's CameraSwitch, so the gate's own thread opens the file, and the two
videos share one clock (LatestFrameCapture sync group 'demo'), so the front and
rear pictures show the same moment. The videos' own gate lines
(DEMO_GATE_LINES) apply meanwhile, and violations recorded are marked as test
data (VideoPipeline._is_test_source).

A gate still busy with an earlier switch (opening a live camera can take
seconds) is switched as soon as it is free, by a small background worker: a
quick Stop -> Start used to leave one gate on its live camera while the other
played its video.
"""
import os
import threading
import time

from app.config import DEMO_GATE_LINES, DEMO_VIDEOS, GATES
from app.cv.camera_switch import CameraBusy

SETTLE_TIMEOUT_SEC = 5.0   # how long Start/Stop wait to answer with both gates switched
PASS_INTERVAL_SEC = 0.3

_lock = threading.RLock()
_mode = None        # 'demo' | 'live' (returning to the cameras) | None
_live = {}          # gate_id -> (live source, loop flag) to return to
_started_at = None
_get_pipeline = None
_worker = None


def videos():
    """Test video for each configured gate."""
    return {gate: path for gate, path in DEMO_VIDEOS.items() if gate in GATES}


def is_demo_video(source):
    if not isinstance(source, str):
        return False
    target = os.path.normcase(os.path.abspath(source))
    return any(os.path.normcase(os.path.abspath(p)) == target for p in DEMO_VIDEOS.values())


def _configured_source(gate):
    """The gate's own camera: the one chosen in Settings -> Camera, else .env."""
    from app.config import GATE_CONFIGURED_SOURCES
    from app.db import get_gate_camera_source
    saved = get_gate_camera_source(gate)
    return saved if saved is not None and not is_demo_video(saved) else GATE_CONFIGURED_SOURCES.get(gate)


def _missing(found):
    return [os.path.basename(p) for p in found.values() if not os.path.isfile(p)]


def _scene(pipeline, gate, demo):
    """Gate line + detection zone: the video's own, or the gate's saved ones."""
    if demo:
        line, roi = DEMO_GATE_LINES.get(gate), None
    else:
        from app.db import get_gate_line, get_gate_roi
        line, roi = get_gate_line(gate), get_gate_roi(gate)
    pipeline.set_gate_line(line)
    pipeline._roi_points = roi or None


def _pass():
    """Ask every gate that is not where it should be to switch, unless it is
    still busy with an earlier switch. True when every gate is there."""
    global _mode, _started_at
    with _lock:
        if _mode is None:
            return True
        found, done = videos(), True
        for gate, (live, loop) in list(_live.items()):
            pipeline = _get_pipeline(gate) if _get_pipeline else None
            if pipeline is None:
                continue
            switch = pipeline.camera_switch
            target = found.get(gate) if _mode == 'demo' else live
            if switch.source == target and not switch.has_pending:
                if _mode == 'live':
                    GATES[gate]['loop'] = loop
                    del _live[gate]
                continue
            done = False
            if switch.has_pending:
                continue  # mid-switch: ask again on the next pass
            try:
                if _mode == 'demo':
                    GATES[gate]['loop'] = True  # play the video again and again
                    switch.request(target, persist=False)
                else:
                    # force: an offline camera still replaces the video; the
                    # gate keeps retrying it and says so on screen.
                    switch.request(target, persist=False, force=True)
            except CameraBusy:
                continue
            _scene(pipeline, gate, demo=_mode == 'demo')
        if _mode == 'live' and not _live:
            _mode, _started_at = None, None
        return done


def _work():
    while True:
        _pass()
        with _lock:
            if _mode is None:
                return
        time.sleep(PASS_INTERVAL_SEC)


def _kick():
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, daemon=True, name='demo-videos')
            _worker.start()


def _settle():
    deadline = time.monotonic() + SETTLE_TIMEOUT_SEC
    while not _pass() and time.monotonic() < deadline:
        time.sleep(0.1)


def start(get_pipeline):
    """Both gates to their test videos. Raises before switching anything when a
    video or a gate pipeline is missing."""
    global _mode, _started_at, _get_pipeline
    found = videos()
    missing = _missing(found)
    if not found or missing:
        raise FileNotFoundError(', '.join(missing) or 'chưa cấu hình video test')
    pipelines = {gate: get_pipeline(gate) for gate in found}
    if any(p is None for p in pipelines.values()):
        raise RuntimeError('pipeline not running')
    with _lock:
        for gate, pipeline in pipelines.items():
            if gate not in _live:
                source = pipeline.camera_switch.source
                if is_demo_video(source):  # left on a video: return to its configured camera
                    source = _configured_source(gate)
                _live[gate] = (source, GATES[gate].get('loop', True))
        _mode, _get_pipeline = 'demo', get_pipeline
        _started_at = _started_at or time.time()
    _settle()
    _kick()
    return status(get_pipeline)


def stop(get_pipeline):
    """Every gate back to its live camera, even one that is offline right now."""
    global _mode, _get_pipeline
    global _started_at
    with _lock:
        if not _live:
            _mode, _started_at = None, None
            return status(get_pipeline)
        _mode, _get_pipeline = 'live', get_pipeline
    _settle()
    _kick()
    return status(get_pipeline)


def status(get_pipeline=None):
    found = videos()
    with _lock:
        mode, started = _mode, _started_at
    gates = {}
    for gate, path in found.items():
        pipeline = get_pipeline(gate) if get_pipeline else None
        source = getattr(getattr(pipeline, 'camera_switch', None), 'source', None)
        playing = isinstance(source, str) and is_demo_video(source) and os.path.basename(source) == os.path.basename(path)
        position = getattr(pipeline, '_source_position', None) if playing else None
        gates[gate] = {'video': os.path.basename(path), 'playing': playing,
                       'position': round(position, 2) if isinstance(position, (int, float)) else None}
    positions = [g['position'] for g in gates.values()]
    offset = None
    if len(positions) > 1 and None not in positions and max(positions) - min(positions) < 10:
        offset = round(max(positions) - min(positions), 2)  # (>10 s apart = one just looped)
    missing = _missing(found)
    return {'active': mode == 'demo',
            'switching': mode == 'live' or (mode == 'demo' and not all(g['playing'] for g in gates.values())),
            'started_at': started, 'videos': {g: v['video'] for g, v in gates.items()},
            'gates': gates, 'offset_sec': offset,
            'available': bool(found) and not missing, 'missing': missing}
