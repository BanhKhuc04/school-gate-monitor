"""Test-video mode: both gates play the two synced recordings at once.

Nothing is saved: Stop, or restarting the app, returns every gate to its live
camera with its own gate line and detection zone. Sources change through each
gate's CameraSwitch, so the gate's own thread opens the file; files playing at
the same time share one start instant (LatestFrameCapture), so the front and
rear videos stay in step. The videos' own gate lines (DEMO_GATE_LINES) apply
meanwhile, and violations recorded are marked as test data
(VideoPipeline._is_test_source).
"""
import os
import threading
import time

from app.config import DEMO_GATE_LINES, DEMO_VIDEOS, GATES
from app.cv.camera_switch import CameraBusy

_lock = threading.Lock()
_live = {}          # gate_id -> (live source, loop flag) to return to
_started_at = None


def videos():
    """Test video for each configured gate."""
    return {gate: path for gate, path in DEMO_VIDEOS.items() if gate in GATES}


def status():
    with _lock:
        active, started = bool(_live), _started_at
    found = videos()
    missing = [os.path.basename(p) for p in found.values() if not os.path.isfile(p)]
    return {'active': active, 'started_at': started,
            'videos': {gate: os.path.basename(p) for gate, p in found.items()},
            'available': bool(found) and not missing, 'missing': missing}


def _scene(pipeline, gate, demo):
    """Gate line + detection zone: the video's own, or the gate's saved ones."""
    if demo:
        line, roi = DEMO_GATE_LINES.get(gate), None
    else:
        from app.db import get_gate_line, get_gate_roi
        line, roi = get_gate_line(gate), get_gate_roi(gate)
    pipeline.set_gate_line(line)
    pipeline._roi_points = roi or None


def start(get_pipeline):
    """Switch every gate that has a test video to it. Raises before switching
    anything when a video or a gate pipeline is missing; CameraBusy when a gate
    is still in the middle of another switch (the others are switched)."""
    global _started_at
    found = videos()
    missing = [os.path.basename(p) for p in found.values() if not os.path.isfile(p)]
    if not found or missing:
        raise FileNotFoundError(', '.join(missing) or 'chưa cấu hình video test')
    pipelines = {gate: get_pipeline(gate) for gate in found}
    if any(p is None for p in pipelines.values()):
        raise RuntimeError('pipeline not running')
    busy = []
    with _lock:
        for gate, path in found.items():
            pipeline = pipelines[gate]
            switch = pipeline.camera_switch
            if switch.source == path:
                continue  # already playing it
            live = _live.get(gate) or (switch.source, GATES[gate].get('loop', True))
            GATES[gate]['loop'] = True  # play the video again and again
            try:
                switch.request(path, persist=False)
            except CameraBusy:
                GATES[gate]['loop'] = live[1]
                busy.append(gate)
                continue
            _live[gate] = live
            _scene(pipeline, gate, demo=True)
        if _live:
            _started_at = _started_at or time.time()
    if busy:
        raise CameraBusy(', '.join(busy))
    return status()


def stop(get_pipeline):
    """Every gate back to its live camera, even one that is offline right now
    (the gate then keeps retrying it instead of playing the video)."""
    global _started_at
    busy = []
    with _lock:
        for gate, (source, loop) in list(_live.items()):
            pipeline = get_pipeline(gate)
            if pipeline is not None:
                try:
                    pipeline.camera_switch.request(source, persist=False, force=True)
                except CameraBusy:
                    busy.append(gate)
                    continue
                _scene(pipeline, gate, demo=False)
            GATES[gate]['loop'] = loop
            del _live[gate]
        if not _live:
            _started_at = None
    if busy:
        raise CameraBusy(', '.join(busy))
    return status()
