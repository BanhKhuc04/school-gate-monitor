"""Bounded round-robin model owner shared by both cameras."""
from collections import OrderedDict, deque
from concurrent.futures import Future
import threading
import time

from app.cv.pipeline_metrics import MetricsBuffer


class InferenceWorker:
    def __init__(self, capacity_per_camera=8):
        self.capacity = capacity_per_camera
        self._queues = OrderedDict()
        self._condition = threading.Condition()
        self._closed = False
        self.queue_ms, self.inference_ms = MetricsBuffer(), MetricsBuffer()
        self._thread = threading.Thread(target=self._loop, daemon=True, name='model-owner')
        self._thread.start()

    def submit(self, camera, fn, *args, **kwargs):
        future = Future()
        with self._condition:
            if self._closed:
                raise RuntimeError('inference worker stopped')
            queue = self._queues.setdefault(camera, deque())
            if len(queue) >= self.capacity:
                raise RuntimeError('inference queue full')
            queue.append((future, fn, args, kwargs, time.perf_counter()))
            self._condition.notify()
        return future

    def run(self, camera, fn, *args, **kwargs):
        if threading.current_thread() is self._thread:
            return fn(*args, **kwargs)
        return self.submit(camera, fn, *args, **kwargs).result()

    def _loop(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._queues)
                if not self._queues:
                    return
                camera, queue = self._queues.popitem(last=False)
                future, fn, args, kwargs, submitted = queue.popleft()
                if queue:
                    self._queues[camera] = queue
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
            sizes = {str(k): len(v) for k, v in self._queues.items()}
        return {'queues': sizes, 'capacity_per_camera': self.capacity,
                'queue_ms': {'p50': self.queue_ms.percentile(50), 'p95': self.queue_ms.percentile(95)},
                'inference_ms': {'p50': self.inference_ms.percentile(50), 'p95': self.inference_ms.percentile(95)}}

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        self._thread.join(4)


_worker = None
_lock = threading.Lock()


def model_owner():
    global _worker
    with _lock:
        if _worker is None:
            _worker = InferenceWorker()
        return _worker
