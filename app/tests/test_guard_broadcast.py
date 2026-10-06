"""Bounded gate distribution, using fake pipelines and real async tasks."""
import asyncio
from collections import deque
import pytest


@pytest.fixture(autouse=True)
def enable_mocked_cv_endpoints(monkeypatch):
    monkeypatch.setenv('CV_PIPELINES_ENABLED', '1')


def test_broadcast_two_viewers_and_isolated_gate(monkeypatch):
    import app.cv.pipeline as pipeline
    import app.api.guard as guard
    sources = {'main':deque(), 'secondary':deque()}
    class FakePipeline:
        def __init__(self, gate): self.source = sources[gate]
        def get_alert(self): return self.source.popleft() if self.source else None
    monkeypatch.setattr(pipeline, 'get_pipeline', lambda gate_id: FakePipeline(gate_id))
    async def exercise():
        a = guard._subscribe('main', 1)
        b = guard._subscribe('main', 2)
        other = guard._subscribe('secondary', 3)
        try:
            sources['main'].append({'event_id':'shared', 'event_version':1})
            x, y = await asyncio.wait_for(asyncio.gather(a.get(), b.get()), 2)
            assert x == y == {'event_id':'shared','event_version':1,'gate_id':'main'}
            assert other.empty()
            assert len(guard._gate_pumps) == 2
        finally:
            tasks=list(guard._gate_pumps.values())
            guard._gate_clients.clear()
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            guard._gate_pumps.clear()
    asyncio.run(exercise())


def test_slow_viewer_does_not_block_fast_viewer(monkeypatch):
    import app.cv.pipeline as pipeline
    import app.api.guard as guard
    source=deque([{'event_id':'new'}])
    class FakePipeline:
        def get_alert(self): return source.popleft() if source else None
    monkeypatch.setattr(pipeline, 'get_pipeline', lambda gate_id: FakePipeline())
    async def exercise():
        slow=guard._subscribe('main', 1)
        fast=guard._subscribe('main', 2)
        for n in range(64): slow.put_nowait({'event_id':str(n)})
        try:
            assert (await asyncio.wait_for(fast.get(), 2))['event_id'] == 'new'
            assert await asyncio.wait_for(slow.get(), 2) is None
            assert slow.maxsize == fast.maxsize == 64
        finally:
            tasks=list(guard._gate_pumps.values())
            guard._gate_clients.clear()
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            guard._gate_pumps.clear()
    asyncio.run(exercise())
