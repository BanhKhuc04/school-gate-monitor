"""Camera presets are local configuration and do not embed device credentials."""
import json

import pytest

from app import config


def test_default_presets_have_no_network_credentials(monkeypatch):
    monkeypatch.delenv('CAMERA_PRESETS_JSON', raising=False)
    assert config._camera_presets_from_env() == [
        {'label': 'Webcam laptop', 'source': '0'},
        {'label': 'OBS Virtual Camera', 'source': '1'},
    ]


def test_local_presets_are_loaded_from_environment(monkeypatch):
    preset = {'label': 'Local camera', 'source': 'rtsp://camera.example.test/live'}
    monkeypatch.setenv('CAMERA_PRESETS_JSON', json.dumps([preset]))
    assert config._camera_presets_from_env()[-1] == preset


@pytest.mark.parametrize('value', ['not-json', '{}', '[{}]', '[{"label": 1, "source": "0"}]'])
def test_malformed_presets_fail_without_echoing_payload(monkeypatch, value):
    monkeypatch.setenv('CAMERA_PRESETS_JSON', value)
    with pytest.raises(ValueError, match='CAMERA_PRESETS_JSON') as error:
        config._camera_presets_from_env()
    assert value not in str(error.value)
