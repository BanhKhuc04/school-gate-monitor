"""
Fine-tune helmet detector trên dữ liệu mới annotate qua CVAT (datasets/helmet_detect/).

Bối cảnh: helmet_best.pt gốc tải từ HuggingFace (iam-tsr/yolov8n-helmet-detection),
chưa từng train trong dự án này. Đánh giá trên 55 frame thật từ camera cổng trường
(scripts/../datasets/cvat_review/helmet_review/) cho thấy model miss nhiều trong
cảnh đông người/xa (vd: 8 người + 4 xe nhưng 0 helmet detect được dù ảnh cho thấy
rõ người đội mũ), và có false positive trên nền không có người/vật gì.

Cách dùng:
1. Annotate datasets/cvat_review/helmet_review/*.jpg trong CVAT (2 class: 'With
   Helmet', 'Without Helmet' — đúng thứ tự đang dùng trong helmet_best.pt), thêm
   cả các frame KHÔNG có helmet nào (annotate rỗng, không box) để dạy model không
   detect nhầm trên nền — đây chính là các case false positive đã phát hiện.
2. Export từ CVAT theo format "YOLO 1.1" hoặc "Ultralytics YOLO".
3. Giải nén, đổ ảnh vào datasets/helmet_detect/images/{train,val}/ và nhãn .txt
   tương ứng vào datasets/helmet_detect/labels/{train,val}/ (giữ nguyên tên file,
   chia train/val theo tỉ lệ ~90/10).
4. Chạy: python scripts/train_helmet.py

Có GPU cục bộ (RTX 3050, CUDA) — device=0, nhanh hơn CPU rất nhiều.
"""
from ultralytics import YOLO

BASE_MODEL = "models/helmet_best.pt"  # fine-tune tiếp từ model hiện có, không train từ đầu
DATA_YAML = "datasets/helmet_detect/data.yaml"
OUT_NAME = "helmet_finetune_v1"

if __name__ == "__main__":
    model = YOLO(BASE_MODEL)
    model.train(
        data=DATA_YAML,
        epochs=30,
        imgsz=640,
        batch=16,
        device=0,
        project="runs/train",
        name=OUT_NAME,
        patience=8,
    )
    print("Xong. Model mới: runs/train/%s/weights/best.pt" % OUT_NAME)
    print("So sánh với models/helmet_best.pt hiện tại (dùng scripts/diagnose_hard_cases.py hoặc test trên datasets/cvat_review/helmet_review/) trước khi thay thế.")
