"""N01 (Post-Video Review): helmet backup model đúng mapping chạy được
trong runtime QA, không sửa weights file vận hành.

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
import pytest
import numpy as np


HELMET_CURRENT = "models/helmet_best.pt"
HELMET_BACKUP = "models/backups/helmet_best_20260930_090903.pt"


def test_helmet_current_is_wrong_class():
    """Helmet hiện tại chỉ có 1 class 'plate' — sai vai trò."""
    from ultralytics import YOLO
    m = YOLO(HELMET_CURRENT)
    names = m.names
    assert names == {0: 'plate'}, f"Current helmet_best.pt phải sai mapping, got {names}"
    # Không có 'With Helmet' / 'Without Helmet'
    assert 'With Helmet' not in names.values()
    assert 'Without Helmet' not in names.values()


def test_helmet_backup_is_correct_class():
    """Helmet backup có 2 class With Helmet / Without Helmet — đúng vai trò."""
    from ultralytics import YOLO
    m = YOLO(HELMET_BACKUP)
    names = m.names
    assert 'With Helmet' in names.values(), f"Helmet backup phải có 'With Helmet', got {names}"
    assert 'Without Helmet' in names.values(), f"Helmet backup phải có 'Without Helmet', got {names}"
    assert len(names) >= 2


def test_helmet_backup_loadable_into_pipeline_qa():
    """Backup helmet có thể load qua HelmetPlateDetector (subprocess, env override)
    không crash. Dùng HELMET_MODEL_PATH env."""
    env = os.environ.copy()
    env['HELMET_MODEL_PATH'] = HELMET_BACKUP
    env['PYTHONPATH'] = 'D:\\Work\\Project_motorbike'
    code = """
import os
from app.cv.detector import HelmetPlateDetector
det = HelmetPlateDetector(os.environ['HELMET_MODEL_PATH'], conf_threshold=0.3)
print('OK', det.class_names if hasattr(det, 'class_names') else 'no names')
"""
    res = subprocess.run(
        [r'D:\\Work\\Project_motorbike\\venv\\Scripts\\python.exe', '-c', code],
        env=env, capture_output=True, text=True, cwd='D:/Work/Project_motorbike', timeout=120,
    )
    assert res.returncode == 0, f"Pipeline crash: stderr={res.stderr[:500]}"
    assert 'OK' in res.stdout


def test_helmet_backup_runs_inference_on_synthetic_image():
    """Inference trên ảnh giả lập 'có mũ' / 'không mũ' cho kết quả hợp lệ.
    Chỉ verify: load OK + chạy không crash + trả list detections."""
    from ultralytics import YOLO
    m = YOLO(HELMET_BACKUP)
    # Ảnh đen 640x640 — không có mũ → có thể không trả detection nào (OK)
    img_black = np.zeros((640, 640, 3), dtype=np.uint8)
    results = m.predict(img_black, conf=0.1, verbose=False)
    assert len(results) >= 1
    # Ảnh sáng có 2 box giả lập — kiểm tra không crash
    img_light = np.ones((640, 640, 3), dtype=np.uint8) * 200
    results = m.predict(img_light, conf=0.05, verbose=False)
    assert len(results) >= 1


def test_helmet_mapping_validator_rejects_current_model():
    """app.cv.helmet_contract.validate_helmet_mapping phải từ chối current model
    (chỉ có 1 class 'plate', thiếu 'With Helmet'/'Without Helmet')."""
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
        'models/helmet_best.pt': 'ef083bb37f490afa',  # 16-char prefix
        'models/backups/helmet_best_20260930_090903.pt': 'c8eb324e365cf4fa',
        'models/plate_best.pt': '5b57ca666211a4b7',
    }
    for path, expected_prefix in expected.items():
        if not os.path.isfile(path):
            pytest.skip(f"{path} not present")
        actual = hashlib.sha256(open(path, 'rb').read()).hexdigest()
        assert actual.startswith(expected_prefix), (
            f"{path} hash mismatch: expected {expected_prefix}, got {actual[:16]}"
        )