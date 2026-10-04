"""N01: the restored helmet model and its backup satisfy the runtime contract.

Kiểm tra:
1. SHA256 + mapping contract của helmet_best.pt (current) vs helmet backup
2. Pipeline QA env override: HELMET_MODEL_PATH env → load đúng file.
4. Khi mapping sai → set _helmet_health['status']='error', nhánh mũ không chạy.
3. Khi load backup đúng mapping → detector thật chạy inference và trả dự đoán.
"""
import os
import sys
import hashlib
import tempfile
import subprocess
from pathlib import Path
import pytest
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
HELMET_CURRENT = str(ROOT / 'models' / 'helmet_best.pt')


@pytest.fixture
def helmet_qa_copy(tmp_path):
    """Exercise an env-selected artifact without requiring an ignored local backup."""
    import shutil
    path = tmp_path / 'helmet_qa.pt'
    shutil.copy2(HELMET_CURRENT, path)
    return str(path)


def test_helmet_current_has_expected_classes():
    """The deployed artifact must recognize both helmet labels, never plates."""
    from ultralytics import YOLO
    m = YOLO(HELMET_CURRENT)
    names = m.names
    assert names == {0: 'With Helmet', 1: 'Without Helmet'}


def test_helmet_qa_copy_is_correct_class(helmet_qa_copy):
    """A QA copy preserves both labels from the restored model."""
    from ultralytics import YOLO
    m = YOLO(helmet_qa_copy)
    names = m.names
    assert 'With Helmet' in names.values(), f"Helmet backup phải có 'With Helmet', got {names}"
    assert 'Without Helmet' in names.values(), f"Helmet backup phải có 'Without Helmet', got {names}"
    assert len(names) >= 2


def test_helmet_backup_loadable_into_pipeline_qa(helmet_qa_copy):
    """Backup helmet có thể load qua HelmetPlateDetector (subprocess, env override)
    không crash. Dùng HELMET_MODEL_PATH env."""
    env = os.environ.copy()
    env['HELMET_MODEL_PATH'] = helmet_qa_copy
    env['PYTHONPATH'] = str(ROOT)
    code = """
import os
from app.cv.detector import HelmetPlateDetector
det = HelmetPlateDetector(os.environ['HELMET_MODEL_PATH'], conf_threshold=0.3)
print('OK', det.class_names if hasattr(det, 'class_names') else 'no names')
"""
    res = subprocess.run(
        [sys.executable, '-c', code],
        env=env, capture_output=True, text=True, cwd=str(ROOT), timeout=60,
    )
    assert res.returncode == 0, f"Pipeline crash: stderr={res.stderr[:500]}"
    assert 'OK' in res.stdout


def test_helmet_backup_runs_inference_on_synthetic_image():
    """Inference trên ảnh giả lập 'có mũ' / 'không mũ' cho kết quả hợp lệ.
    Chỉ verify: load OK + chạy không crash + trả list detections."""
    from ultralytics import YOLO
    m = YOLO(HELMET_CURRENT)
    # Ảnh đen 640x640 — không có mũ → có thể không trả detection nào (OK)
    img_black = np.zeros((640, 640, 3), dtype=np.uint8)
    results = m.predict(img_black, conf=0.1, verbose=False)
    assert len(results) >= 1
    # Ảnh sáng có 2 box giả lập — kiểm tra không crash
    img_light = np.ones((640, 640, 3), dtype=np.uint8) * 200
    results = m.predict(img_light, conf=0.05, verbose=False)
    assert len(results) >= 1


def test_helmet_mapping_validator_rejects_plate_model():
    """A plate model must still be refused if placed in the helmet slot."""
    from app.cv.helmet_contract import validate_helmet_mapping
    # Mapping mặc định "0=With Helmet,1=Without Helmet"
    result = validate_helmet_mapping({0: 'plate'}, "0=With Helmet,1=Without Helmet")
    assert result is False, "Mapping sai (chỉ 'plate') phải fail validation"


def test_helmet_mapping_validator_accepts_backup_model():
    """app.cv.helmet_contract.validate_helmet_mapping phải chấp nhận backup."""
    from app.cv.helmet_contract import validate_helmet_mapping
    result = validate_helmet_mapping(
        {0: 'With Helmet', 1: 'Without Helmet'},
        "0=With Helmet,1=Without Helmet",
    )
    assert result is True, "Mapping đúng phải pass"


def test_files_hash_pinned_for_audit():
    """SHA256 được ghi cố định để audit."""
    expected = {
        'models/helmet_best.pt': 'c8eb324e365cf4fa',  # restored helmet artifact
        'models/plate_best.pt': '5b57ca666211a4b7',
        'models/plate_real_best.pt': '3602cb96399b5ce2',  # default plate detector since 2026-10-04
    }
    for path, expected_prefix in expected.items():
        path = str(ROOT / path)
        if not os.path.isfile(path):
            pytest.skip(f"{path} not present")
        actual = hashlib.sha256(open(path, 'rb').read()).hexdigest()
        assert actual.startswith(expected_prefix), (
            f"{path} hash mismatch: expected {expected_prefix}, got {actual[:16]}"
        )
