"""Only an explicitly selected guard/admin browser owns the gate speaker."""
from uuid import uuid4
import pytest


@pytest.fixture(autouse=True)
def isolated_leases(monkeypatch):
    import app.api.audio_lease as lease
    monkeypatch.setattr(lease, '_leases', {})


def login(client, role='security'):
    response=client.post('/api/auth/login',json={'username':role,'password':'test123'})
    assert response.status_code==200


def test_one_browser_owns_speaker_until_release(client):
    import app.api.audio_lease as lease
    login(client)
    a={'client_id':str(uuid4()),'gate_id':'main'}
    b={'client_id':str(uuid4()),'gate_id':'main'}
    assert client.post('/guard/audio/lease',json=a).status_code==200
    assert lease.owns_audio('main','security',a['client_id'])
    assert not lease.owns_audio('main','security',b['client_id'])
    assert client.post('/guard/audio/lease',json=b).status_code==409
    assert client.post('/guard/audio/lease',json=a).status_code==200
    assert client.request('DELETE','/guard/audio/lease',json=b).status_code==200
    assert lease.owns_audio('main','security',a['client_id'])
    assert client.request('DELETE','/guard/audio/lease',json=a).status_code==200
    assert client.post('/guard/audio/lease',json=b).status_code==200


def test_lease_expires_after_fifteen_seconds(client, monkeypatch):
    import app.api.audio_lease as lease
    clock=[100.0]
    monkeypatch.setattr(lease,'monotonic',lambda:clock[0])
    login(client)
    a={'client_id':str(uuid4()),'gate_id':'main'}
    assert client.post('/guard/audio/lease',json=a).status_code==200
    clock[0]=115.1
    assert not lease.owns_audio('main','security',a['client_id'])
    assert client.post('/guard/audio/lease',json={**a,'client_id':str(uuid4())}).status_code==200


@pytest.mark.parametrize('role',['teacher','management'])
def test_viewer_cannot_acquire_speaker(client, role):
    login(client,role)
    assert client.post('/guard/audio/lease',json={'client_id':str(uuid4()),'gate_id':'main'}).status_code==403


def test_lease_checks_origin_and_gate(client, monkeypatch):
    login(client)
    data={'client_id':str(uuid4()),'gate_id':'main'}
    monkeypatch.setenv('WS_ALLOWED_ORIGINS','http://allowed.test')
    assert client.post('/guard/audio/lease',json=data,headers={'Origin':'http://evil.test'}).status_code==403
    assert client.post('/guard/audio/lease',json={**data,'gate_id':'nonexistent'}).status_code==404
