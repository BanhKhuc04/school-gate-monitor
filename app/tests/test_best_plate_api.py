from types import SimpleNamespace
import numpy as np
from app.tests.conftest import auth_headers
from app.cv.best_plate import BestPlateStore, make_candidate


def test_audio_configuration_does_not_construct_pipeline(client,monkeypatch):
    import app.cv.pipeline as module
    from unittest.mock import MagicMock
    constructor=MagicMock(side_effect=AssertionError('No pipeline initialization'))
    monkeypatch.setattr(module,'get_pipeline',constructor)
    headers=auth_headers(client)
    response=client.get('/guard/audio/config',headers=headers)
    assert response.status_code==200
    assert response.json()['engine']=='Web Speech API'
    assert response.json()['rate']==1.45 and response.json()['volume']==1
    constructor.assert_not_called()
    client.cookies.clear()
    assert client.get('/guard/audio/config').status_code==401


def test_best_crop_download_is_exact_and_checks_role_and_epoch(client,monkeypatch):
    import cv2
    import app.cv.pipeline as module
    store=BestPlateStore()
    original=np.arange(100*120*3,dtype=np.uint8).reshape(100,120,3)
    store.offer(7,make_candidate(original,(10,10,110,90),.9,42,1))
    monkeypatch.setattr(module,'get_existing_pipeline',lambda *_:SimpleNamespace(_best_plates=store,_source_epoch=2))
    headers=auth_headers(client)
    response=client.get('/guard/plate_best/7?gate=main&epoch=2',headers=headers)
    assert response.status_code==200 and response.headers['content-type']=='image/png'
    decoded=cv2.imdecode(np.frombuffer(response.content,np.uint8),cv2.IMREAD_COLOR)
    assert np.array_equal(decoded,original[10:90,10:110])
    assert 'frame-42.png' in response.headers['content-disposition']
    assert client.get('/guard/plate_best/7?gate=main&epoch=1',headers=headers).status_code==404
    client.cookies.clear()
    assert client.get('/guard/plate_best/7?gate=main&epoch=2').status_code==401
    assert client.get('/guard/plate_best/7?gate=main&epoch=2',headers=auth_headers(client,'teacher')).status_code==403
