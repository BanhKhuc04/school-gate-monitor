"""
Gương chiếu hậu — quyết định "xe có gương TRÁI (theo người lái) hay không"
cho CẢ LƯỢT XE, không theo 1 frame.

Nguyên tắc (docs/PLAN_GUONG_VA_NHIEU_NGUOI_VAO_RA.md, Phần B):
  - Model (YOLO 1 lớp `mirror`, chạy trên crop xe) chỉ cho biết CÓ thấy gương
    ở đâu. Không thấy ≠ không có: gương có thể bị tay/đầu/người khác che, hoặc
    ảnh quá nhỏ. Vì vậy:
      present : thấy gương trái ở ≥ min_present frame tốt.
      missing : ĐỦ k frame tốt, KHÔNG bị che, và không frame nào thấy gương trái.
      unknown : mọi trường hợp còn lại — KHÔNG BAO GIỜ cảnh báo từ unknown.
  - Trái/phải tính theo NGƯỜI LÁI, suy từ chiều đi: xe đi VỀ PHÍA camera thì
    tay trái người lái nằm bên PHẢI ảnh; xe đi XA camera thì ngược lại.
  - Xe nhỏ hơn min_vehicle_px (bề ngang bbox) bị bỏ qua: gương chỉ còn vài px,
    model không phân biệt được có/không.

Thuần Python, chưa nối vào pipeline: cần models/mirror_best.pt (train bằng
scripts/train_mirror.py) và camera có MIRROR_LEFT_OBSERVABLE=1 trước.
"""
from __future__ import annotations

from dataclasses import dataclass

PRESENT, MISSING, UNKNOWN = 'present', 'missing', 'unknown'


def rider_side(mirror_box, vehicle_box, toward_camera: bool) -> str:
    """'left' / 'right' theo người lái cho 1 box gương nằm trên 1 xe."""
    mirror_cx = (mirror_box[0] + mirror_box[2]) / 2
    vehicle_cx = (vehicle_box[0] + vehicle_box[2]) / 2
    on_image_right = mirror_cx > vehicle_cx
    return 'left' if on_image_right == toward_camera else 'right'


@dataclass
class _Frame:
    width: float
    left_found: bool
    left_occluded: bool


class MirrorVote:
    """Gom quan sát gương của 1 track xe, giữ k frame tốt nhất (xe to nhất)."""

    def __init__(self, k: int = 5, min_present: int = 2, min_vehicle_px: float = 250):
        self.k = k
        self.min_present = min_present
        self.min_vehicle_px = min_vehicle_px
        self._frames: list[_Frame] = []

    def observe(self, vehicle_box, mirror_boxes, toward_camera: bool,
                left_occluded: bool = False) -> bool:
        """Thêm 1 frame. mirror_boxes cùng hệ tọa độ với vehicle_box.
        left_occluded: vùng gương trái bị che (vd cổ tay/khuỷu tay trái người
        lái từ pose nằm đúng chỗ gương). Trả False nếu frame bị bỏ (xe quá nhỏ)."""
        width = vehicle_box[2] - vehicle_box[0]
        if width < self.min_vehicle_px:
            return False
        left_found = any(rider_side(m, vehicle_box, toward_camera) == 'left' for m in mirror_boxes)
        self._frames.append(_Frame(width, left_found, left_occluded and not left_found))
        self._frames.sort(key=lambda f: f.width, reverse=True)
        del self._frames[self.k:]
        return True

    def decide(self) -> str:
        if sum(f.left_found for f in self._frames) >= self.min_present:
            return PRESENT
        clear = [f for f in self._frames if not f.left_occluded]
        if len(clear) >= self.k and not any(f.left_found for f in self._frames):
            return MISSING
        return UNKNOWN
