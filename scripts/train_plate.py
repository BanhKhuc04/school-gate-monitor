"""
Fine-tune plate detector trên dataset biển số Việt Nam thật (datasets/vn_plate_detect/).

Nguồn dataset: winter2897/Real-time-Auto-License-Plate-Recognition-with-Jetson-Nano
(8259 ảnh biển số VN thật — xe máy, ô tô, quân đội, ngoại giao), 1 class 'plate'.

Chạy: python scripts/train_plate.py
Có GPU cục bộ (RTX 3050, CUDA) — device=0, nhanh hơn CPU rất nhiều.

ponytail: epoch=20, imgsz=640 — đủ để đo model có cải thiện hay không so với
plate_best.pt hiện tại (0/5 detect trên ảnh thật). Nếu kết quả tốt nhưng chưa
đủ chính xác, tăng epoch sau — không train 100+ epoch mù quáng ngay từ đầu.
"""
from ultralytics import YOLO

BASE_MODEL = "models/plate_best.pt"  # fine-tune tiếp từ model hiện có, không train từ đầu
DATA_YAML = "datasets/vn_plate_detect/data.yaml"
OUT_NAME = "plate_finetune_v1"

if __name__ == "__main__":
    model = YOLO(BASE_MODEL)
    model.train(
        data=DATA_YAML,
        epochs=20,
        imgsz=640,
        batch=16,
        device=0,
        project="runs/train",
        name=OUT_NAME,
        patience=5,
    )
    print("Xong. Model mới: runs/train/%s/weights/best.pt" % OUT_NAME)
    print("So sánh với models/plate_best.pt hiện tại trước khi thay thế.")
