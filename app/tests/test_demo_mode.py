"""Nút "Chạy video test": both gates play the recorded videos, then go back live."""
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.cv import demo_mode
from app.cv.camera_switch import CameraBusy, CameraSwitch

FRONT_LIVE = 'rtsp://admin:pw@192.168.0.102/cam/realmonitor?channel=1&subtype=0'
REAR_LIVE = 'rtsp://admin:pw@192.168.0.103/cam/realmonitor?channel=1&subtype=0'


@pytest.fixture
def gates(monkeypatch, tmp_path):
    front, rear = tmp_path / 'cam_truoc.mp4', tmp_path / 'cam_sau.mp4'
    front.write_bytes(b'x')
    rear.write_bytes(b'x')
    config = {'main': {'source': FRONT_LIVE, 'loop': False}, 'secondary': {'source': REAR_LIVE, 'loop': False}}
    monkeypatch.setattr(demo_mode, 'GATES', config)
    monkeypatch.setattr(demo_mode, 'DEMO_VIDEOS', {'main': str(front), 'secondary': str(rear)})
    monkeypatch.setattr(demo_mode, '_live', {})
    monkeypatch.setattr(demo_mode, '_started_at', None)
    import app.db
    monkeypatch.setattr(app.db, 'get_gate_line', lambda gate: [0.1, 0.9, 0.5, 0.7] if gate == 'main' else None)
    monkeypatch.setattr(app.db, 'get_gate_roi', lambda gate: [[0, 0], [1, 0], [1, 1]] if gate == 'main' else None)
    pipelines = {}
    for gate, live in (('main', FRONT_LIVE), ('secondary', REAR_LIVE)):
        p = MagicMock()
        p.camera_switch = CameraSwitch(live)
        p._roi_points = [[0, 0], [1, 0], [1, 1]] if gate == 'main' else None
        pipelines[gate] = p
    return {'config': config, 'pipelines': pipelines, 'front': str(front), 'rear': str(rear)}


def test_start_switches_both_gates_to_their_videos_without_saving(gates):
    status = demo_mode.start(gates['pipelines'].get)
    assert status['active'] and status['videos'] == {'main': 'cam_truoc.mp4', 'secondary': 'cam_sau.mp4'}
    for gate, video in (('main', gates['front']), ('secondary', gates['rear'])):
        p = gates['pipelines'][gate]
        assert p.camera_switch._pending == video and p.camera_switch._persist is False
        assert gates['config'][gate]['loop'] is True  # the video plays again and again
        assert p._roi_points is None
    gates['pipelines']['main'].set_gate_line.assert_called_with([0.0, 0.62, 1.0, 0.62])
    gates['pipelines']['secondary'].set_gate_line.assert_called_with([0.0, 0.55, 1.0, 0.55])


def test_stop_returns_every_gate_to_its_live_camera_line_and_zone(gates):
    demo_mode.start(gates['pipelines'].get)
    for p in gates['pipelines'].values():
        p.camera_switch._pending = None  # the gate thread applied the video
    status = demo_mode.stop(gates['pipelines'].get)
    assert not status['active']
    main, rear = gates['pipelines']['main'], gates['pipelines']['secondary']
    assert main.camera_switch._pending == FRONT_LIVE and main.camera_switch._force is True
    assert rear.camera_switch._pending == REAR_LIVE and rear.camera_switch._persist is False
    main.set_gate_line.assert_called_with([0.1, 0.9, 0.5, 0.7])
    assert main._roi_points == [[0, 0], [1, 0], [1, 1]]
    assert gates['config']['main']['loop'] is False


def test_missing_video_switches_nothing(gates, tmp_path):
    (tmp_path / 'cam_sau.mp4').unlink()
    with pytest.raises(FileNotFoundError, match='cam_sau.mp4'):
        demo_mode.start(gates['pipelines'].get)
    assert all(p.camera_switch._pending is None for p in gates['pipelines'].values())
    assert demo_mode.status()['available'] is False


def test_a_gate_mid_switch_is_reported_and_the_other_still_starts(gates):
    gates['pipelines']['secondary'].camera_switch.request('rtsp://admin:pw@192.168.0.50/x')
    with pytest.raises(CameraBusy):
        demo_mode.start(gates['pipelines'].get)
    assert gates['pipelines']['main'].camera_switch._pending == gates['front']
    assert set(demo_mode._live) == {'main'}


def test_stop_reaches_an_offline_live_camera_instead_of_keeping_the_video():
    switch = CameraSwitch('D:/videos/cam_truoc.mp4')
    video = MagicMock()
    switch.request(FRONT_LIVE, persist=False, force=True)
    assert switch.apply(video, MagicMock(side_effect=RuntimeError('offline')), MagicMock()) is None
    video.release.assert_called_once()
    assert switch.source == FRONT_LIVE and switch.status()['state'] == 'error'


def test_a_normal_failed_switch_still_keeps_the_old_source():
    switch = CameraSwitch(FRONT_LIVE)
    old = MagicMock()
    switch.request(REAR_LIVE)
    assert switch.apply(old, MagicMock(side_effect=RuntimeError('offline')), MagicMock()) is None
    old.release.assert_not_called()
    assert switch.source == FRONT_LIVE


@pytest.fixture
def pipeline(monkeypatch):
    import app.cv.pipeline as module
    monkeypatch.setattr(module, 'GATES', {'main': {'source': 'D:/videos/cam_truoc.mp4', 'loop': True, 'name': 'Camera trước'}})
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


def test_pipeline_drops_the_video_and_retries_the_offline_live_camera(pipeline, monkeypatch):
    import app.cv.pipeline as module
    video = pipeline._webcam = MagicMock()
    monkeypatch.setattr(pipeline, '_open_webcam', MagicMock(side_effect=RuntimeError('offline')))
    pipeline.camera_switch.request(FRONT_LIVE, persist=False, force=True)
    assert pipeline._apply_camera_change() is False
    video.release.assert_called_once()
    assert pipeline._webcam is None  # the run loop now retries the live camera
    assert module.GATES['main']['source'] == FRONT_LIVE
    module.set_gate_camera_source.assert_not_called()


def test_offline_gate_shows_why_on_the_video(pipeline):
    pipeline.camera_switch.source = REAR_LIVE
    pipeline._publish_offline_frame()
    jpeg = pipeline.get_jpeg()
    assert jpeg is not None and jpeg[:2] == b'\xff\xd8'
    import cv2
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape[:2] == (720, 1280)


def test_violations_from_a_video_are_test_data(pipeline):
    pipeline.camera_switch.source = 'D:/videos/cam_truoc.mp4'
    assert pipeline._is_test_source() is True
    pipeline.camera_switch.source = FRONT_LIVE
    assert pipeline._is_test_source() is False
    pipeline.camera_switch.source = 0  # webcam
    assert pipeline._is_test_source() is False


def test_a_camera_that_stays_down_after_a_drop_is_shown_as_disconnected(pipeline, monkeypatch, capsys):
    import app.cv.pipeline as module
    pipeline._webcam, pipeline._running = MagicMock(), True
    pipeline._consecutive_errors = pipeline._RECONNECT_AFTER
    monkeypatch.setattr(pipeline, '_apply_camera_change', lambda: False)
    monkeypatch.setattr(module.time, 'sleep', lambda s: None)
    pipeline._latest_jpeg = None
    assert pipeline._handle_read_error(RuntimeError('rtsp read timeout'))
    out = capsys.readouterr().out
    assert 'Reconnect failed' in out and 'Webcam reconnected' not in out
    assert pipeline.get_jpeg()[:2] == b'\xff\xd8'
