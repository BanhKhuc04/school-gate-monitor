"""Exercise source changes through the real pipeline, without models or physical cameras."""
from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.fixture
def pipeline(monkeypatch):
    """FIX (T4): pipeline fixture cho test_camera_pipeline.py.

    Không dùng pipeline_test_env (init_db nặng). Thay vào đó mock tất cả
    DB-touching functions để pipeline tests không cần real DB.
    """
    import app.cv.pipeline as module
    monkeypatch.setattr(module, 'GATES', {'main': {'source': 0, 'loop': True, 'name': 'Test gate'}})
    monkeypatch.setattr(module, 'HelmetPlateDetector', MagicMock())
    monkeypatch.setattr(module, 'get_gate_roi', lambda gate: None)
    monkeypatch.setattr(module, 'get_gate_camera_source', lambda gate: None)
    monkeypatch.setattr(module, 'get_gate_line', lambda gate: None)
    monkeypatch.setattr(module, 'CONTINUOUS_RECORDING_ENABLED', False)
    monkeypatch.setattr(module, 'set_gate_camera_source', MagicMock())
    value = module.VideoPipeline('main', module.GATES['main'])
    yield value
    value._detect_pool.shutdown(wait=True)
    value._io_pool.shutdown(wait=True)


def test_source_switch_preserves_pipeline_and_models_but_clears_scene(pipeline, monkeypatch):
    import app.cv.pipeline as module
    old = MagicMock()
    pipeline._webcam = old
    pipeline._last_person_dets = ['old detection']
    pipeline._prev_track_bbox[1] = (1, 2, 3, 4)
    pipeline._clip_buffer.append(np.zeros((2, 2, 3)))
    previous_voter = pipeline._plate_voter
    previous_events = pipeline._event_manager
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    candidate = MagicMock()
    candidate.read_frame.return_value = frame
    monkeypatch.setattr(pipeline, '_open_webcam', lambda config: candidate)
    pipeline.camera_switch.request('1')
    pipeline._apply_camera_change()
    assert pipeline._webcam is candidate
    assert np.array_equal(pipeline.get_frame(), frame)
    assert module.GATES['main']['source'] == 1
    module.set_gate_camera_source.assert_called_once_with('main', '1')
    assert module.HelmetPlateDetector.call_count == 3  # construction only
    assert not pipeline._last_person_dets and not pipeline._prev_track_bbox and not pipeline._clip_buffer
    assert pipeline._plate_voter is not previous_voter and pipeline._event_manager is not previous_events
    old.release.assert_called_once()


def test_pipeline_recovers_from_failed_startup_via_source_selection(pipeline, monkeypatch):
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    candidate = MagicMock()
    # Stop only after the first-frame verification.
    reads = []
    def read():
        reads.append(1)
        if len(reads) == 2:
            pipeline._running = False
        return frame
    candidate.read_frame.side_effect = read
    monkeypatch.setattr(pipeline, '_open_webcam', MagicMock(side_effect=[RuntimeError('offline'), candidate]))
    pipeline.camera_switch.request('1')
    pipeline._running = True
    pipeline._run_loop()
    assert pipeline.camera_switch.status()['state'] == 'applied'
    assert pipeline.camera_switch.source == 1
    assert np.array_equal(pipeline.get_frame(), frame)
    candidate.release.assert_called_once()


def test_bad_change_leaves_existing_frame_available(pipeline, monkeypatch):
    frame = np.ones((20, 20, 3), dtype=np.uint8)
    pipeline._latest_frame = frame
    old = pipeline._webcam = MagicMock()
    monkeypatch.setattr(pipeline, '_open_webcam', MagicMock(side_effect=RuntimeError('offline')))
    pipeline.camera_switch.request('1')
    pipeline._apply_camera_change()
    assert pipeline._webcam is old
    assert np.array_equal(pipeline.get_frame(), frame)
    assert pipeline.camera_switch.status()['state'] == 'error'
    old.release.assert_not_called()


def test_real_video_capture_can_switch_without_camera_hardware(tmp_path):
    import cv2
    from app.cv.capture import WebcamStream
    from app.cv.camera_switch import CameraSwitch
    paths = [tmp_path / 'first.avi', tmp_path / 'second.avi']
    for path, color in zip(paths, [30, 210]):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 5, (32, 32))
        assert writer.isOpened()
        for _ in range(3):
            writer.write(np.full((32, 32, 3), color, dtype=np.uint8))
        writer.release()
    old = WebcamStream(str(paths[0]), loop=True)
    change = CameraSwitch(str(paths[0]))
    save = MagicMock()
    change.request(str(paths[1]))
    result = change.apply(old, lambda source: WebcamStream(source, loop=True), save)
    assert result is not None
    stream, frame = result
    try:
        assert frame.mean() > 180
        assert not old.is_opened
        for _ in range(6):
            assert stream.read_frame().mean() > 180
    finally:
        stream.release()
    save.assert_called_once_with(str(paths[1]))
