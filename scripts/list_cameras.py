"""
Dò camera index để tìm OBS Virtual Camera (hoặc bất kỳ webcam nào khác).
Thử nhiều backend: DSHOW, MF (Media Foundation), default.

Chạy: python scripts/list_cameras.py
Mỗi camera tìm được sẽ mở 1 cửa sổ ghi rõ index + backend. Nhấn phím bất kỳ để xem camera
tiếp theo, 'q' để dừng. Ghi lại index + backend của cửa sổ hiện đúng nguồn OBS,
đặt vào CAMERA_INDEX trong app/config.py (backend mặc định là cv2.CAP_ANY).
"""
import cv2

BACKENDS = [
    (cv2.CAP_DSHOW, "DSHOW"),
    (cv2.CAP_MSMF,  "MSMF"),
    (cv2.CAP_ANY,   "ANY"),
]

found_any = False

for backend, backend_name in BACKENDS:
    print(f"\n--- Thu backend: {backend_name} ---")
    for index in range(8):
        try:
            if backend == cv2.CAP_ANY:
                cap = cv2.VideoCapture(index)
            else:
                cap = cv2.VideoCapture(index, backend)
        except Exception:
            continue

        if not cap.isOpened():
            continue

        # Thử đọc vài frame
        ok = False
        for _ in range(5):
            ok, frame = cap.read()
            if ok and frame is not None and frame.size > 0:
                break

        if not ok:
            cap.release()
            continue

        found_any = True
        label = f"Camera {index} [{backend_name}] - nhan phim de xem tiep, 'q' de dung"
        h, w = frame.shape[:2]
        info = f"index={index}, backend={backend_name}, {w}x{h}"
        cv2.putText(frame, info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow(f"Camera {index} [{backend_name}]", frame)
        key = cv2.waitKey(0)
        cv2.destroyAllWindows()
        cap.release()

        print(f"  Tim thay: index={index}, backend={backend_name}")

        if key == ord('q'):
            break

    if found_any and backend_name != "ANY":
        pass  # tiếp tục thử backend khác

if not found_any:
    print("\nKhong tim thay camera nao!")
    print("Dam bao OBS da bat Start Virtual Camera, va scene co noi dung.")
else:
    print("\nXong. Dat index + backend vao CAMERA_INDEX trong app/config.py")
    print("Neu dung MSMF, trong config dat: CAMERA_INDEX = <index>")
    print("Code hien tai khong co tuy chon backend, nen chi can dat index.")
