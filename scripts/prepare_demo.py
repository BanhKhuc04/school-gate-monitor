"""
Chuẩn bị máy chạy demo — kiểm tra + tự sửa mọi thứ cần thiết, in bảng kết quả rõ ràng.

Chạy (từ thư mục dự án, đã bật venv):
    python scripts/prepare_demo.py           # kiểm tra + tự sửa (cần mạng lần đầu)
    python scripts/prepare_demo.py --quick   # chỉ kiểm tra nhanh, không tải gì

Làm gì:
  1. GPU: torch có thấy GPU NVIDIA không — có card mà torch bản CPU thì in lệnh cài bản CUDA
  2. Model mũ bảo hiểm: models/helmet_best.pt phải có lớp "có mũ / không mũ". Sai/thiếu →
     tìm file đúng trong models/ (kể cả *.bak), không có thì tải bản gốc từ HuggingFace
     (iam-tsr/yolov8n-helmet-detection), kiểm tra lớp rồi mới cài vào
  3. Model biển số, model người/xe (yolov8n/yolov8s), model tư thế, trọng số EasyOCR —
     tải sẵn để lúc demo không phải chờ tải (và chạy được khi không có mạng)
  4. File .env: chưa có thì tạo từ .env.example kèm JWT_SECRET_KEY ngẫu nhiên
  5. Tự kiểm tra: phát hiện + đọc 1 biển số thật, phát hiện người trong ảnh mẫu
"""
import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # yolov8n.pt... được ultralytics tải vào thư mục hiện tại — phải là gốc dự án

HELMET_HF_REPO = "iam-tsr/yolov8n-helmet-detection"
MODELS = ROOT / "models"

results: list[tuple[str, bool, str]] = []


