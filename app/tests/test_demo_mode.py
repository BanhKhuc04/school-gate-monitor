"""Nút "Chạy video test": both gates play the recorded videos, then go back live."""
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.cv import demo_mode
from app.cv.camera_switch import CameraSwitch

FRONT_LIVE = 'rtsp://admin:pw@192.168.0.102/cam/realmonitor?channel=1&subtype=0'
REAR_LIVE = 'rtsp://admin:pw@192.168.0.103/cam/realmonitor?channel=1&subtype=0'


class Clip:
    """What a gate thread opens: a video or camera that hands over a frame."""
    def read_frame(self):
        return np.zeros((4, 4, 3), np.uint8)

    def release(self):
        pass


def offline(source):
    raise RuntimeError('offline')


def gate_thread_applies(pipeline, open_stream=lambda source: Clip()):
    """The gate's own thread picks up its pending switch."""
    return pipeline.camera_switch.apply(Clip(), open_stream, MagicMock())


@pytest.fixture
def gates(monkeypatch, tmp_path):
    front, rear = tmp_path / 'dongbo_camera_truoc.mp4', tmp_path / 'dongbo_camera_sau.mp4'
    front.write_bytes(b'x')
    rear.write_bytes(b'x')
    config = {'main': {'source': FRONT_LIVE, 'loop': False}, 'secondary': {'source': REAR_LIVE, 'loop': False}}
    monkeypatch.setattr(demo_mode, 'GATES', config)
    monkeypatch.setattr(demo_mode, 'DEMO_VIDEOS', {'main': str(front), 'secondary': str(rear)})
    monkeypatch.setattr(demo_mode, '_live', {})
    monkeypatch.setattr(demo_mode, '_mode', None)
    monkeypatch.setattr(demo_mode, '_started_at', None)
    monkeypatch.setattr(demo_mode, '_get_pipeline', None)
    monkeypatch.setattr(demo_mode, 'SETTLE_TIMEOUT_SEC', 0)
    monkeypatch.setattr(demo_mode, '_kick', lambda: None)  # tests drive the passes themselves
    import app.db
    monkeypatch.setattr(app.db, 'get_gate_line', lambda gate: [0.1, 0.9, 0.5, 0.7] if gate == 'main' else None)
    monkeypatch.setattr(app.db, 'get_gate_roi', lambda gate: [[0, 0], [1, 0], [1, 1]] if gate == 'main' else None)
    pipelines = {}
    for gate, live in (('main', FRONT_LIVE), ('secondary', REAR_LIVE)):
        p = MagicMock()
        p.camera_switch = CameraSwitch(live)
        p._roi_points = [[0, 0], [1, 0], [1, 1]] if gate == 'main' else None
        p._source_position = None
        pipelines[gate] = p
    return {'config': config, 'pipelines': pipelines, 'front': str(front), 'rear': str(rear)}


def test_start_switches_both_gates_to_their_videos_without_saving(gates):
    status = demo_mode.start(gates['pipelines'].get)
    assert status['active'] and status['switching']  # until each gate thread opens its video
    assert status['videos'] == {'main': 'dongbo_camera_truoc.mp4', 'secondary': 'dongbo_camera_sau.mp4'}
    for gate, video in (('main', gates['front']), ('secondary', gates['rear'])):
        p = gates['pipelines'][gate]
        assert p.camera_switch._pending == video and p.camera_switch._persist is False
        assert gates['config'][gate]['loop'] is True  # the video plays again and again
        assert p._roi_points is None
        gate_thread_applies(p)
    gates['pipelines']['main'].set_gate_line.assert_called_with([0.0, 0.62, 1.0, 0.62])
    gates['pipelines']['secondary'].set_gate_line.assert_called_with([0.0, 0.55, 1.0, 0.55])
    status = demo_mode.status(gates['pipelines'].get)
    assert not status['switching'] and all(g['playing'] for g in status['gates'].values())


def test_a_gate_still_opening_its_camera_switches_as_soon_as_it_is_free(gates):
    # 05/10 on site: Stop then Start quickly; the rear gate was still opening its
    # offline camera, was skipped, and stayed live while the front played its video.
    rear = gates['pipelines']['secondary']
    rear.camera_switch.request(REAR_LIVE.replace('.103', '.104'), persist=False, force=True)
    demo_mode.start(gates['pipelines'].get)
    gate_thread_applies(gates['pipelines']['main'])
    assert rear.camera_switch._pending != gates['rear']
    gate_thread_applies(rear, offline)  # the earlier switch finally gives up
    assert demo_mode._pass() is False
    assert rear.camera_switch._pending == gates['rear']
    gate_thread_applies(rear)
    assert demo_mode._pass() is True
    assert all(g['playing'] for g in demo_mode.status(gates['pipelines'].get)['gates'].values())


