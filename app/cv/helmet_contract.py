"""Explicit model classes; absence of a detection is never a no-helmet label."""
from typing import Optional


def validate_helmet_classes(names):
    return isinstance(names, dict) and {'With Helmet', 'Without Helmet'}.issubset(set(names.values()))


def parse_mapping(mapping_str: str) -> Optional[dict]:
    """Parse mapping string "0=With Helmet,1=Without Helmet" → {0: 'With Helmet', 1: 'Without Helmet'}.
    Trả None nếu parse fail hoặc thiếu 2 key 'With Helmet' và 'Without Helmet'."""
    if not mapping_str:
        return None
    result = {}
    try:
        for part in mapping_str.split(','):
            part = part.strip()
            if '=' not in part:
                continue
            k, v = part.split('=', 1)
            result[int(k.strip())] = v.strip()
    except (ValueError, AttributeError):
        return None
    if 'With Helmet' not in result.values() or 'Without Helmet' not in result.values():
        return None
    return result


def validate_helmet_mapping(names, mapping_str: str) -> bool:
    """Phase 3 (Task 1): xác minh helmet class mapping khớp với weights file.

    - `names` là class_names dict của weights (vd {0: 'Without Helmet', 1: 'With Helmet'})
    - `mapping_str` là chuỗi mapping kỳ vọng (vd '0=With Helmet,1=Without Helmet')

    Trả True nếu mapping khớp chính xác (cùng index → cùng tên class).
    Sai mapping dẫn đến "Without Helmet" bị gán thành "With Helmet" hoặc ngược
    lại — nguy hiểm nhất trong các lỗi AI (silent wrong direction).
    """
    expected = parse_mapping(mapping_str)
    if expected is None:
        # Không có mapping để so sánh → coi như PASS (giữ backward-compat)
        return True
    if not isinstance(names, dict):
        return False
    for idx, label in expected.items():
        actual = names.get(idx)
        if actual is None or actual != label:
            return False
    return True
