import threading

import pytest

from app.cv.inference_worker import InferenceWorker, model_lock


def test_each_camera_owns_a_lane_and_one_blocked_camera_never_stalls_another():
    worker = InferenceWorker(capacity_per_camera=2)
    started, release = threading.Event(), threading.Event()
    order, threads = [], {}
    def work(name):
        order.append(name); threads.setdefault(name.rstrip('12'), set()).add(threading.get_ident())
    blocked = worker.submit('front', lambda: (started.set(), release.wait(2)))
    assert started.wait(1)
    a = worker.submit('front', work, 'front1')
    b = worker.submit('front', work, 'front2')
    with pytest.raises(RuntimeError, match='full'):
        worker.submit('front', work, 'overflow')
    # The rear lane runs while the front lane is still blocked.
    worker.submit('rear', work, 'rear1').result(1)
    assert order == ['rear1']
    release.set()
    for future in (blocked, a, b):
        future.result(2)
    worker.close()
    assert order == ['rear1', 'front1', 'front2']  # per-camera FIFO
    assert len(threads['front']) == 1 and threads['front'] != threads['rear']


def test_nested_model_call_does_not_deadlock():
    worker = InferenceWorker()
    assert worker.run('front', lambda: worker.run('front', lambda: 42)) == 42
    assert worker.run('front', lambda: worker.run('rear', lambda: 7)) == 7
    worker.close()


def test_a_model_shared_by_two_lanes_never_runs_twice_at_once():
    worker = InferenceWorker()
    model, active, peak = object.__new__(type('Model', (), {})), [0], [0]
    def infer():
        with model_lock(model):
            active[0] += 1; peak[0] = max(peak[0], active[0])
            threading.Event().wait(.05)
            active[0] -= 1
    futures = [worker.submit(camera, infer) for camera in ('front', 'rear', 'front', 'rear')]
    for future in futures:
        future.result(2)
    worker.close()
    assert peak[0] == 1
