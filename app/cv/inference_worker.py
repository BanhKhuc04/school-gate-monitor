"""Bounded model-owner lanes: one owner thread per camera.

Every model call runs on its camera's owner thread, so a camera never runs two
inferences at once and a slow consumer cannot queue unbounded work. Cameras
used to share ONE owner thread: with both gates running, every person/helmet/
plate/pose call of one camera waited for the other's (7-9 ms a call alone,
21 ms with two cameras; both stuck at ~22 fps from a 25 fps source while the
GPU sat at 29%). Models are never shared unguarded: `model_lock` serialises any
model that two lanes happen to use.
"""
from collections import deque
from concurrent.futures import Future
import threading
import time

from app.cv.pipeline_metrics import MetricsBuffer


def model_lock(model):
    """The lock that serialises every call into one model instance."""
    lock = getattr(model, '_owner_lock', None)
    if lock is None:
        with _lock:
            lock = getattr(model, '_owner_lock', None)
            if lock is None:
                lock = threading.Lock()
                setattr(model, '_owner_lock', lock)
    return lock


class InferenceWorker:
    def __init__(self, capacity_per_camera=8):
        self.capacity = capacity_per_camera
        self._lanes = {}
        self._condition = threading.Condition()
        self._closed = False
        self._owner_threads = set()
        self.queue_ms, self.inference_ms = MetricsBuffer(), MetricsBuffer()

    def submit(self, camera, fn, *args, **kwargs):
        future = Future()
        with self._condition:
            if self._closed:
                raise RuntimeError('inference worker stopped')
            queue = self._lanes.get(camera)
            if queue is None:
                queue = self._lanes[camera] = deque()
                thread = threading.Thread(target=self._loop, args=(camera, queue), daemon=True,
                                          name=f'model-owner-{camera}')
                thread.start()
            if len(queue) >= self.capacity:
                raise RuntimeError('inference queue full')
            queue.append((future, fn, args, kwargs, time.perf_counter()))
            self._condition.notify_all()
        return future

    def run(self, camera, fn, *args, **kwargs):
        # A model call made from inside an owner thread runs inline: queueing
        # it behind the caller (or another lane waiting on this one) deadlocks.
        if threading.current_thread() in self._owner_threads:
            return fn(*args, **kwargs)
        return self.submit(camera, fn, *args, **kwargs).result()

    def _loop(self, camera, queue):
        with self._condition:
            self._owner_threads.add(threading.current_thread())
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or queue)
                if not queue:
                    return
                future, fn, args, kwargs, submitted = queue.popleft()
            if not future.set_running_or_notify_cancel():
                continue
            started = time.perf_counter()
            self.queue_ms.add((started-submitted)*1000)
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                future.set_exception(exc)
            else:
                future.set_result(result)
            finally:
                self.inference_ms.add((time.perf_counter()-started)*1000)

    def status(self):
        with self._condition:
            sizes = {str(k): len(v) for k, v in self._lanes.items()}
        return {'queues': sizes, 'capacity_per_camera': self.capacity,
                'queue_ms': {'p50': self.queue_ms.percentile(50), 'p95': self.queue_ms.percentile(95)},
                'inference_ms': {'p50': self.inference_ms.percentile(50), 'p95': self.inference_ms.percentile(95)}}

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()
            threads = list(self._owner_threads)
        for thread in threads:
            thread.join(4)


_worker = None
_lock = threading.Lock()


def model_owner():
    global _worker
    with _lock:
        if _worker is None:
            _worker = InferenceWorker()
        return _worker
