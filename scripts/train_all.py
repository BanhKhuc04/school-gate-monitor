"""
Train lại các model của dự án, dùng TỐI ĐA GPU, tự so sánh và chỉ thay model khi
model mới TỐT HƠN THẬT (model cũ luôn được backup thành *.bak).

Chạy (từ thư mục dự án, đã bật venv, máy có GPU NVIDIA):
    python scripts/train_all.py                 # train tất cả job có dữ liệu
    python scripts/train_all.py --only ocr      # chỉ model đọc ký tự biển số
    python scripts/train_all.py --check         # chỉ kiểm tra dữ liệu + GPU, không train

Các job:
  ocr     Model đọc TỪNG KÝ TỰ biển số (YOLO 36 lớp 0-9, A-Z) từ datasets/plate_char_ocr.
          Sau khi train, đo tỉ lệ đọc ĐÚNG CẢ BIỂN trên tập val và so với EasyOCR trên
          cùng tập — chỉ cài vào models/plate_ocr_best.pt nếu đọc đúng nhiều hơn EasyOCR.
          (app/cv/ocr.py tự dùng file này nếu có, EasyOCR làm dự phòng.)
  plate   Fine-tune model phát hiện biển số từ models/plate_best.pt trên
          datasets/vn_plate_detect, tăng augment thu nhỏ (biển ở xa camera). Chỉ thay
          nếu mAP50-95 trên val KHÔNG giảm VÀ bắt biển nhỏ (cao 24-32px) KHÔNG kém hơn.
  helmet  Fine-tune model mũ bảo hiểm — chỉ chạy khi có datasets/helmet/data.yaml
          (YOLO format, lớp có/không mũ). Chỉ thay nếu mAP50-95 tốt hơn.

"Tối đa GPU": batch tự tính theo % VRAM (--vram, mặc định 0.8 = 80%), AMP (FP16),
nạp sẵn ảnh vào RAM nếu đủ, số worker = số nhân CPU (tối đa 8).
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

DATASETS = ROOT / "datasets"
MODELS = ROOT / "models"
RUNS = ROOT / "runs" / "train"

CHAR_NAMES = {i: str(i) for i in range(10)} | {10 + i: chr(ord('A') + i) for i in range(26)}


# ─── tiện ích ─────────────────────────────────────────────────────────────────

def gpu_info():
    import torch
    if not torch.cuda.is_available():
        return None
    props = torch.cuda.get_device_properties(0)
    return f"{props.name} ({props.total_memory / 1024 ** 3:.1f} GB)"


def resolve_dataset(name: str) -> Path | None:
    """Thư mục dataset có images/train + images/val. Ưu tiên datasets/<name> trong
    repo, sau đó đường dẫn `path:` ghi trong data.yaml (vd. D:/Work/...)."""
    import yaml
    candidates = [DATASETS / name]
    yaml_path = DATASETS / name / "data.yaml"
    if yaml_path.exists():
        p = (yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}).get("path")
        if p and p != ".":
            candidates.append(Path(p))
    for c in candidates:
        if (c / "images" / "train").is_dir() and (c / "images" / "val").is_dir():
            return c.resolve()
    return None


def write_data_yaml(dataset_dir: Path, names: dict, out: Path) -> Path:
    """data.yaml với `path` tuyệt đối — data.yaml trong repo dùng path '.'/ổ D: của
    máy cũ, ultralytics hiểu '.' là thư mục datasets mặc định của nó, không phải repo."""
    import yaml
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump({
        "path": str(dataset_dir), "train": "images/train", "val": "images/val",
        "names": {int(k): str(v) for k, v in names.items()},
    }, allow_unicode=True), encoding="utf-8")
    return out


def train_kwargs(args, imgsz: int) -> dict:
    import psutil
    gpu = gpu_info()
    workers = min(8, os.cpu_count() or 2)
    # Nạp ảnh vào RAM nếu máy dư RAM (nhanh hơn đọc đĩa mỗi epoch), không thì cache đĩa
    cache = "ram" if psutil.virtual_memory().available > 12 * 1024 ** 3 else "disk"
    return dict(
        imgsz=imgsz,
        device=0 if gpu else "cpu",
        batch=args.vram if gpu else 8,   # 0<batch<1 = dùng chừng đó % VRAM (AutoBatch)
        workers=workers,
        cache=cache,
        amp=True,
        cos_lr=True,
        close_mosaic=5,
        project=str(RUNS),
        exist_ok=True,
        plots=True,
        verbose=False,
    )


def backup_and_install(src: Path, dst: Path):
    if dst.exists():
        bak = dst.with_suffix(dst.suffix + f".{time.strftime('%Y%m%d_%H%M%S')}.bak")
        shutil.copy2(dst, bak)
        print(f"   backup model cũ → {bak.name}")
    shutil.copy2(src, dst)
    print(f"   ĐÃ CÀI {src} → {dst}")


def val_map(model_path: Path, data_yaml: Path, imgsz: int) -> float:
    from ultralytics import YOLO
    import torch
    metrics = YOLO(str(model_path)).val(data=str(data_yaml), imgsz=imgsz, batch=16, plots=False,
                                        device=0 if torch.cuda.is_available() else "cpu", verbose=False)
    return float(metrics.box.map)  # mAP50-95


# ─── job: OCR ký tự biển số ───────────────────────────────────────────────────

def plate_text_from_labels(label_file: Path) -> str:
    from app.cv.ocr import group_into_lines
    boxes = []
    for line in label_file.read_text().split("\n"):
        parts = line.split()
        if len(parts) != 5:
            continue
        cls, cx, cy, _w, h = int(parts[0]), *map(float, parts[1:])
        boxes.append((CHAR_NAMES.get(cls, "?"), 1.0, cx, cy, h))
    return "".join(group_into_lines(boxes))


def plate_accuracy(dataset_dir: Path, read_fn, limit: int | None = None) -> tuple[float, int]:
    import cv2
    images = sorted((dataset_dir / "images" / "val").glob("*.*"))[:limit]
    correct = total = 0
    for img_path in images:
        label = dataset_dir / "labels" / "val" / (img_path.stem + ".txt")
        if not label.exists():
            continue
        truth = plate_text_from_labels(label)
        img = cv2.imread(str(img_path))
        if not truth or img is None:
            continue
        total += 1
        correct += read_fn(img) == truth
    return (correct / total if total else 0.0), total


def job_ocr(args) -> str:
    from ultralytics import YOLO
    from app.cv import ocr

    dataset = resolve_dataset("plate_char_ocr")
    if dataset is None:
        return "BỎ QUA — không thấy datasets/plate_char_ocr/images/{train,val} (giải nén yolo_plate_ocr_dataset.zip vào đó)"
    data_yaml = write_data_yaml(dataset, CHAR_NAMES, RUNS / "_data" / "plate_char_ocr.yaml")
    if args.check:
        return f"SẴN SÀNG — {dataset}"

    print(f"\n=== [ocr] Train model đọc ký tự trên {dataset}")
    model = YOLO("yolov8n.pt")
    model.train(data=str(data_yaml), epochs=args.epochs or 120, patience=25, name="plate_ocr",
                # biển số không lật ngang được (chữ bị ngược), xoay/nghiêng nhẹ như camera thật
                fliplr=0.0, degrees=5.0, shear=2.0, perspective=0.0005, scale=0.3, mosaic=0.5,
                **train_kwargs(args, imgsz=320))
    best = RUNS / "plate_ocr" / "weights" / "best.pt"

    trained = YOLO(str(best))

    def read_trained(img):
        crop = ocr._prepare_crop(img)
        return ocr._read_with_char_model(trained, crop)["full"] if crop is not None else ""

    def read_easyocr(img):
        crop = ocr._prepare_crop(img)
        return ocr._read_with_easyocr(crop)["full"] if crop is not None else ""

    trained_acc, n = plate_accuracy(dataset, read_trained)
    easy_acc, _ = plate_accuracy(dataset, read_easyocr)
    print(f"   Đọc đúng CẢ BIỂN trên {n} ảnh val: model mới {trained_acc:.1%} | EasyOCR {easy_acc:.1%}")
    if trained_acc > easy_acc:
        backup_and_install(best, MODELS / "plate_ocr_best.pt")
        return f"ĐÃ CÀI — đọc đúng cả biển {trained_acc:.1%} (EasyOCR {easy_acc:.1%})"
    return f"KHÔNG CÀI — model mới {trained_acc:.1%} không hơn EasyOCR {easy_acc:.1%}"


# ─── job: phát hiện biển số ───────────────────────────────────────────────────

def small_plate_recall(model_path: Path, imgsz: int, heights=(32, 24)) -> int:
    """Số lần model bắt được biển (10 ảnh biển thật × mỗi chiều cao trong heights)
    khi biển chỉ cao vài chục px trong khung 1280x720 — đúng tình huống xe ở xa
    camera cổng (điểm yếu lớn nhất đo được của model hiện tại)."""
    import cv2
    import numpy as np
    from app.cv.detector import HelmetPlateDetector
    det = HelmetPlateDetector(str(model_path), conf_threshold=0.25, imgsz=imgsz)
    hits = 0
    for f in sorted((ROOT / "data" / "samples" / "plates").glob("*.jpg")):
        img = cv2.imread(str(f))
        h, w = img.shape[:2]
        for plate_h in heights:
            pw = round(w * plate_h / h)
            canvas = np.full((720, 1280, 3), 90, np.uint8)
            canvas[500:500 + plate_h, 700:700 + pw] = cv2.resize(img, (pw, plate_h))
            hits += bool(det.detect(canvas))
    return hits


def job_plate(args) -> str:
    from ultralytics import YOLO

    dataset = resolve_dataset("vn_plate_detect")
    if dataset is None:
        return "BỎ QUA — không thấy datasets/vn_plate_detect/images/{train,val} (hoặc đường dẫn trong data.yaml)"
    data_yaml = write_data_yaml(dataset, {0: "plate"}, RUNS / "_data" / "vn_plate_detect.yaml")
    if args.check:
        return f"SẴN SÀNG — {dataset}"

    current = MODELS / "plate_best.pt"
    print(f"\n=== [plate] Fine-tune {current.name} trên {dataset}")
    model = YOLO(str(current))
    model.train(data=str(data_yaml), epochs=args.epochs or 40, patience=10, name="plate_detect",
                scale=0.9,  # thu nhỏ mạnh → giống biển ở xa camera (điểm yếu của model hiện tại)
                **train_kwargs(args, imgsz=args.imgsz))
    best = RUNS / "plate_detect" / "weights" / "best.pt"

    old_map, new_map = val_map(current, data_yaml, args.imgsz), val_map(best, data_yaml, args.imgsz)
    old_small, new_small = small_plate_recall(current, 1280), small_plate_recall(best, 1280)
    print(f"   mAP50-95 val: cũ {old_map:.4f} | mới {new_map:.4f}")
    print(f"   Biển nhỏ (cao 32px + 24px) bắt được: cũ {old_small}/20 | mới {new_small}/20")
    if new_map >= old_map - 0.002 and new_small >= old_small:
        backup_and_install(best, current)
        return f"ĐÃ CÀI — mAP50-95 {old_map:.4f}→{new_map:.4f}, biển nhỏ {old_small}→{new_small}/20"
    return f"KHÔNG CÀI — mAP50-95 {old_map:.4f}→{new_map:.4f}, biển nhỏ {old_small}→{new_small}/20 (không tốt hơn)"


# ─── job: mũ bảo hiểm ─────────────────────────────────────────────────────────

def job_helmet(args) -> str:
    import yaml
    from ultralytics import YOLO
    from app.cv.detector import helmet_state

    src_yaml = DATASETS / "helmet" / "data.yaml"
    dataset = resolve_dataset("helmet")
    if dataset is None or not src_yaml.exists():
        return "BỎ QUA — chưa có datasets/helmet (data.yaml + images/{train,val} + labels/{train,val})"
    names = (yaml.safe_load(src_yaml.read_text(encoding="utf-8")) or {}).get("names") or {}
    if isinstance(names, list):
        names = dict(enumerate(names))
    if not any(helmet_state(str(n)) for n in names.values()):
        return f"BỎ QUA — lớp trong datasets/helmet/data.yaml không phải có/không mũ: {names}"
    data_yaml = write_data_yaml(dataset, names, RUNS / "_data" / "helmet.yaml")
    if args.check:
        return f"SẴN SÀNG — {dataset}"

    current = MODELS / "helmet_best.pt"
    base = str(current) if current.exists() and any(
        helmet_state(n) for n in YOLO(str(current)).names.values()) else "yolov8n.pt"
    print(f"\n=== [helmet] Fine-tune {base} trên {dataset}")
    YOLO(base).train(data=str(data_yaml), epochs=args.epochs or 60, patience=15, name="helmet",
                     **train_kwargs(args, imgsz=args.imgsz))
    best = RUNS / "helmet" / "weights" / "best.pt"
    new_map = val_map(best, data_yaml, args.imgsz)
    old_map = val_map(current, data_yaml, args.imgsz) if base == str(current) else -1.0
    print(f"   mAP50-95 val: cũ {old_map:.4f} | mới {new_map:.4f}")
    if new_map > old_map:
        backup_and_install(best, current)
        return f"ĐÃ CÀI — mAP50-95 {old_map:.4f}→{new_map:.4f}"
    return f"KHÔNG CÀI — mAP50-95 mới {new_map:.4f} không hơn cũ {old_map:.4f}"


JOBS = {"ocr": job_ocr, "plate": job_plate, "helmet": job_helmet}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default="ocr,plate,helmet", help="danh sách job, vd. ocr,plate")
    parser.add_argument("--epochs", type=int, default=None, help="số epoch (mặc định theo từng job)")
    parser.add_argument("--imgsz", type=int, default=640, help="cỡ ảnh train cho plate/helmet")
    parser.add_argument("--vram", type=float, default=0.8, help="tỉ lệ VRAM dùng cho batch (0.5-0.9)")
    parser.add_argument("--check", action="store_true", help="chỉ kiểm tra dữ liệu + GPU")
    parser.add_argument("--cpu", action="store_true", help="cho phép train bằng CPU (rất chậm)")
    args = parser.parse_args()

    gpu = gpu_info()
    print("=" * 70)
    print(f" TRAIN MODEL — GPU: {gpu or 'KHÔNG CÓ (CPU)'}  |  VRAM dùng: {args.vram:.0%}")
    print("=" * 70)
    if not gpu and not args.check and not args.cpu:
        print("Không thấy GPU NVIDIA (torch bản CPU?). Chạy  python scripts/prepare_demo.py  để xem cách\n"
              "cài torch bản CUDA, hoặc thêm --cpu nếu thật sự muốn train bằng CPU (rất chậm).")
        return 1

    summary = []
    for name in [j.strip() for j in args.only.split(",") if j.strip()]:
        if name not in JOBS:
            print(f"Job không tồn tại: {name} (có: {', '.join(JOBS)})")
            return 1
        t0 = time.time()
        try:
            result = JOBS[name](args)
        except Exception as e:
            import traceback
            traceback.print_exc()
            result = f"LỖI — {e}"
        summary.append((name, result, time.time() - t0))

    print("\n" + "=" * 70)
    print(" KẾT QUẢ")
    for name, result, secs in summary:
        print(f"   {name:7s} {result}  ({secs / 60:.1f} phút)")
    print("=" * 70)
    print(" Khởi động lại backend để dùng model mới.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