def test_stop_returns_every_gate_to_its_live_camera_line_and_zone(gates):
    demo_mode.start(gates['pipelines'].get)
    for p in gates['pipelines'].values():
        gate_thread_applies(p)
    status = demo_mode.stop(gates['pipelines'].get)
    assert not status['active'] and status['switching']
    main, rear = gates['pipelines']['main'], gates['pipelines']['secondary']
    assert main.camera_switch._pending == FRONT_LIVE and main.camera_switch._force is True
    assert rear.camera_switch._pending == REAR_LIVE and rear.camera_switch._persist is False
    gate_thread_applies(main)
    gate_thread_applies(rear, offline)  # offline camera: the video is dropped anyway
    assert demo_mode._pass() is True
    status = demo_mode.status(gates['pipelines'].get)
    assert not status['active'] and not status['switching'] and demo_mode._live == {}
    assert rear.camera_switch.source == REAR_LIVE
    main.set_gate_line.assert_called_with([0.1, 0.9, 0.5, 0.7])
    assert main._roi_points == [[0, 0], [1, 0], [1, 1]]
    assert gates['config']['main']['loop'] is False


def test_quick_stop_then_start_keeps_each_gates_own_camera(gates):
    demo_mode.start(gates['pipelines'].get)
    for p in gates['pipelines'].values():
        gate_thread_applies(p)
    demo_mode.stop(gates['pipelines'].get)
    demo_mode.start(gates['pipelines'].get)  # before the gates went back live
    assert demo_mode._live['main'][0] == FRONT_LIVE and demo_mode._live['secondary'][0] == REAR_LIVE
    for p in gates['pipelines'].values():
        gate_thread_applies(p)  # the pending return to live completes...
    demo_mode._pass()  # ...and each gate is sent back to its video
    assert gates['pipelines']['main'].camera_switch._pending == gates['front']
    assert gates['pipelines']['secondary'].camera_switch._pending == gates['rear']


def test_status_shows_where_each_video_is_and_how_far_apart(gates):
    demo_mode.start(gates['pipelines'].get)
    main, rear = gates['pipelines']['main'], gates['pipelines']['secondary']
    for p in (main, rear):
        gate_thread_applies(p)
    main._source_position, rear._source_position = 83.42, 83.38
    status = demo_mode.status(gates['pipelines'].get)
    assert status['gates']['main']['position'] == 83.42 and status['offset_sec'] == 0.04
    main._source_position = 0.1  # the front video just looped: no bogus 83 s gap
    assert demo_mode.status(gates['pipelines'].get)['offset_sec'] is None
    rear.camera_switch.source = gates['front']  # the rear gate showing the front video
    assert demo_mode.status(gates['pipelines'].get)['gates']['secondary']['playing'] is False


def test_missing_video_switches_nothing(gates, tmp_path):
    (tmp_path / 'dongbo_camera_sau.mp4').unlink()
    with pytest.raises(FileNotFoundError, match='dongbo_camera_sau.mp4'):
        demo_mode.start(gates['pipelines'].get)
    assert all(p.camera_switch._pending is None for p in gates['pipelines'].values())
    assert demo_mode.status(gates['pipelines'].get)['available'] is False


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
    value._stop_capture()
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


def test_only_the_two_test_videos_share_a_playback_clock(pipeline, monkeypatch):
    import queue
    monkeypatch.setattr(demo_mode, 'DEMO_VIDEOS', {'main': 'D:/demo/dongbo_camera_truoc.mp4'})
    pipeline._webcam, pipeline._preview_frame_queue = Clip(), queue.Queue(maxsize=2)
    pipeline.camera_switch.source = 'D:/demo/dongbo_camera_truoc.mp4'
    pipeline._start_capture()
    assert pipeline._capture.sync_group == 'demo'
    pipeline._stop_capture()
    pipeline.camera_switch.source = 'D:/Work/gate_recordings/20261004_2336_cong_chinh_cam18_000.mp4'
    pipeline._start_capture()
    assert pipeline._capture.sync_group is None


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
