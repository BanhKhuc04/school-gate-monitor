"""Selftest cho r8_inspect_audit — verify script CLI chạy đúng với audit JSON.

Test thật với audit fixture ở tasks/task-05/dataset_audit.json (nếu có) và
fallback audit fixture tối thiểu (được copy sang tmp + monkeypatch path).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _make_minimal_audit() -> dict:
    """Audit JSON tối thiểu — đủ schema để script in ra các section."""
    return {
        "schema_version": 1,
        "datasets": {
            "vn_plate_detect": {
                "summary": {
                    "images": 0, "valid": 0, "invalid": 0, "by_split": {},
                    "objects_by_class": {}, "duplicate_groups": 0,
                    "cross_split_duplicates": 0, "orphan_labels": 0,
                    "holdout_status": "pending_human_group_curation",
                },
                "duplicates": [],
                "records": [],
            },
            "plate_char_ocr": {
                "summary": {
                    "images": 0, "valid": 0, "invalid": 0, "by_split": {},
                    "objects_by_class": {}, "duplicate_groups": 0,
                    "cross_split_duplicates": 0, "orphan_labels": 0,
                    "holdout_status": "pending_human_group_curation",
                },
                "duplicates": [],
                "records": [],
            },
            "helmet_detect": {
                "summary": {
                    "images": 0, "valid": 0, "invalid": 0, "by_split": {},
                    "objects_by_class": {}, "duplicate_groups": 0,
                    "cross_split_duplicates": 0, "orphan_labels": 0,
                    "holdout_status": "pending_human_group_curation",
                },
                "duplicates": [],
                "records": [],
            },
        },
    }


def test_inspect_with_real_audit():
    """Chạy với audit JSON thật (nếu có) — kiểm tra output chứa 4 group trùng."""
    audit_path = ROOT / "tasks" / "task-05" / "dataset_audit.json"
    if not audit_path.exists():
        # Bỏ qua nếu audit chưa có; test_minimal cover case audit tồn tại
        import pytest
        pytest.skip("dataset_audit.json không có trong workspace")
    proc = subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts" / "r8_inspect_audit.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr}"
    out = proc.stdout
    assert "DETECT DUPLICATES" in out
    assert "Group 1:" in out
    assert "Group 4:" in out
    assert "OCR SUMMARY" in out
    assert "HELMET SUMMARY" in out
    assert "pending_human_group_curation" in out
    # 4 group trùng theo DATA_REPORT.md
    assert out.count("Group ") == 4


def test_inspect_minimal_audit(tmp_path):
    """Audit fixture tối thiểu → script vẫn in đầy đủ các section."""
    fixture = _make_minimal_audit()
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(fixture), encoding="utf-8")
    # Patch AUDIT path trong script qua monkey-patch sys.modules.
    # Cách đơn giản: chạy subprocess với cwd ở tmp và sửa script tạm thời.
    script = ROOT / "scripts" / "r8_inspect_audit.py"
    # Tạo script copy với AUDIT khác để không phụ thuộc audit workspace
    patched = tmp_path / "r8_inspect_audit_patched.py"
    content = script.read_text(encoding="utf-8")
    content = content.replace(
        'AUDIT = Path("tasks/task-05/dataset_audit.json")',
        f'AUDIT = Path("{audit_path.as_posix()}")',
    )
    patched.write_text(content, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-B", str(patched)], cwd=ROOT,
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr}"
    out = proc.stdout
    # Section phải có cho dù không có duplicate/proposal
    assert "DETECT DUPLICATES" in out
    assert "OCR SUMMARY" in out
    assert "HELMET SUMMARY" in out
    assert "rare chars" in out  # vẫn in key
    # helmet summary hiện images=0
    assert "'images': 0" in out


def test_missing_audit_exits_nonzero(tmp_path):
    """Khi audit JSON không tồn tại → exit 1 + message rõ."""
    script = ROOT / "scripts" / "r8_inspect_audit.py"
    patched = tmp_path / "r8_inspect_audit_patched.py"
    content = script.read_text(encoding="utf-8")
    content = content.replace(
        'AUDIT = Path("tasks/task-05/dataset_audit.json")',
        'AUDIT = Path("/nonexistent/audit.json")',
    )
    patched.write_text(content, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-B", str(patched)], cwd=ROOT,
        capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 1
    assert "Missing" in proc.stderr or "/nonexistent" in proc.stderr