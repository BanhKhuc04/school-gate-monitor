"""
Train model phát hiện gương chiếu hậu (1 lớp `mirror`) trên CROP XE.

Dữ liệu: datasets/vn_mirror/ tạo bằng scripts/prepare_mirror_dataset.py (to-yolo).
Bộ VN_street_motorbike_300 chỉ là dữ liệu PHỤ (ảnh nhỏ, camera giao thông). Trước
khi bật cảnh báo phải thêm dữ liệu quay tại cổng: ≥100 xe thiếu gương trái rõ và
≥100 xe đủ gương (xem docs/PLAN_GUONG_VA_NHIEU_NGUOI_VAO_RA.md, B2/B4).

    python scripts/train_mirror.py            # GPU 0 (RTX 3050)
    python scripts/train_mirror.py --device cpu

Kết quả: runs/train/mirror_v1/weights/best.pt -> chép sang models/mirror_best.pt
SAU KHI xem precision/recall trên tập val.
"""
import argparse

from ultralytics import YOLO

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default='datasets/vn_mirror/data.yaml')
    parser.add_argument('--model', default='yolo11n.pt')
    parser.add_argument('--device', default='0')
    parser.add_argument('--epochs', type=int, default=80)
    args = parser.parse_args()
    YOLO(args.model).train(
        data=args.data,
        epochs=args.epochs,
        # Crop xe nhỏ (trung vị ~150 px): phóng lên 320 đủ để gương 6-10 px
        # thành 15-20 px mà không tốn VRAM như 640.
        imgsz=320,
        batch=32,
        device=args.device,
        # Lật ngang đổi gương trái <-> phải, nhưng model chỉ có 1 lớp `mirror`
        # (trái/phải suy ra bằng hình học ở app/cv/mirror.py) nên lật vẫn đúng.
        fliplr=0.5,
        project='runs/train',
        name='mirror_v1',
        patience=20,
    )
    print('Xong: runs/train/mirror_v1/weights/best.pt')
