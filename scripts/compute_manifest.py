#!/usr/bin/env python
"""Pin SHA256 cho file THỰC SỰ cần thiết để tái lập bản demo.

Không scan full repo (lâu + có file staging/lịch sử). Chỉ:
- app/ (mã backend đang dùng)
- frontend/src/ (mã React đang dùng)
- scripts/ (công cụ đang dùng)
- tasks/task-06-demo-2026-10-04/ (kế hoạch đợt 6)
- marketing/ (landing local)
- release/demo-2026-10-04/ (artefact bàn giao)
- frontend/index.html, package.json, requirements.txt, pytest.ini
- README.md, .gitignore
"""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path('.').resolve()
SKIP_BIG = {'.pt', '.onnx', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg',
            '.mp4', '.mov', '.webm', '.wav', '.mp3', '.db', '.sqlite',
            '.sqlite3', '.zip', '.gz', '.bz2', '.xz', '.7z'}
BIG_SIZE = 2 * 1024 * 1024  # 2 MB

# Pin các entry bắt buộc. Tự động thêm mọi file .py/.json/.md/.ps1/.sh/.toml/.ini/.yml/.yaml/.css/.html
# trong các thư mục dưới đây.
PIN_DIRS = [
    'app',
    'frontend/src',
    'scripts',
    'tasks/task-06-demo-2026-10-04',
    'marketing',
    'release/demo-2026-10-04',
    'tasks/task-05',  # chỉ file .md quan trọng
]
PIN_FILES = [
    'README.md', '.gitignore', 'frontend/index.html',
    'frontend/package.json', 'frontend/package-lock.json',
    'requirements.txt', 'pytest.ini', 'app/main.py', 'app/config.py',
    'Makefile', 'pyproject.toml',
]

EXCLUDE_FROM_DIRS = {
    'tasks/task-05': {'regression-*.xml', 'regression-*.json', 'regression-*.log',
                       'r*-focused-test.log', '*.diff', '*.head', '*.err',
                       'screenshot_*.png', '*.pyc', '__pycache__'},
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def keep(p: Path, rel: str) -> bool:
    if any(p.is_relative_to(ROOT / d) for d in PIN_DIRS):
        for src, globs in EXCLUDE_FROM_DIRS.items():
            if p.is_relative_to(ROOT / src):
                from fnmatch import fnmatch
                if any(fnmatch(rel, g) for g in globs):
                    return False
        return p.suffix.lower() not in {'.pyc'}
    return False


def main():
    files = []
    seen = set()
    for f in PIN_FILES:
        p = ROOT / f
        if p.exists() and p.is_file():
            rel = p.relative_to(ROOT).as_posix()
            try:
                files.append({'path': rel, 'sha256': sha256(p), 'size': p.stat().st_size})
            except OSError:
                continue
            seen.add(rel)
    for d in PIN_DIRS:
        root = ROOT / d
        if not root.exists():
            continue
        for p in root.rglob('*'):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT).as_posix()
            if rel in seen:
                continue
            if not keep(p, rel):
                continue
            if p.suffix.lower() in SKIP_BIG or p.stat().st_size > BIG_SIZE:
                continue
            try:
                files.append({'path': rel, 'sha256': sha256(p), 'size': p.stat().st_size})
            except OSError:
                continue
    files.sort(key=lambda x: x['path'])
    out = {
        'note': 'Pin SHA256 cho file quan trọng để tái lập demo. Scan có chọn lọc.',
        'count': len(files),
        'files': files,
    }
    outp = ROOT / 'release/demo-2026-10-04/RELEASE_MANIFEST.json'
    outp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'manifest: {len(files)} entries -> {outp}')


if __name__ == '__main__':
    main()