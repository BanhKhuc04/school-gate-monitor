"""Xóa vi phạm: test-video records only, or everything (backed up first)."""
import os
import sqlite3

import pytest

from app.tests.conftest import auth_headers


def _add(db, name, is_test):
    return db.add_violation_event(
        timestamp='2026-10-05T07:00:00+00:00', helmet_status='no_helmet',
        violation_type='NO_HELMET', snapshot_path=f'data/snapshots/{name}.jpg',
        crop_snapshot_path=f'data/snapshots/{name}_crop.jpg', gate_id='main',
        encounter_id=f'enc-{name}', is_test=is_test)


@pytest.fixture
def env(client, tmp_path, monkeypatch):
    import app.config as config
    import app.db as db
    db.clear_violations()
    snapshots, backups = tmp_path / 'snapshots', tmp_path / 'backups'
    snapshots.mkdir()
    monkeypatch.setattr(config, 'SNAPSHOTS_DIR', str(snapshots))
    monkeypatch.setattr(config, 'BACKUP_DIR', str(backups))
    for name in ('real', 'real_crop', 'test', 'test_crop'):
        (snapshots / f'{name}.jpg').write_bytes(b'jpg')
    return {'db': db, 'snapshots': snapshots, 'backups': backups,
            'real': _add(db, 'real', False), 'test': _add(db, 'test', True)}


def _ids(db):
    return {row['id'] for row in db.list_violations(limit=50)['items']}


def test_violation_rows_say_whether_they_came_from_a_test_video(env):
    rows = {row['id']: row for row in env['db'].list_violations(limit=50)['items']}
    assert rows[env['real']]['is_test'] == 0 and rows[env['test']]['is_test'] == 1


def test_test_scope_removes_only_test_records_and_their_pictures(env, client):
    response = client.post('/api/violations/clear', json={'scope': 'test'}, headers=auth_headers(client))
    assert response.status_code == 200, response.text
    assert response.json()['deleted'] == 1 and response.json()['backup'] is None
    assert _ids(env['db']) == {env['real']}
    assert sorted(os.listdir(env['snapshots'])) == ['real.jpg', 'real_crop.jpg']


def test_all_scope_backs_up_then_removes_everything(env, client):
    response = client.post('/api/violations/clear', json={'scope': 'all'}, headers=auth_headers(client))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['deleted'] == 2 and body['media_moved'] == 4
    assert _ids(env['db']) == set()
    assert os.listdir(env['snapshots']) == []
    backup = env['backups'] / os.path.basename(body['backup'])
    assert sorted(os.listdir(backup)) == ['app.db', 'real.jpg', 'real_crop.jpg', 'test.jpg', 'test_crop.jpg']
    with sqlite3.connect(backup / 'app.db') as saved:
        assert saved.execute('SELECT COUNT(*) FROM violation_events').fetchone()[0] == 2


def test_only_admin_may_clear(env, client):
    response = client.post('/api/violations/clear', json={'scope': 'all'}, headers=auth_headers(client, 'security'))
    assert response.status_code == 403
    assert _ids(env['db']) == {env['real'], env['test']}


def test_unknown_scope_is_rejected(env, client):
    response = client.post('/api/violations/clear', json={'scope': 'everything'}, headers=auth_headers(client))
    assert response.status_code == 422


def test_demo_status_is_readable_by_guards_but_only_admin_starts_it(client):
    assert client.get('/api/demo', headers=auth_headers(client, 'security')).status_code == 200
    assert client.post('/api/demo/start', headers=auth_headers(client, 'security')).status_code == 403
