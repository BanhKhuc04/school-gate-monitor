from unittest.mock import MagicMock

import numpy as np
import pytest

from app.cv.camera_switch import CameraSwitch, CameraBusy


def test_bad_first_frame_keeps_old_stream_and_database():
    change = CameraSwitch('0')
    old, candidate, save = MagicMock(), MagicMock(), MagicMock()
    candidate.read_frame.side_effect = RuntimeError('rtsp://secret:password@host')
    change.request('1')
    assert change.apply(old, lambda source: candidate, save) is None
    old.release.assert_not_called()
    candidate.release.assert_called_once()
    save.assert_not_called()
    assert change.source == 0
    assert change.status()['state'] == 'error'
    assert 'password' not in str(change.status())


def test_switch_commits_only_after_first_frame_and_releases_old():
    change = CameraSwitch(0)
    old, candidate = MagicMock(), MagicMock()
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    candidate.read_frame.return_value = frame
    save = MagicMock(side_effect=lambda source: old.release.assert_not_called())
    change.request('1')
    stream, first_frame = change.apply(old, lambda source: candidate, save)
    assert stream is candidate and first_frame is frame
    save.assert_called_once_with('1')
    old.release.assert_called_once()
    assert change.source == 1
    assert change.status()['state'] == 'applied'


def test_database_failure_keeps_old_stream():
    change = CameraSwitch(0)
    old, candidate = MagicMock(), MagicMock()
    candidate.read_frame.return_value = np.zeros((2, 2, 3))
    change.request('1')
    save = MagicMock(side_effect=OSError('disk full'))
    assert change.apply(old, lambda source: candidate, save) is None
    old.release.assert_not_called()
    candidate.release.assert_called_once()
    assert change.source == 0


def test_second_request_cannot_replace_pending_source():
    change = CameraSwitch(0)
    change.request('1')
    with pytest.raises(CameraBusy):
        change.request('2')
    assert change.status()['pending'] == '1'


def test_status_redacts_credentials_and_query():
    change = CameraSwitch('rtsp://user:secret@host/live?token=private')
    assert change.status()['current'] == 'rtsp://host/live'


def test_same_source_is_noop_when_camera_is_online():
    change = CameraSwitch(0)
    change.request('0', camera_online=True)
    assert change.status()['state'] == 'applied'
    assert not change.has_pending


def test_same_source_can_retry_when_camera_is_offline():
    change = CameraSwitch(0)
    change.request('0', camera_online=False)
    assert change.has_pending
