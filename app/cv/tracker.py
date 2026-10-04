"""
Theo dõi người qua nhiều khung hình (gán ID ổn định cho từng box) bằng IoU.

Pipeline trước đây không biết 2 box ở 2 khung hình liên tiếp có phải cùng 1
người hay không, nên phải chặn ghi trùng bằng cooldown 60s theo biển số — mọi xe
không đọc được biển dùng chung 1 khóa "UNKNOWN", khiến xe thứ 2, thứ 3... đi qua
trong cùng 1 phút bị BỎ SÓT hoàn toàn. Có ID theo dõi thì mỗi người/xe được xét
và ghi đúng 1 lần, độc lập với nhau.

Ghép tham lam theo IoU (cao nhất trước) — đủ cho camera cổng trường (ít người
cùng lúc, di chuyển chậm). Box không ghép được với IoU thì thử khoảng cách tâm
(người đi nhanh giữa 2 lần detect có thể không còn chồng lấp nhiều).
"""


def iou(a: tuple, b: tuple) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = max(0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def _center_close(a: tuple, b: tuple, ratio: float) -> bool:
    """Tâm 2 box cách nhau không quá `ratio` lần chiều rộng box cũ, và kích thước
    không đổi quá 2 lần (tránh ghép người ở xa với người ở gần)."""
    aw, ah = a[2] - a[0], a[3] - a[1]
    bw, bh = b[2] - b[0], b[3] - b[1]
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return False
    if not (0.5 <= bh / ah <= 2.0):
        return False
    dx = (a[0] + a[2]) / 2 - (b[0] + b[2]) / 2
    dy = (a[1] + a[3]) / 2 - (b[1] + b[3]) / 2
    return (dx * dx + dy * dy) ** 0.5 <= ratio * aw


class IouTracker:
    def __init__(self, iou_threshold: float = 0.25, max_age_sec: float = 1.5,
                 center_ratio: float = 1.2):
        self.iou_threshold = iou_threshold
        self.max_age_sec = max_age_sec
        self.center_ratio = center_ratio
        self._next_id = 1
        self._tracks: dict[int, tuple[tuple, float]] = {}  # id -> (bbox, last_seen)

    def update(self, bboxes: list[tuple], now: float) -> list[int]:
        """Trả về track id cho từng bbox (cùng thứ tự). Track không xuất hiện quá
        max_age_sec bị xoá — người quay lại sau đó nhận ID mới."""
        self._tracks = {tid: (box, ts) for tid, (box, ts) in self._tracks.items()
                        if now - ts <= self.max_age_sec}

        ids: list[int | None] = [None] * len(bboxes)
        free_tracks = set(self._tracks)

        pairs = []
        for i, box in enumerate(bboxes):
            for tid in free_tracks:
                score = iou(box, self._tracks[tid][0])
                if score >= self.iou_threshold:
                    pairs.append((score, i, tid))
        for _, i, tid in sorted(pairs, reverse=True):
            if ids[i] is None and tid in free_tracks:
                ids[i] = tid
                free_tracks.discard(tid)

        for i, box in enumerate(bboxes):
            if ids[i] is not None:
                continue
            best = None
            for tid in free_tracks:
                if _center_close(self._tracks[tid][0], box, self.center_ratio):
                    dist = abs((self._tracks[tid][0][0] + self._tracks[tid][0][2]) - (box[0] + box[2]))
                    if best is None or dist < best[0]:
                        best = (dist, tid)
            if best is not None:
                ids[i] = best[1]
                free_tracks.discard(best[1])
            else:
                ids[i] = self._next_id
                self._next_id += 1

        for i, box in enumerate(bboxes):
            self._tracks[ids[i]] = (box, now)
        return ids

    def active_ids(self) -> set[int]:
        return set(self._tracks)
