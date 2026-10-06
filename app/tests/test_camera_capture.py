from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from app.cv.capture import WebcamStream


def test_saved_numeric_source_opens_device_not_file():
    with patch('app.cv.capture.cv2.VideoCapture') as factory:
        stream = WebcamStream(' 0 ')
        assert factory.call_args.args[0] == 0
        stream.release()


def test_network_capture_has_timeouts_and_never_seeks_on_failure():
    cap = MagicMock()
    cap.read.return_value = (False, None)
    with patch('app.cv.capture.cv2.VideoCapture', return_value=cap) as factory:
        stream = WebcamStream('rtsp://example.test/live', loop=True)
        assert factory.call_args.args[1] == cv2.CAP_FFMPEG
        assert cv2.CAP_PROP_OPEN_TIMEOUT_MSEC in factory.call_args.args[2]
        with pytest.raises(RuntimeError):
            stream.read_frame()
        assert not any(c.args[0] == cv2.CAP_PROP_POS_FRAMES for c in cap.set.call_args_list)


def test_failed_open_releases_capture_and_does_not_expose_password():
    cap = MagicMock()
    cap.isOpened.return_value = False
    with patch('app.cv.capture.cv2.VideoCapture', return_value=cap):
        with pytest.raises(RuntimeError) as error:
            WebcamStream('rtsp://admin:private-password@example.test/live')
    assert 'private-password' not in str(error.value)
    cap.release.assert_called_once()


def test_local_video_loops_at_eof():
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    cap = MagicMock()
    cap.read.side_effect = [(False, None), (True, frame)]
    with patch('app.cv.capture.cv2.VideoCapture', return_value=cap):
        stream = WebcamStream('sample.mp4', loop=True)
        assert stream.read_frame() is frame
    cap.set.assert_any_call(cv2.CAP_PROP_POS_FRAMES, 0)
