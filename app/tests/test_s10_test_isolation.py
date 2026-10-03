"""
S10/F02: Test isolation — sys.modules pollution phải được cleanup fixture restore.

Plan Pre-E3: Thay gán trực tiếp `sys.modules["cv2"]` (và quên xoá) bằng
fixture `restore_sys_modules` có teardown hoàn trả. Verify:
1. Trong test: gán tạm → sys.modules["fake_module"] tồn tại.
2. Sau test: fixture cleanup → fake_module phải bị xoá.
3. Env vars bị set trong test cũng phải được khôi phục.
"""

import os
import sys
import types
import pytest

import app.tests.conftest as cf_module


def _drive_fixture(fn):
    """Gọi fixture generator (chạy setup + yield + teardown) thủ công."""
    gen = fn.__wrapped__()
    value = next(gen)
    return gen, value


def test_restore_sys_modules_removes_added_module():
    """Setup một module giả, fixture teardown phải xoá nó."""
    assert "fake_module_s10" not in sys.modules
    gen, _ = _drive_fixture(cf_module.restore_sys_modules)
    # Trong fixture (đã setup)
    sys.modules["fake_module_s10"] = types.SimpleNamespace()
    assert "fake_module_s10" in sys.modules
    # Teardown
    try:
        next(gen)
    except StopIteration:
        pass
    assert "fake_module_s10" not in sys.modules, (
        "Fixture restore_sys_modules phải xoá module được thêm trong test"
    )


def test_restore_sys_modules_restores_overwritten_module():
    """Nếu test ghi đè sys.modules["json"] (real), teardown phải khôi phục."""
    import json as real_json
    gen, _ = _drive_fixture(cf_module.restore_sys_modules)
    # Test ghi đè
    sys.modules["json"] = types.SimpleNamespace()
    assert sys.modules["json"] is not real_json
    # Cleanup
    try:
        next(gen)
    except StopIteration:
        pass
    # Phục hồi
    assert sys.modules["json"] is real_json, (
        "restore_sys_modules phải khôi phục module bị ghi đè"
    )


def test_restore_sys_modules_restores_env_vars():
    """Env var set trong test phải được khôi phục về giá trị ban đầu.

    Dùng 1 trong các key được tracked (`WS_ALLOWED_ORIGINS`) để test fixture.
    """
    test_key = "WS_ALLOWED_ORIGINS"
    original = os.environ.get(test_key)
    gen, _ = _drive_fixture(cf_module.restore_sys_modules)
    # Test set giá trị
    os.environ[test_key] = "polluted_by_s10_test"
    assert os.environ.get(test_key) == "polluted_by_s10_test"
    # Cleanup
    try:
        next(gen)
    except StopIteration:
        pass
    assert os.environ.get(test_key) == original, (
        f"Env var {test_key} phải được teardown khôi phục về {original!r}"
    )


def test_stub_cv2_helper_is_idempotent(restore_sys_modules):
    """stub_cv2_module() gọi 2 lần không phá nếu module đã có."""
    cf_module.stub_cv2_module()
    before = sys.modules.get("cv2")
    cf_module.stub_cv2_module()
    after = sys.modules.get("cv2")
    assert before is after, (
        "stub_cv2_module phải idempotent — không ghi đè nếu 'cv2' đã có"
    )


def test_stub_cv2_does_not_overwrite_real_cv2():
    """Nếu cv2 thật đã import → stub KHÔNG được ghi đè nó."""
    import cv2  # noqa: F401  # đảm bảo cv2 thật có trong sys.modules
    real_cv2 = sys.modules["cv2"]
    cf_module.stub_cv2_module()
    assert sys.modules["cv2"] is real_cv2, (
        "stub_cv2_module KHÔNG được ghi đè cv2 thật"
    )
