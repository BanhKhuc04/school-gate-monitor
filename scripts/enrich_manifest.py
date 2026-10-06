#!/usr/bin/env python
"""Append git + build state info to RELEASE_MANIFEST.json."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path('.').resolve()
mf = ROOT / 'release/demo-2026-10-04/RELEASE_MANIFEST.json'
data = json.loads(mf.read_text(encoding='utf-8'))


def run(cmd):
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return (r.stdout or '').strip()


data['git'] = {
    'commit': run(['git', 'rev-parse', 'HEAD']),
    'short': run(['git', 'rev-parse', '--short', 'HEAD']),
    'branch': run(['git', 'branch', '--show-current']),
    'dirty': bool(run(['git', 'status', '--porcelain'])),
    'porcelain_count': len([x for x in run(['git', 'status', '--porcelain']).splitlines() if x.strip()]),
}

# Backend/frontend versions
data['build'] = {
    'python': run(['venv/Scripts/python.exe', '--version']) or run(['python', '--version']),
    'node': run(['node', '--version']),
    'platform': os.name,
}

# Audio wiring point
data['audio'] = {
    'helper': 'frontend/src/utils/alertAudio.js (createAlertAudio)',
    'lease': 'frontend/src/utils/useAudioLease.js + app/api/audio_lease.py',
    'speak': 'frontend/src/utils/speak.js (localService filter)',
    'banner': 'frontend/src/components/AlertBanner.jsx (wired through helper)',
}

# VPS probe evidence
data['vps'] = {
    'host': '103.101.162.111',
    'port22': 'reachable (probe 2026-10-03 ~22:54 UTC+7)',
    'port80': 'reachable, nginx/1.18.0 Ubuntu, currently serving EduPortal landing',
    'port443': 'fail',
    'ssh': 'denied (no key) — pending_access',
    'decision': 'no deploy (would overwrite existing site + no key)',
}

# Test counts
data['tests'] = {
    'r0_full': '1214 passed, 1 skipped, 0 failed (regression-r0.xml)',
    'r8_r9': '1277 passed, 2 skipped, 0 failed (~443s)',
    'focused': '152 passed, 1 skipped, 0 failed (R2-R14 focused, 19.28s)',
    'r14_eof': '15/15 clips clean EOF, 216 FPS avg',
}

# Disk snapshot
data['disk'] = {
    'note': 'Xem Get-Volume C/D khi bàn giao; D phải ≥ 30 GiB.',
}

mf.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
print('manifest updated:', mf)
print(f"  files: {data['count']}, commit: {data['git']['short']}, dirty: {data['git']['dirty']}")