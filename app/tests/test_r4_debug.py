"""Verify that monkeypatch on model_owner propagates AND that the fixture
contract matches production (returns object with `.names`, not raw string).

Trước đây mock fixture trả string "FAKE" — production detector expect
object có `.names`. Sửa fixture trả MagicMock có `.names` để test debug
đi qua QA pass mà không cần sửa detector production.

Đây là test debug nội bộ (không thuộc full regression R0–R9), được chạy
riêng trong focused test debug pass."""
import numpy as np
import pytest

from unittest.mock import MagicMock


def test_monkeypatch_owner_persists(monkeypatch):
    from app.cv import detector as detector_mod

    fake_owner = MagicMock()
    # Contract đúng: production trả object có .names (vd YOLO model),
    # KHÔNG trả raw string.
    fake_owner.run = MagicMock(return_value=MagicMock(names={0: "plate"}))
    monkeypatch.setattr("app.cv.detector.model_owner", lambda: fake_owner)

    # Should be patched now
    assert detector_mod.model_owner() is fake_owner
    bootstrap = detector_mod.model_owner().run("bootstrap", lambda x: x)
    assert bootstrap.names == {0: "plate"}

    # Now test that HelmetPlateDetector init uses the patched model_owner
    monkeypatch.setattr("app.cv.detector.YOLO", lambda *a, **kw: MagicMock(names={0: "plate"}))

    det = detector_mod.HelmetPlateDetector("/fake.pt", conf_threshold=0.25)
    # The model attribute should be whatever fake_owner.run returned for "bootstrap"
    assert det.model is not None
    assert hasattr(det.model, "names")
    # Verify fake_owner.run was called once for "bootstrap"
    assert any(call.args[0] == "bootstrap" for call in fake_owner.run.call_args_list)