"""Sinh notebooks/kaggle_mirror_train.ipynb — train model gương + gán nháp vòng sau.

Nhúng nguyên văn scripts/prepare_mirror_dataset.py và scripts/prelabel_mirror.py
bằng %%writefile, nên notebook chạy trên Kaggle không cần clone repo.
Sửa 2 script đó thì chạy lại: python scripts/training/build_mirror_notebook.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _notebook_builder import make_cell, make_notebook, save_notebook  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'notebooks' / 'kaggle_mirror_train.ipynb'

INTRO = '''# Train model gương chiếu hậu + gán nháp vòng sau

**Chuẩn bị (1 lần mỗi vòng):** tạo 1 Kaggle Dataset (Datasets → New Dataset) gồm 3 file:

| File | Lấy ở đâu |
|---|---|
| `1_anh_xe_may.zip` | file ảnh đã dùng để tạo task CVAT |
| `VN_street_motorbike_300_image_labels.json` | file thông tin bộ ảnh |
| `cvat_export.zip` | CVAT → Actions → Export task dataset → **CVAT for images 1.1** (đổi tên thành `cvat_export.zip`) |

Kaggle tự giải nén file zip — không sao, notebook đọc được cả 2 dạng.

**Chạy:** Add Input → chọn dataset trên → Settings: **Accelerator = GPU T4 x2**, **Internet = On** → **Run All** (~20–40 phút).

**Kết quả** (tab Output, bên phải):
- `mirror_best.pt` — model gương
- `prelabel_cvat11.zip` — nhãn nháp: CVAT → Actions → **Upload annotations** → **CVAT 1.1** → duyệt & sửa
'''

FIND_INPUTS = '''import glob, os

def find(*patterns):
    for pat in patterns:
        hits = sorted(glob.glob(f'/kaggle/input/**/{pat}', recursive=True))
        if hits:
            return hits[0]
    raise FileNotFoundError(f'Không thấy {patterns} trong /kaggle/input — kiểm tra lại dataset đã Add Input chưa')

LABELS = find('*image_labels*.json')
IMAGES = find('1_anh_xe_may.zip', '1_anh_xe_may')
CVAT = find('cvat_export*.zip', 'cvat_export*')
print('labels:', LABELS); print('images:', IMAGES); print('cvat  :', CVAT)
'''

CONVERT = '''from prepare_mirror_dataset import cvat_to_yolo, held_out

stats = cvat_to_yolo(CVAT, LABELS, '/kaggle/working/vn_mirror', IMAGES)
print(stats)
if stats['val'] == 0:
    print('ĐỀ THI (gán tay các ảnh này trước):')
    print('\\n'.join(held_out(LABELS)))
    raise SystemExit('Chưa có ảnh đề thi nào được gán nhãn — gán tay các ảnh ở danh sách trên rồi export lại')
if stats['train'] < 20:
    raise SystemExit(f"Mới có {stats['train']} ảnh train — gán thêm cho đủ ít nhất 20 ảnh rồi chạy lại")
'''

TRAIN = '''from ultralytics import YOLO

model = YOLO('yolo11n.pt')
model.train(
    data='/kaggle/working/vn_mirror/data.yaml',
    epochs=80, imgsz=320, batch=32, device=0,
    fliplr=0.5,          # 1 lớp `mirror`, trái/phải tính bằng hình học nên lật ngang vẫn đúng
    patience=20, project='/kaggle/working/runs', name='mirror', exist_ok=True,
)
'''

EVALUATE = '''import shutil

best = '/kaggle/working/runs/mirror/weights/best.pt'
shutil.copy(best, '/kaggle/working/mirror_best.pt')
metrics = YOLO(best).val(data='/kaggle/working/vn_mirror/data.yaml', imgsz=320, verbose=False)
p, r, m50 = metrics.box.mp, metrics.box.mr, metrics.box.map50
print(f'Trên ĐỀ THI: precision={p:.2f}  recall={r:.2f}  mAP50={m50:.2f}')
print('precision = trong các box model vẽ, bao nhiêu là gương thật')
print('recall    = trong các gương thật, model tìm được bao nhiêu')
print('Mục tiêu trước khi dùng thật: mAP50 >= 0.80 trên ảnh quay tại cổng.')
'''

PRELABEL = '''import subprocess, sys

subprocess.run([sys.executable, 'prelabel_mirror.py', '--model', '/kaggle/working/mirror_best.pt',
                '--cvat', CVAT, '--images', IMAGES, '--labels', LABELS,
                '--out', '/kaggle/working/prelabel_cvat11.zip'], check=True)
print('Tải prelabel_cvat11.zip ở tab Output → CVAT → Actions → Upload annotations → CVAT 1.1')
'''


def writefile(path: Path) -> str:
    return f'%%writefile {path.name}\n' + path.read_text(encoding='utf-8')


def build() -> dict:
    scripts = ROOT / 'scripts'
    return make_notebook([
        make_cell(INTRO, 'markdown'),
        make_cell('!pip install -q ultralytics==8.4.168'),
        make_cell(writefile(scripts / 'prepare_mirror_dataset.py')),
        make_cell(writefile(scripts / 'prelabel_mirror.py')),
        make_cell(FIND_INPUTS),
        make_cell(CONVERT),
        make_cell(TRAIN),
        make_cell(EVALUATE),
        make_cell(PRELABEL),
    ])


if __name__ == '__main__':
    save_notebook(build(), OUT)
    print(OUT)
