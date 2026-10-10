from unittest.mock import MagicMock

import pytest

from app.tests.conftest import auth_headers


@pytest.fixture
def camera_client(client, test_app):
    from app.api.camera import router
    if not any(getattr(route, 'path', '') == '/api/camera/{gate_id}' for route in test_app.routes):
        test_app.include_router(router)
    return client


def test_unknown_gate_is_404(camera_client):
    response = camera_client.get('/api/camera/missing', headers=auth_headers(camera_client))
    assert response.status_code == 404


def test_presets_do_not_expose_credentials(camera_client, monkeypatch):
    import app.api.camera as api
    monkeypatch.setattr(api, 'CAMERA_PRESETS', [{'label': 'IP', 'source': 'rtsp://user:secret@host/live?token=private'}])
    response = camera_client.get('/api/camera/main', headers=auth_headers(camera_client))
    assert response.status_code == 200
    assert 'secret' not in response.text and 'private' not in response.text


@pytest.mark.parametrize('role', ['security', 'management', 'teacher'])
def test_only_admin_can_change_source(camera_client, role):
    assert camera_client.post('/api/camera/main', json={'source': '0'}, headers=auth_headers(camera_client, role)).status_code == 403


@pytest.fixture
def pipeline(monkeypatch):
    import app.api.camera as api
    from app.cv.camera_switch import CameraSwitch
    fake = MagicMock()
    fake.camera_switch = CameraSwitch(0)
    fake.get_status.return_value = {'running': True, 'thread_alive': True, 'camera_open': True, 'last_frame_age_sec': 0.1}
    monkeypatch.setattr(api, '_get_pipeline', lambda gate_id: fake)
    return fake


@pytest.mark.parametrize('source', ['', '-1', 'ftp://host/live', 'rtsp://', 'missing.mp4'])
def test_invalid_source_is_rejected(camera_client, pipeline, source):
    response = camera_client.post('/api/camera/main', json={'source': source}, headers=auth_headers(camera_client))
    assert response.status_code == 422
    assert not pipeline.camera_switch.has_pending


def test_apply_is_pending_without_persisting(camera_client, pipeline):
    from app.db import get_gate_camera_source
    before = get_gate_camera_source('main')
    response = camera_client.post('/api/camera/main', json={'source': '1'}, headers=auth_headers(camera_client))
    assert response.status_code == 202
    assert response.json()['state'] == 'checking'
    assert response.json()['current'] == '0'
    assert get_gate_camera_source('main') == before
    assert camera_client.post('/api/camera/main', json={'source': '2'}, headers=auth_headers(camera_client)).status_code == 409


def test_missing_gate_never_writes_database(camera_client, pipeline):
    from app.db import get_gate_camera_source
    response = camera_client.post('/api/camera/missing', json={'source': '0'}, headers=auth_headers(camera_client))
    assert response.status_code == 404
    assert get_gate_camera_source('missing') is None


def test_preset_resolves_on_server(camera_client, pipeline, monkeypatch):
    import app.api.camera as api
    monkeypatch.setattr(api, 'CAMERA_PRESETS', [{'label': 'IP', 'source': 'rtsp://user:secret@host/live'}])
    response = camera_client.post('/api/camera/main', json={'preset_id': 'preset-0'}, headers=auth_headers(camera_client))
    assert response.status_code == 202
    assert 'secret' not in response.text
    opened = []
    capture = MagicMock()
    pipeline.camera_switch.apply(None, lambda source: opened.append(source) or capture, MagicMock())
    assert opened == ['rtsp://user:secret@host/live']


def test_offline_service_returns_503(camera_client, pipeline):
    pipeline.get_status.return_value['thread_alive'] = False
    response = camera_client.post('/api/camera/main', json={'source': '1'}, headers=auth_headers(camera_client))
    assert response.status_code == 503


def test_status_reads_live_registry_without_creating_pipeline(camera_client, monkeypatch):
    import app.cv.pipeline as module
    from app.cv.camera_switch import CameraSwitch

    live = MagicMock()
    live.camera_switch = CameraSwitch(0)
    live.get_status.return_value = {
        'running': True, 'thread_alive': True, 'camera_open': True,
        'last_frame_age_sec': 0.1,
    }
    monkeypatch.setattr(module, '_pipelines', {'main': live})
    constructor = MagicMock(side_effect=AssertionError('Status must not load models'))
    monkeypatch.setattr(module, 'VideoPipeline', constructor)
    headers = auth_headers(camera_client)

    response = camera_client.get('/api/camera/main', headers=headers)
    assert response.status_code == 200
    assert response.json()['health']['running'] is True
    assert response.json()['health']['camera_open'] is True

    monkeypatch.setattr(module, '_pipelines', {})
    response = camera_client.get('/api/camera/main', headers=headers)
    assert response.json()['health']['running'] is False
    assert module._pipelines == {}
    constructor.assert_not_called()
