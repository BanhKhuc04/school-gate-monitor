import threading
from app.cv.inference_worker import InferenceWorker


def test_one_owner_round_robins_camera_queues_and_bounds_backlog():
    worker = InferenceWorker(capacity_per_camera=2)
    started, release = threading.Event(), threading.Event()
    order, threads = [], []
    def work(name):
        order.append(name); threads.append(threading.get_ident())
    blocked = worker.submit('front', lambda: (started.set(), release.wait(2)))
    assert started.wait(1)
    a = worker.submit('front', work, 'front1')
    b = worker.submit('front', work, 'front2')
    c = worker.submit('rear', work, 'rear1')
    import pytest
    with pytest.raises(RuntimeError, match='full'):
        worker.submit('front', work, 'overflow')
    release.set()
    for future in (blocked, a, b, c):
        future.result(2)
    worker.close()
    assert order == ['front1', 'rear1', 'front2']
    assert len(set(threads)) == 1


def test_nested_model_call_does_not_deadlock():
    worker = InferenceWorker()
    assert worker.run('front', lambda: worker.run('front', lambda: 42)) == 42
    worker.close()
