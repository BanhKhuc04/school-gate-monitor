"""Sinh gói giọng đọc cảnh báo tiếng Việt OFFLINE (frontend/public/voice/vi/*.mp3).

Máy giám sát chạy trên router không có internet và Windows không có giọng vi-VN
cài sẵn: giọng Việt của Chrome/Edge đều đọc qua mạng nên mất tiếng khi offline.
Script này (chạy 1 lần khi CÓ mạng) thu các câu nhắc cố định + số + chữ cái của
biển số; frontend/src/utils/offlineVoice.js ghép lại thành câu cảnh báo.

    pip install edge-tts
    python scripts/tools/build_voice_pack.py
"""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import edge_tts

OUT = Path(__file__).resolve().parents[2] / 'frontend' / 'public' / 'voice' / 'vi'
VOICE = 'vi-VN-HoaiMyNeural'

# Giữ đúng chữ với buildAlertMessage (frontend/src/utils/alertAudio.js).
PHRASES = {
    'p_helmet': 'Vui lòng đội mũ.',
    'p_walk': 'Vui lòng dắt xe.',
    'p_helmet_walk': 'Không đội mũ, vui lòng dắt xe.',
    'p_mirror': 'Mời kiểm tra gương trái.',
    'p_riders': 'Mời kiểm tra số người trên xe.',
    'p_register': 'Mời kiểm tra đăng ký xe.',
    'p_unreadable': 'Không đọc được biển số.',
}
LETTERS = {'A': 'a', 'B': 'bê', 'C': 'xê', 'D': 'dê', 'E': 'e', 'F': 'ép', 'G': 'giê', 'H': 'hát',
           'I': 'i', 'J': 'gi', 'K': 'ca', 'L': 'lờ', 'M': 'mờ', 'N': 'nờ', 'O': 'o', 'P': 'pê',
           'Q': 'quy', 'R': 'rờ', 'S': 'ét', 'T': 'tê', 'U': 'u', 'V': 'vê', 'W': 'vê kép',
           'X': 'ích', 'Y': 'i dài', 'Z': 'dét'}


def clips():
    items = dict(PHRASES)
    items.update({f'n{n}': str(n) for n in range(100)})          # 0-99 đọc trọn
    items.update({f'h{d}': f'{d}00' for d in range(1, 10)})       # "hai trăm"
    items['linh'] = 'linh'
    items.update({f'l_{k}': v for k, v in LETTERS.items()})
    return items


def trim(path, pad_start=.04, pad_end=.08):
    """Cắt khoảng lặng dài ở đầu/cuối để ghép số liền mạch (cần ffmpeg, bỏ qua nếu không có).

    Chỉ bỏ khoảng lặng >= 0.15 s chạm đầu/cuối file, giữ đệm: silenceremove cắt
    luôn phụ âm nhẹ ("ích" còn 0.07 s).
    """
    if not shutil.which('ffmpeg'):
        return
    info = subprocess.run(['ffmpeg', '-v', 'info', '-i', str(path), '-af', 'silencedetect=n=-50dB:d=0.15',
                           '-f', 'null', '-'], capture_output=True, text=True).stderr
    duration = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
                                     'csv=p=0', str(path)], capture_output=True, text=True).stdout or 0)
    starts = [float(l.split('silence_start: ')[1].split()[0]) for l in info.splitlines() if 'silence_start: ' in l]
    ends = [float(l.split('silence_end: ')[1].split()[0]) for l in info.splitlines() if 'silence_end: ' in l]
    begin = next((e for s, e in zip(starts, ends) if s <= .01), 0.0)
    finish = next((s for s in reversed(starts) if s > begin and (len(ends) < len(starts) or s >= ends[-1] - .01
                                                                  or abs(ends[-1] - duration) < .05)), duration)
    begin, finish = max(0, begin - pad_start), min(duration, finish + pad_end)
    if finish - begin < .1:
        return
    tmp = path.with_suffix('.tmp.mp3')
    done = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-af',
                           f'atrim=start={begin:.3f}:end={finish:.3f},asetpts=PTS-STARTPTS', '-b:a', '48k', str(tmp)])
    if done.returncode == 0 and tmp.stat().st_size > 500:
        tmp.replace(path)
    else:
        tmp.unlink(missing_ok=True)


# +8 dB then a limiter at ~-1 dBFS: gate PCs drive small speakers in a noisy
# yard; the raw voice sat at -16..-19 dB mean and was hard to hear.
LOUDNESS_FILTER = 'volume=8dB,alimiter=limit=0.89:level=disabled'


def louden(path):
    if not shutil.which('ffmpeg'):
        return
    tmp = path.with_suffix('.tmp.mp3')
    done = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-af', LOUDNESS_FILTER,
                           '-b:a', '64k', str(tmp)])
    if done.returncode == 0 and tmp.stat().st_size > 500:
        tmp.replace(path)
    else:
        tmp.unlink(missing_ok=True)


async def synth(key, text, sem):
    path = OUT / f'{key}.mp3'
    if path.exists() and path.stat().st_size > 500:
        return key, 'cached'
    async with sem:
        for attempt in range(8):  # the service drops requests now and then
            try:
                await edge_tts.Communicate(text, VOICE).save(str(path))
                if path.stat().st_size > 500:
                    trim(path)
                    louden(path)
                    return key, 'ok'
            except Exception:
                pass
            await asyncio.sleep(1 + attempt)
    return key, 'FAILED'


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items = clips()
    sem = asyncio.Semaphore(4)
    results = await asyncio.gather(*(synth(k, t, sem) for k, t in items.items()))
    failed = [k for k, s in results if s == 'FAILED']
    manifest = {'voice': VOICE, 'phrases': PHRASES, 'letters': sorted(LETTERS),
                'clips': sorted(k for k, s in results if s != 'FAILED')}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    size = sum(p.stat().st_size for p in OUT.glob('*.mp3'))
    print(f'{len(items) - len(failed)}/{len(items)} clips, {size / 1e6:.2f} MB -> {OUT}')
    if failed:
        raise SystemExit(f'failed: {failed} — chạy lại script (bỏ qua file đã có)')


if __name__ == '__main__':
    import sys
    if '--louden-existing' in sys.argv:  # one-off for packs built before LOUDNESS_FILTER
        for clip in sorted(OUT.glob('*.mp3')):
            louden(clip)
        print('loudened', len(list(OUT.glob('*.mp3'))), 'clips')
    else:
        asyncio.run(main())
