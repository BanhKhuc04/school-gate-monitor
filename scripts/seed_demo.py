"""
T2.1 — Seed bộ dữ liệu demo cho môi trường dev/demo: 4 role, 2 lớp, roster,
một số xe và vi phạm giả.

Idempotent:
- Không ghi đè user đã tồn tại (dùng force=False).
- Không tạo trùng biển.
- Không động vào DB/media vận hành: nếu DB_PATH trỏ tới `data/app.db` thật
  (không phải test/giả), script cảnh báo và yêu cầu --i-understand-this-writes-demo.

Chạy:
    python scripts/seed_demo.py
    python scripts/seed_demo.py --i-understand-this-writes-demo   # cho demo DB thật
    APP_DB_PATH=/tmp/demo.db python scripts/seed_demo.py --reset   # DB tạm
"""
import argparse
import os
import sys
from pathlib import Path

# Allow running as a plain script without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DB_PATH  # noqa: E402
from app.db import (  # noqa: E402
    init_db,
    add_vehicle,
    add_roster_entry,
    create_user,
    get_user_by_username,
    get_vehicle_by_plate,
    count_admins,
    update_user,
)

from app.auth import hash_password  # noqa: E402


# ─── Demo data ────────────────────────────────────────────────────────────────

DEMO_USERS = [
    # (username, password, role, homeroom_class)
    ("admin",      "admin123",      "admin",      None),
    ("security",   "security123",   "security",   None),
    ("management", "management123", "management", None),
    ("teacher",    "teacher123",    "teacher",    "10A1"),
    ("teacher_b",  "teacher123",    "teacher",    "10A2"),
]

# Roster (mã số hợp lệ cho public register)
DEMO_ROSTER_10A1 = [
    ("HS2025001", "Nguyễn Văn An", "10A1"),
    ("HS2025002", "Trần Thị Bình", "10A1"),
    ("HS2025003", "Lê Hoàng Cường", "10A1"),
    ("HS2025004", "Phạm Thị Dung", "10A1"),
]
DEMO_ROSTER_10A2 = [
    ("HS2025010", "Đỗ Văn Em",   "10A2"),
    ("HS2025011", "Hoàng Thị Phương", "10A2"),
    ("HS2025012", "Bùi Minh Quân", "10A2"),
]

# Xe đã đăng ký
DEMO_VEHICLES_10A1 = [
    ("50A41234", "Nguyễn Văn An",  "10A1", "HS2025001"),
    ("50A41235", "Trần Thị Bình",  "10A1", "HS2025002"),
    ("50A41236", "Lê Hoàng Cường", "10A1", "HS2025003"),
]
DEMO_VEHICLES_10A2 = [
    ("60B12345", "Đỗ Văn Em",        "10A2", "HS2025010"),
    ("60B12346", "Hoàng Thị Phương",  "10A2", "HS2025011"),
]


def is_production_like_db() -> bool:
    """Đoán DB_PATH có phải vận hành không (không phải file test/tạm)."""
    path = Path(DB_PATH).resolve()
    name = path.name.lower()
    if name in ("app.db", "production.db"):
        return True
    # Không có marker rõ ràng thì coi như dev/demo — không chặn.
    return False


def seed_users(force: bool = False) -> list[str]:
    """Tạo/cập nhật user demo. Idempotent."""
    actions = []
    for username, password, role, cls in DEMO_USERS:
        existing = get_user_by_username(username)
        if existing and not force:
            actions.append(
                f"  - {username} ({existing['role']}, class={existing.get('homeroom_class')}): SKIP (đã tồn tại)"
            )
            continue
        if existing and force:
            # cập nhật role + class; password hash nếu force
            pw_hash = hash_password(password)
            update_user(existing["id"], role=role, password_hash=pw_hash,
                        homeroom_class=cls)
            actions.append(f"  - {username}: UPDATED (role={role}, class={cls})")
        else:
            pw_hash = hash_password(password)
            create_user(username, pw_hash, role, cls)
            actions.append(f"  - {username}: CREATED (role={role}, class={cls})")
    return actions


def seed_roster(force: bool = False) -> list[str]:
    """Thêm roster nếu chưa có. force=True bỏ qua kiểm tra trùng."""
    actions = []
    from app.db import get_roster_entry
    for entry in DEMO_ROSTER_10A1 + DEMO_ROSTER_10A2:
        sid = entry[0]
        existing = get_roster_entry(sid)
        if existing:
            actions.append(f"  - {sid}: SKIP (đã có)")
            continue
        add_roster_entry(*entry)
        actions.append(f"  - {sid}: CREATED ({entry[1]} / {entry[2]})")
    return actions


def seed_vehicles(force: bool = False) -> list[str]:
    actions = []
    for v in DEMO_VEHICLES_10A1 + DEMO_VEHICLES_10A2:
        plate, name, cls, sid = v
        existing = get_vehicle_by_plate(plate)
        if existing:
            actions.append(f"  - {plate}: SKIP (đã có)")
            continue
        try:
            add_vehicle(plate, name, cls, student_id=sid)
            actions.append(f"  - {plate}: CREATED ({name} / {cls})")
        except Exception as e:
            actions.append(f"  - {plate}: ERROR ({e})")
    return actions


def main():
    parser = argparse.ArgumentParser(description="Seed demo data (T2.1)")
    parser.add_argument(
        "--i-understand-this-writes-demo",
        action="store_true",
        help="Bỏ qua cảnh báo khi DB_PATH trỏ tới app thật (chỉ dùng khi demo).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Cập nhật user đã tồn tại (mặc định: bỏ qua).",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="KHÔNG xóa DB nhưng seed lại từ đầu (kết hợp --force).",
    )
    args = parser.parse_args()

    if is_production_like_db() and not args.i_understand_this_writes_demo:
        print("=" * 60)
        print("CẢNH BÁO: DB_PATH trỏ tới DB vận hành (data/app.db hoặc tương đương).")
        print(f"  DB_PATH = {DB_PATH}")
        print("Script này sẽ tạo tài khoản demo (admin/security/management/teacher")
        print("với mật khẩu yếu). KHÔNG chạy trên DB vận hành.")
        print("Để tiếp tục trên DB vận hành (CHỈ cho demo): --i-understand-this-writes-demo")
        print("Hoặc dùng APP_DB_PATH=/path/to/demo.db trước khi chạy.")
        print("=" * 60)
        sys.exit(2)

    print(f"DB_PATH = {DB_PATH}")
    init_db()

    if args.reset:
        args.force = True

    print("\n[users]")
    for line in seed_users(force=args.force):
        print(line)

    print("\n[roster]")
    for line in seed_roster(force=args.force):
        print(line)

    print("\n[vehicles]")
    for line in seed_vehicles(force=args.force):
        print(line)

    # Đếm admin để xác nhận không mất admin
    print(f"\n[admins] count = {count_admins()}")
    print("\nDemo data ready. Tài khoản demo (mật khẩu yếu — chỉ dùng cho dev/demo):")
    for u, p, role, cls in DEMO_USERS:
        cls_str = f" / lớp {cls}" if cls else ""
        print(f"  {u:24s} {p:24s} role={role}{cls_str}")


if __name__ == "__main__":
    main()