#!/usr/bin/env python
"""Pin SHA256 cho file THỰC SỰ cần thiết để tái lập bản demo.

Không scan full repo (lâu + có file staging/lịch sử). Chỉ:
- app/ (mã backend đang dùng)
- frontend/src/ (mã React đang dùng)
- scripts/ (công cụ đang dùng)
- tasks/task-06-demo-2026-10-04/ (kế hoạch đợt 6)
- marketing/ (landing local)
- release/demo-2026-10-04/ (artefact bàn giao)
- frontend/dist/ (built assets cần cho HTTP serving)
- models/ (active weights .pt/.onnx)
- marketing/audio_clips/ (voice fallback clips nếu có)
- frontend/index.html, package.json, requirements.txt, pytest.ini
- README.md, .gitignore
"""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path('.').resolve()
# Bỏ qua file binary nặng không pin (datasets, recordings, backups).
SKIP_BIG = {'.pyc', '.db', '.sqlite', '.sqlite3', '.zip', '.gz', '.bz2', '.xz', '.7z',
            '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
# Pin weights .pt/.onnx + dist/ + audio clips (kể cả > 2MB) — cần thiết để
# tái lập demo runtime. KHÔNG bỏ qua các extension này.
PIN_EXTS_OVERRIDE = {'.pt', '.onnx', '.wav', '.mp3', '.m4a', '.ogg', '.flac',
                     '.mp4', '.mov', '.webm'}
# Dist/ + models/ file có thể > 2MB → bỏ qua BIG_SIZE cho các PIN_EXTS_OVERRIDE.
# Các dist asset (.js, .css) thường < 2MB.

PIN_DIRS = [
    'app',
    'frontend/src',
    'scripts',
    'tasks/task-06-demo-2026-10-04',
    'marketing',
    'release/demo-2026-10-04',
    'frontend/dist',
    'models',
    'marketing/audio_clips',
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
    'models': {'*.bak', '*.tmp'},
    'frontend/dist': {'*.map', '.vite/deps'},
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
        if p.suffix.lower() in SKIP_BIG:
            return False
        # Pin các extension override bất kể size; khác thì giới hạn 2MB.
        if p.suffix.lower() not in PIN_EXTS_OVERRIDE and p.stat().st_size > 2 * 1024 * 1024:
            return False
        return True
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
            # Bỏ self-hash: không pin chính manifest (tự tham chiếu)
            if rel.endswith('RELEASE_MANIFEST.json'):
                continue
            if not keep(p, rel):
                continue
            try:
                files.append({'path': rel, 'sha256': sha256(p), 'size': p.stat().st_size})
            except OSError:
                continue
    files.sort(key=lambda x: x['path'])
    out = {
        'note': 'Pin SHA256 cho file quan trọng để tái lập demo. Scan có chọn lọc, pin weights/dist/audio clips.',
        'count': len(files),
        'files': files,
    }
    outp = ROOT / 'release/demo-2026-10-04/RELEASE_MANIFEST.json'
    outp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    # Verify sau freeze
    verify_count = sum(1 for f in files if f['size'] > 0)
    print(f'manifest: {len(files)} entries ({verify_count} verified) -> {outp}')

    # Verify mọi entry còn tồn tại + hash khớp
    bad = []
    for f in files:
        p = ROOT / f['path']
        if not p.exists():
            bad.append((f['path'], 'missing'))
            continue
        try:
            if sha256(p) != f['sha256']:
                bad.append((f['path'], 'hash_mismatch'))
        except OSError:
            bad.append((f['path'], 'io_error'))
    if bad:
        print('VERIFY FAIL:')
        for p, why in bad:
            print(f'  {p}: {why}')
        raise SystemExit(1)
    print('manifest: verified all entries OK')


if __name__ == '__main__':
    main()