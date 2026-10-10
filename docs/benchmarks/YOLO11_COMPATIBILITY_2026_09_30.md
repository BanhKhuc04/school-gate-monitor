"""
YOLO11 compatibility test results (Đợt D1).

Môi trường: .venv_yolo11 với ultralytics>=8.3.0 (thực cài 8.4.168).
Máy: i7-12700H, RAM 16 GB, RTX 3050 4 GB (test chạy trên CPU).

Môi trường app đang chạy: ultralytics 8.2.103 (< 8.3).

=== KẾT QUẢ ===

YOLO11n model:
- Model: yolo11n.pt (5.4 MB)
- Classes: 80 COCO classes (person, bicycle, motorcycle có sẵn)
- YOLO11n inference: 122.6ms/frame (8.2 FPS) — CPU, 640x640
- YOLOv8n inference: 50.5ms/frame (19.8 FPS) — CPU, 640x640
- YOLO11n SLOWER than YOLOv8n by 2.4x on CPU
- Lý do: YOLO11n model lớn hơn (5.4MB vs 2.6MB yolov8n.pt); không có TensorRT

BoT-SORT tracker:
- Available in ultralytics 8.4.168 (importable)
- Works: botsort.yaml tracker loaded OK
- Cảnh báo: GMC failed (OpenCV LKOpticalFlow error) — fallback identity
- BoT-SORT có thêm byte_tracker đi kèm

=== KẾT LUẬN D1 ===

Không có bằng chứng YOLO11n tốt hơn YOLOv8n trên CPU cho use case này:
1. YOLO11n chậm hơn 2.4x (122ms vs 50ms/frame)
2. Không có benchmark precision/recall (cần video có nhãn)
3. YOLOv8n hiện tại đạt 65 FPS helmet, 62 FPS plate, 65 FPS person trên GPU
4. GPU inference YOLO11n chưa đo trong môi trường này

ByteTrack (hiện tại) vs BoT-SORT:
- ByteTrack hoạt động tốt với camera cố định
- BoT-SORT có thêm GMC (global motion compensation) cho camera di chuyển
- Camera cổng trường KHÔNG di chuyển → ByteTrack đủ tốt
- BoT-SORT không cần thiết cho use case này

=== KHUYẾN NGHỊ ===

- KHÔNG thay YOLOv8 bằng YOLO11n trên CPU
- ByteTrack đủ cho camera cố định
- Nếu cần tăng tốc GPU: thử TensorRT export (yolov8n → yolov8n.engine)
  thay vì đổi model mới
- Chỉ thay model khi có benchmark precision/recall với dữ liệu có nhãn
  cho thấy YOLO11 tốt hơn trên helmet/plate detection

=== LỆNH ĐOẠT MÔI TRƯỜNG ===
cd D:\Work\Project_motorbike
.venv_yolo11\Scripts\python.exe -c "import ultralytics; print(ultralytics.__version__)"
"""