def report(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(f"  [{'OK ' if ok else 'LỖI'}] {name}" + (f" — {detail}" if detail else ""))


def model_classes(path: Path) -> list[str]:
    from ultralytics import YOLO
    return [str(n) for n in YOLO(str(path)).names.values()]


def is_helmet_model(path: Path) -> bool:
    from app.cv.detector import helmet_state
    try:
        return any(helmet_state(n) for n in model_classes(path))
    except Exception:
        return False


# ─── 1. GPU ───────────────────────────────────────────────────────────────────

def check_gpu():
    print("\n[1] GPU")
    import torch
    has_nvidia = shutil.which("nvidia-smi") is not None and subprocess.run(
        ["nvidia-smi", "-L"], capture_output=True, text=True).returncode == 0
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
        report("GPU", True, f"{name} ({vram:.1f} GB VRAM), torch {torch.__version__} — hệ thống sẽ chạy FP16 trên GPU")
    elif has_nvidia:
        report("GPU", False,
               f"máy CÓ card NVIDIA nhưng torch {torch.__version__} là bản CPU → đang KHÔNG dùng GPU. Sửa:\n"
               "        pip install --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cu126\n"
               "        (lỗi thì thử cu128 hoặc cu124 thay cho cu126)")
    else:
        report("GPU", True, "không có GPU NVIDIA — chạy CPU (chậm hơn nhưng vẫn đủ demo)")


# ─── 2. Model mũ bảo hiểm ─────────────────────────────────────────────────────

def download_helmet_from_hf(dest: Path) -> str:
    """Tải file .pt từ repo HuggingFace về dest. Trả về tên file đã tải."""
    api = f"https://huggingface.co/api/models/{HELMET_HF_REPO}"
    with urllib.request.urlopen(api, timeout=30) as resp:
        info = json.load(resp)
    files = [s["rfilename"] for s in info.get("siblings", []) if s["rfilename"].endswith(".pt")]
    if not files:
        raise RuntimeError(f"repo {HELMET_HF_REPO} không có file .pt")
    files.sort(key=lambda f: (0 if "best" in f else 1, len(f)))
    url = f"https://huggingface.co/{HELMET_HF_REPO}/resolve/main/{files[0]}"
    print(f"      tải {url} ...")
    urllib.request.urlretrieve(url, dest)
    return files[0]


def fix_helmet_model(quick: bool):
    print("\n[2] Model mũ bảo hiểm (models/helmet_best.pt)")
    target = MODELS / "helmet_best.pt"
    if target.exists() and is_helmet_model(target):
        report("Model mũ bảo hiểm", True, f"lớp: {model_classes(target)}")
        return
    if target.exists():
        print(f"      file hiện tại KHÔNG phải model mũ (lớp: {model_classes(target)})")
    if quick:
        report("Model mũ bảo hiểm", False, "sai/thiếu — chạy  python scripts/prepare_demo.py  (không --quick) để tự sửa")
        return

    # 2a. File đúng có sẵn trên máy (vd. bản backup trước khi bị ghi đè nhầm)
    for cand in sorted(MODELS.glob("*.pt*")):
        if cand.name == target.name or not cand.is_file():
            continue
        if is_helmet_model(cand):
            if target.exists():
                target.replace(MODELS / "helmet_best.pt.wrong")
            shutil.copy2(cand, target)
            report("Model mũ bảo hiểm", True, f"dùng file có sẵn {cand.name} (lớp: {model_classes(target)})")
            return

    # 2b. Tải bản gốc từ HuggingFace
    tmp = MODELS / "helmet_download.tmp"
    try:
        name = download_helmet_from_hf(tmp)
        if not is_helmet_model(tmp):
            raise RuntimeError(f"file tải về ({name}) không có lớp mũ bảo hiểm: {model_classes(tmp)}")
        if target.exists():
            target.replace(MODELS / "helmet_best.pt.wrong")
        tmp.replace(target)
        report("Model mũ bảo hiểm", True, f"đã tải {HELMET_HF_REPO}/{name} (lớp: {model_classes(target)})")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        report("Model mũ bảo hiểm", False,
               f"không tải được ({e}). Tự tải tay file .pt tại https://huggingface.co/{HELMET_HF_REPO} "
               "rồi lưu thành models/helmet_best.pt. Trong lúc chờ, hệ thống vẫn chạy (biển số, người, xe) "
               "nhưng KHÔNG bắt được lỗi không đội mũ")


# ─── 3. Các model còn lại + EasyOCR ───────────────────────────────────────────

def prefetch_models(quick: bool):
    print("\n[3] Model biển số / người-xe / tư thế / OCR")
    from app.config import PLATE_MODEL_PATH, PERSON_MODEL_PATH, POSE_MODEL_PATH, PLATE_OCR_MODEL_PATH, DEVICE

    try:
        names = model_classes(Path(PLATE_MODEL_PATH))
        report("Model biển số", any("plate" in n.lower() for n in names), f"lớp: {names}")
    except Exception as e:
        report("Model biển số", False, f"không nạp được {PLATE_MODEL_PATH}: {e}")

    wanted = {PERSON_MODEL_PATH, POSE_MODEL_PATH, "yolov8n.pt"}
    for name in sorted(wanted):
        if quick and not Path(name).exists():
            report(f"Model {name}", False, "chưa tải — chạy không --quick khi có mạng")
            continue
        try:
            from ultralytics import YOLO
            YOLO(name)
            report(f"Model {name}", True, "sẵn sàng")
        except Exception as e:
            ok = name != PERSON_MODEL_PATH or Path("yolov8n.pt").exists()
            report(f"Model {name}", ok, f"không tải được ({e})" + (" — sẽ tự dùng yolov8n.pt" if ok else ""))

    if Path(PLATE_OCR_MODEL_PATH).exists():
        report("Model đọc ký tự biển số", True, f"{PLATE_OCR_MODEL_PATH} (dùng trước, EasyOCR dự phòng)")
    else:
        print("      (chưa có models/plate_ocr_best.pt — đọc biển số bằng EasyOCR. Train: python scripts/train_all.py)")

    has_weights = (Path.home() / ".EasyOCR" / "model" / "craft_mlt_25k.pth").exists()
    if quick and not has_weights:
        report("EasyOCR", False, "chưa tải trọng số — chạy không --quick khi có mạng")
        return
    try:
        from app.cv.ocr import _get_reader
        _get_reader()
        report("EasyOCR", True, f"sẵn sàng (gpu={DEVICE == 'cuda'})")
    except Exception as e:
        report("EasyOCR", False, f"không khởi tạo được: {e}")


# ─── 4. .env ──────────────────────────────────────────────────────────────────

def ensure_env():
    print("\n[4] File cấu hình .env")
    env = ROOT / ".env"
    if not env.exists():
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        text = text.replace("JWT_SECRET_KEY=\n", f"JWT_SECRET_KEY={secrets.token_hex(32)}\n")
        env.write_text(text, encoding="utf-8")
        report(".env", True, "đã tạo từ .env.example + JWT_SECRET_KEY ngẫu nhiên")
        return
    has_key = any(line.startswith("JWT_SECRET_KEY=") and line.strip() != "JWT_SECRET_KEY="
                  for line in env.read_text(encoding="utf-8").splitlines())
    report(".env", has_key, "có JWT_SECRET_KEY" if has_key else "JWT_SECRET_KEY còn trống — điền theo README Bước 5")


# ─── 5. Tự kiểm tra trên ảnh thật ─────────────────────────────────────────────

def self_test():
    print("\n[5] Tự kiểm tra trên ảnh thật")
    import difflib
    import cv2
    import numpy as np
    from app.config import (PLATE_MODEL_PATH, PERSON_MODEL_PATH, PLATE_CONF_THRESHOLD,
                            DETECT_WIDTH, DETECT_HEIGHT, DETECT_IMGSZ)
    from app.cv.detector import HelmetPlateDetector, Detection
    from app.cv.ocr import read_plate_detailed
    from app.cv.plate_voter import PlateVoter

    # Đi đúng đường của pipeline: detect ở ảnh thu nhỏ → quy đổi box → PlateVoter cắt + OCR
    sample = ROOT / "data" / "samples" / "plates" / "3xemay373.jpg"  # biển 59-K1 650.72
    truth = "59K165072"
    try:
        canvas = np.full((720, 1280, 3), 90, np.uint8)
        canvas[560:630, 1000:1095] = cv2.resize(cv2.imread(str(sample)), (95, 70))
        det = HelmetPlateDetector(PLATE_MODEL_PATH, conf_threshold=PLATE_CONF_THRESHOLD, imgsz=DETECT_IMGSZ)
        plates = det.detect(cv2.resize(canvas, (DETECT_WIDTH, DETECT_HEIGHT)))
        if not plates:
            report("Phát hiện biển số", False, "model biển số không thấy biển trong ảnh mẫu")
        else:
            sx, sy = 1280 / DETECT_WIDTH, 720 / DETECT_HEIGHT
            x1, y1, x2, y2 = plates[0].bbox
            box = Detection("plate", plates[0].confidence,
                            (round(x1 * sx), round(y1 * sy), round(x2 * sx), round(y2 * sy)))
            text = PlateVoter(60, 2.5, 2, 0.55).read(canvas, box, read_plate_detailed).text
            # Sai tối đa 1 ký tự vẫn tính là chuỗi chạy đúng (OCR thật trên biển nhỏ
            # đôi khi nhầm 1↔7) — pipeline còn gom phiếu qua nhiều khung hình
            close = difflib.SequenceMatcher(None, text, truth).ratio() >= 0.85
            report("Phát hiện + đọc biển số", close,
                   f"đọc được '{text}' (đúng: {truth})" + ("" if text == truth or not close else " — lệch 1 ký tự, chấp nhận"))
    except Exception as e:
        report("Phát hiện + đọc biển số", False, str(e))

    try:
        import ultralytics
        bus = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"
        det = HelmetPlateDetector(PERSON_MODEL_PATH, conf_threshold=0.4, fallback_path="yolov8n.pt")
        people = [d for d in det.detect(cv2.imread(str(bus))) if d.class_name == "person"]
        report("Phát hiện người", len(people) >= 3, f"{len(people)} người trong ảnh mẫu (có 4)")
    except Exception as e:
        report("Phát hiện người", False, str(e))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="chỉ kiểm tra, không tải/sửa gì")
    args = parser.parse_args()

    print("=" * 70)
    print(" CHUẨN BỊ DEMO — School Gate Monitor")
    print("=" * 70)
    check_gpu()
    fix_helmet_model(args.quick)
    prefetch_models(args.quick)
    ensure_env()
    if not args.quick:
        self_test()

    failed = [r for r in results if not r[1]]
    print("\n" + "=" * 70)
    if failed:
        print(f" CÒN {len(failed)} VẤN ĐỀ:")
        for name, _, detail in failed:
            print(f"   - {name}: {detail}")
    else:
        print(" TẤT CẢ ĐỀU SẴN SÀNG — chạy CHAY_DEMO.bat (hoặc uvicorn) để bắt đầu.")
    print("=" * 70)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
