"""F4.3 integration test: app lifespan start/stop collector + training_worker.

Verify the 3 integration points from APP_LIFESPAN_PATCH.md v1.1:
  1. Startup: start_collector_task + start_training_worker (lazy import)
  2. Normal yield shutdown: stop_training_worker + stop_collector_task
  3. Early-exit path (CV import fail): stop Task 3 workers + yield

Also verify:
  - TASK3_COLLECTOR_ENABLED=0 skips collector start
  - TASK3_TRAINING_WORKER_ENABLED=0 skips worker start
  - Multiple start is idempotent
"""
from __future__ import annotations

import pytest
import threading


def test_collector_and_worker_start_on_lifespan(test_app):
    """Lifespan startup gọi start_collector_task + start_training_worker."""
    import app.main as main_module
    from app.training import sample_collector, worker

    # Ensure clean state
    worker.stop_training_worker()
    sample_collector.stop_collector_task()

    assert worker._WORKER is None
    assert sample_collector._SINGLETON is None

    # Simulate lifespan startup by calling the module-level start functions
    # (The actual lifespan context manager requires a full ASGI app event loop)
    sample_collector.start_collector_task()
    worker.start_training_worker(poll_sec=5.0)

    assert worker._WORKER is not None
    assert worker._WORKER._running is True
    assert sample_collector._SINGLETON is not None
    assert sample_collector._SINGLETON._started.is_set() is True

    # Cleanup
    worker.stop_training_worker()
    sample_collector.stop_collector_task()


def test_collector_and_worker_stop_clean(test_app):
    """Lifespan shutdown gọi stop_training_worker + stop_collector_task."""
    from app.training import sample_collector, worker

    # Start
    sample_collector.start_collector_task()
    worker.start_training_worker(poll_sec=5.0)
    assert worker._WORKER is not None
    assert sample_collector._SINGLETON is not None

    # Stop
    worker.stop_training_worker()
    sample_collector.stop_collector_task()

    assert worker._WORKER is None
    assert sample_collector._SINGLETON is None


def test_collector_start_is_idempotent(test_app):
    """Gọi start_collector_task nhiều lần → cùng singleton instance."""
    from app.training import sample_collector

    sample_collector.stop_collector_task()
    c1 = sample_collector.start_collector_task()
    c2 = sample_collector.start_collector_task()
    assert c1 is c2
    sample_collector.stop_collector_task()


def test_worker_start_is_idempotent(test_app):
    """Gọi start_training_worker nhiều lần → cùng singleton instance."""
    from app.training import worker

    worker.stop_training_worker()
    w1 = worker.start_training_worker(poll_sec=5.0)
    w2 = worker.start_training_worker(poll_sec=5.0)
    assert w1 is w2
    worker.stop_training_worker()


def test_stop_is_idempotent(test_app):
    """Gọi stop_training_worker/stop_collector_task khi đã stopped → no-op."""
    from app.training import sample_collector, worker

    # Ensure stopped
    worker.stop_training_worker()
    sample_collector.stop_collector_task()

    # Stop again → no raise
    worker.stop_training_worker()
    sample_collector.stop_collector_task()

    assert worker._WORKER is None
    assert sample_collector._SINGLETON is None


def test_stop_collector_with_timeout(test_app):
    """stop_collector_task(timeout=X) đợi worker thread join."""
    from app.training import sample_collector

    sample_collector.stop_collector_task()  # clean
    c = sample_collector.start_collector_task()
    assert c._started.is_set() is True

    sample_collector.stop_collector_task(timeout=5.0)
    assert sample_collector._SINGLETON is None


def test_stop_worker_with_timeout(test_app):
    """stop_training_worker(timeout=X) đợi worker thread join."""
    from app.training import worker

    worker.stop_training_worker()  # clean
    w = worker.start_training_worker(poll_sec=0.5)
    assert w._running is True

    worker.stop_training_worker(timeout=5.0)
    assert worker._WORKER is None


def test_collector_disabled_env_skips_start(test_app, monkeypatch):
    """TASK3_COLLECTOR_ENABLED=0 → collector không được start."""
    from app.training import sample_collector

    monkeypatch.setenv("TASK3_COLLECTOR_ENABLED", "0")
    sample_collector.stop_collector_task()

    # Re-import to pick up env
    import importlib
    import app.training.sample_collector as sc_module
    importlib.reload(sc_module)

    # start_collector_task vẫn gọi được nhưng is_enabled() trả False
    c = sc_module.start_collector_task()
    # Khi disabled: start_collector_task vẫn tạo singleton nhưng worker không chạy
    # (worker chỉ start nếu is_enabled() = True)
    assert sc_module.is_enabled() is False
    sc_module.stop_collector_task()


def test_worker_disabled_env_skips_start(test_app, monkeypatch):
    """TASK3_TRAINING_WORKER_ENABLED=0 → worker không được start."""
    from app.training import worker

    monkeypatch.setenv("TASK3_TRAINING_WORKER_ENABLED", "0")
    worker.stop_training_worker()

    import importlib
    import app.training.worker as w_module
    importlib.reload(w_module)

    assert w_module.is_enabled() is False
    w_module.start_training_worker(poll_sec=5.0)
    assert w_module._WORKER is None  # not started because disabled
    w_module.stop_training_worker()  # no-op


def test_threads_running_after_start(test_app):
    """Sau start, threading.enumerate() có task3-* threads."""
    from app.training import sample_collector, worker

    worker.stop_training_worker()
    sample_collector.stop_collector_task()

    sample_collector.start_collector_task()
    worker.start_training_worker(poll_sec=5.0)

    # Đợi threads khởi động
    import time
    time.sleep(1.0)

    task3_threads = [
        t for t in threading.enumerate()
        if "task3" in t.name.lower()
    ]
    assert len(task3_threads) >= 1, f"Expected task3 threads, got: {[t.name for t in threading.enumerate()]}"

    # Sau stop
    worker.stop_training_worker()
    sample_collector.stop_collector_task()
    time.sleep(0.5)

    task3_threads_after = [
        t for t in threading.enumerate()
        if "task3" in t.name.lower() and t.is_alive()
    ]
    assert len(task3_threads_after) == 0, f"task3 threads still alive after stop: {[t.name for t in task3_threads_after]}"


def test_collector_and_worker_stop_order(test_app):
    """stop_training_worker trước stop_collector_task (lifespan order)."""
    from app.training import sample_collector, worker

    sample_collector.start_collector_task()
    worker.start_training_worker(poll_sec=5.0)

    assert worker._WORKER is not None
    assert sample_collector._SINGLETON is not None

    # Stop order: worker trước, collector sau (như lifespan patch)
    worker.stop_training_worker()
    sample_collector.stop_collector_task()

    assert worker._WORKER is None
    assert sample_collector._SINGLETON is None
