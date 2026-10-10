"""Preflight for large artifacts. All sizes are bytes, on the target volume."""
from pathlib import Path
import shutil

GIB = 1024**3


def available_bytes(path):
    target = Path(path).resolve()
    while not target.exists():
        target = target.parent
    return shutil.disk_usage(target).free


def require_space(path, expected_bytes=0, reserve_bytes=10*GIB):
    free = available_bytes(path)
    if expected_bytes < 0 or free < reserve_bytes+expected_bytes:
        raise ValueError(f'Không đủ dung lượng: cần output {expected_bytes/GIB:.2f} GiB và dự phòng {reserve_bytes/GIB:.0f} GiB; còn {free/GIB:.2f} GiB')
    return free


def storage_status(path):
    free = available_bytes(path)
    return {'free_gib': round(free/GIB, 2), 'warning': free < 15*GIB,
            'heavy_work_blocked': free < 10*GIB}
