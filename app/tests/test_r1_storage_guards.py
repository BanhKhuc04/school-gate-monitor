"""R1 guards — preflight disk + upload cap + safe export path.

Mục đích: bảo vệ các điểm vào tác vụ nặng (export/import ZIP, upload) khỏi
đầy ổ đĩa / path traversal / upload quá lớn.

Test dùng fixture QA env từ app/tests/conftest.py — chạy trong .qa/.
"""
from __future__ import annotations

import io
import os
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ===========================================================================
# 1. require_space integration cho _safe_extract
# ===========================================================================

def test_safe_extract_blocks_when_disk_too_small(tmp_path, monkeypatch):
    """Khi available disk < expected output + reserve → raise ImportBlockedError.

    Dùng monkeypatch require_space để giả lập disk đầy — không phụ thuộc vào
    máy test thật có bao nhiêu dung lượng.
    """
    from app.training import import_portable
    zp = tmp_path / "big.zip"
    # ZIP giả với 1 file 500 KB
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("hello.bin", b"x" * 500_000)
    dest = tmp_path / "dest"
    dest.mkdir()

    def fake_require_space(path, expected_bytes=0, reserve_bytes=10 * 1024 ** 3):
        raise ValueError("không đủ dung lượng: giả lập test")

    # Patch ở module gốc (import_portable dùng `from app.storage_budget import require_space`
    # nên cần patch trên app.storage_budget.require_space, không phải import_portable.require_space).
    import app.storage_budget as sb
    monkeypatch.setattr(sb, "require_space", fake_require_space)
    with zipfile.ZipFile(zp) as zf:
        with pytest.raises(import_portable.ImportBlockedError) as exc:
            import_portable._safe_extract(zf, dest)
    assert "không đủ dung lượng" in str(exc.value).lower()


def test_safe_extract_passes_when_disk_enough(tmp_path):
    """ZIP nhỏ, disk đủ → extract OK."""
    from app.training import import_portable
    zp = tmp_path / "small.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("hello.txt", b"hi")
    dest = tmp_path / "dest"
    dest.mkdir()
    with zipfile.ZipFile(zp) as zf:
        import_portable._safe_extract(zf, dest)
    assert (dest / "hello.txt").read_bytes() == b"hi"


# ===========================================================================
# 2. Cap upload size + require_space trên API import
# ===========================================================================

def test_save_upload_streaming_caps_at_limit(tmp_path):
    """_save_upload_streaming raise HTTPException 413 khi upload vượt limit."""
    from fastapi import HTTPException, UploadFile
    from app.api.training_portable import _save_upload_streaming
    # Upload 2 MB vào file với limit 1 MB
    payload = b"x" * (2 * 1024 * 1024)
    fake_file = io.BytesIO(payload)
    upload = UploadFile(filename="test.bin", file=fake_file)
    dest = tmp_path / "cap.bin"
    with pytest.raises(HTTPException) as exc:
        _save_upload_streaming(upload, dest, max_bytes=1024 * 1024)
    assert exc.value.status_code == 413
    # Cleanup: file dở dang phải được unlink
    assert not dest.exists() or dest.stat().st_size <= 1024 * 1024


def test_save_upload_streaming_passes_under_limit(tmp_path):
    """_save_upload_streaming pass khi upload dưới limit, ghi đủ bytes."""
    from fastapi import UploadFile
    from app.api.training_portable import _save_upload_streaming
    payload = b"x" * 1024
    fake_file = io.BytesIO(payload)
    upload = UploadFile(filename="test.bin", file=fake_file)
    dest = tmp_path / "ok.bin"
    written = _save_upload_streaming(upload, dest, max_bytes=4096)
    assert written == 1024
    assert dest.read_bytes() == payload


# ===========================================================================
# 3. Safe export path — chống path traversal ra ngoài exports root
# ===========================================================================

def test_safe_export_path_blocks_absolute_path(monkeypatch, tmp_path):
    """Absolute path bị chặc."""
    from fastapi import HTTPException
    from app.api import training_portable
    monkeypatch.setattr(training_portable, "_exports_root",
                        lambda: tmp_path / "exports_root")
    with pytest.raises(HTTPException) as exc:
        training_portable._safe_export_path("C:/Windows/System32/evil.zip")
    assert exc.value.status_code == 400


def test_safe_export_path_blocks_traversal(monkeypatch, tmp_path):
    """Path traversal (../) ra ngoài exports root → 400."""
    from fastapi import HTTPException
    from app.api import training_portable
    monkeypatch.setattr(training_portable, "_exports_root",
                        lambda: tmp_path / "exports_root")
    with pytest.raises(HTTPException) as exc:
        training_portable._safe_export_path("../../etc/passwd.zip")
    assert exc.value.status_code == 400
    assert "ngoài thư mục exports" in str(exc.value.detail)


def test_safe_export_path_accepts_relative_safe(monkeypatch, tmp_path):
    """Relative path an toàn trong exports root → trả resolved absolute path."""
    from app.api import training_portable
    root = tmp_path / "exports_root"
    root.mkdir()
    monkeypatch.setattr(training_portable, "_exports_root", lambda: root)
    out = training_portable._safe_export_path("my_dataset_v1.zip")
    assert out.is_absolute()
    assert str(out).startswith(str(root.resolve()))


def test_safe_export_path_rejects_empty():
    """output_path rỗng → 400."""
    from fastapi import HTTPException
    from app.api import training_portable
    with pytest.raises(HTTPException) as exc:
        training_portable._safe_export_path("")
    assert exc.value.status_code == 400