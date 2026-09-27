"""
Database operations using sqlite3 thuần.
Schema: registered_vehicles, violation_events (xem PLAN.md)
"""
import sqlite3
import threading
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from app.config import DB_PATH, SNAPSHOTS_DIR
from app.cv.ocr import normalize_plate


# Lock bảo vệ thao tác ghi
_write_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    """
    Tạo connection tới SQLite.
    check_same_thread=False vì dùng chung giữa pipeline thread và FastAPI.
    """
    # Đảm bảo thư mục data tồn tại
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")  # wait up to 5s for locks
    return conn


def init_db():
    """Tạo bảng nếu chưa tồn tại."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Bảng xe đăng ký
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registered_vehicles (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number  TEXT NOT NULL UNIQUE,
                student_name  TEXT NOT NULL,
                student_class TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')
        
        # Bảng sự kiện vi phạm
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS violation_events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp      TEXT NOT NULL,
                plate_read     TEXT,
                plate_matched  TEXT,
                helmet_status  TEXT NOT NULL,
                violation_type TEXT NOT NULL,
                snapshot_path  TEXT,
                posture_status TEXT,  -- 'standing' | 'riding' | 'unknown' | None
                created_at     TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')
        
        # Index cho timestamp
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_violation_events_timestamp 
            ON violation_events(timestamp)
        ''')

        # Migration: add posture_status column if it doesn't exist (for existing DBs)
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN posture_status TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        
        # Bảng người dùng
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL CHECK (role IN ('admin', 'security', 'management')),
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')
        
        conn.commit()
        print("[DB] Database initialized")
    finally:
        conn.close()

    # Also create face recognition tables
    _init_face_tables()


def add_vehicle(plate_number: str, student_name: str, student_class: str) -> int:
    """
    Thêm xe mới.
    
    Args:
        plate_number: Biển số (sẽ được chuẩn hóa)
        student_name: Tên học sinh
        student_class: Lớp
        
    Returns:
        ID của xe mới thêm
        
    Raises:
        ValueError: Nếu biển số đã tồn tại
    """
    plate = normalize_plate(plate_number)
    if not plate:
        raise ValueError("Biển số không hợp lệ")
    
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO registered_vehicles (plate_number, student_name, student_class) VALUES (?, ?, ?)',
                (plate, student_name, student_class)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"Biển số {plate} đã tồn tại")
        finally:
            conn.close()


def get_vehicle_by_plate(plate_number: str) -> Optional[dict]:
    """
    Tìm xe theo biển số (đã chuẩn hóa).
    
    Returns:
        dict hoặc None nếu không tìm thấy
    """
    plate = normalize_plate(plate_number)
    if not plate:
        return None
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM registered_vehicles WHERE plate_number = ?',
            (plate,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def list_vehicles() -> List[dict]:
    """Liệt kê tất cả xe đã đăng ký."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM registered_vehicles ORDER BY created_at DESC')
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def update_vehicle(vehicle_id: int, plate_number: str = None, 
                   student_name: str = None, student_class: str = None) -> bool:
    """
    Cập nhật thông tin xe.
    
    Args:
        vehicle_id: ID xe
        plate_number: Biển số mới (sẽ được chuẩn hóa)
        student_name: Tên mới
        student_class: Lớp mới
        
    Returns:
        True nếu cập nhật thành công, False nếu không tìm thấy
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            
            # Build SET clause dynamically
            updates = []
            params = []
            
            if plate_number is not None:
                plate = normalize_plate(plate_number)
                if plate:
                    updates.append('plate_number = ?')
                    params.append(plate)
            
            if student_name is not None:
                updates.append('student_name = ?')
                params.append(student_name)
            
            if student_class is not None:
                updates.append('student_class = ?')
                params.append(student_class)
            
            if not updates:
                return False
            
            params.append(vehicle_id)
            
            cursor.execute(
                f'UPDATE registered_vehicles SET {", ".join(updates)} WHERE id = ?',
                params
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            raise ValueError("Biển số đã tồn tại")
        finally:
            conn.close()


def delete_vehicle(vehicle_id: int) -> bool:
    """
    Xóa xe.
    
    Returns:
        True nếu xóa thành công, False nếu không tìm thấy
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM registered_vehicles WHERE id = ?', (vehicle_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def add_violation_event(timestamp: str, plate_read: str = None,
                       plate_matched: str = None, helmet_status: str = None,
                       violation_type: str = None, snapshot_path: str = None,
                       posture_status: str = None) -> int:
    """
    Thêm sự kiện vi phạm.
    
    Args:
        timestamp: ISO timestamp
        plate_read: Biển số đọc được (thô)
        plate_matched: Biển số khớp trong whitelist
        helmet_status: 'helmet' | 'no_helmet' | 'unknown'
        violation_type: 'NO_HELMET' | 'PLATE_NOT_REGISTERED' | 'RIDING_THROUGH_GATE' | ...
        snapshot_path: Đường dẫn ảnh chụp
        posture_status: 'standing' | 'riding' | 'unknown' | None
        
    Returns:
        ID của sự kiện mới
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO violation_events 
                   (timestamp, plate_read, plate_matched, helmet_status, violation_type, snapshot_path, posture_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (timestamp, plate_read, plate_matched, helmet_status, violation_type, snapshot_path, posture_status)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()


def list_violations(
    limit: int = 50,
    offset: int = 0,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    violation_type: Optional[str] = None,
    plate: Optional[str] = None,
) -> List[dict]:
    """
    Liệt kê các sự kiện vi phạm với phân trang và lọc.

    Args:
        limit: Số lượng tối đa mỗi trang
        offset: Bỏ qua N bản ghi đầu
        date_from: ISO timestamp bắt đầu (inclusive)
        date_to: ISO timestamp kết thúc (inclusive)
        violation_type: Lọc theo loại vi phạm (e.g. 'NO_HELMET')
        plate: Lọc theo biển số (tìm chứa, không phải khớp tuyệt đối)

    Returns:
        List of violation records
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Build WHERE clause dynamically
        conditions = []
        params: List = []

        if date_from:
            conditions.append('timestamp >= ?')
            params.append(date_from)
        if date_to:
            conditions.append('timestamp <= ?')
            params.append(date_to)
        if violation_type:
            conditions.append('violation_type = ?')
            params.append(violation_type)
        if plate:
            conditions.append('(plate_read LIKE ? OR plate_matched LIKE ?)')
            like_val = f'%{plate}%'
            params.extend([like_val, like_val])

        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        # Total count (ignoring LIMIT/OFFSET)
        cursor.execute(f'SELECT COUNT(*) FROM violation_events WHERE {where_clause}', params)
        total = cursor.fetchone()[0]

        # Paginated results
        query = f'''
            SELECT * FROM violation_events
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        '''
        cursor.execute(query, params + [limit, offset])
        items = [dict(row) for row in cursor.fetchall()]

        return {
            'total': total,
            'limit': limit,
            'offset': offset,
            'items': items,
        }
    finally:
        conn.close()


def create_user(username: str, password_hash: str, role: str) -> int:
    """
    Tạo user mới.
    
    Args:
        username: Tên đăng nhập (UNIQUE)
        password_hash: bcrypt hash
        role: 'admin' | 'security' | 'management'
        
    Returns:
        ID của user mới
        
    Raises:
        ValueError: Nếu username đã tồn tại
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                (username, password_hash, role)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' already exists")
        finally:
            conn.close()


def get_user_by_username(username: str) -> Optional[dict]:
    """
    Tìm user theo username.

    Returns:
        dict hoặc None nếu không tìm thấy
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def list_users() -> List[dict]:
    """Liệt kê tất cả user (không trả password_hash)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, role, created_at FROM users ORDER BY created_at ASC')
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Tìm user theo ID."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, role, created_at FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_admins() -> int:
    """Đếm số user có role='admin'."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def update_user(user_id: int, role: str = None, password_hash: str = None) -> bool:
    """
    Cập nhật user.

    Args:
        user_id: ID user cần sửa
        role: role mới (hoặc None để không đổi)
        password_hash: bcrypt hash mới (hoặc None để không đổi)

    Returns:
        True nếu thành công, False nếu không tìm thấy
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            updates = []
            params = []
            if role is not None:
                updates.append('role = ?')
                params.append(role)
            if password_hash is not None:
                updates.append('password_hash = ?')
                params.append(password_hash)
            if not updates:
                return False
            params.append(user_id)
            cursor.execute(
                f'UPDATE users SET {", ".join(updates)} WHERE id = ?',
                params
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def delete_user(user_id: int) -> bool:
    """
    Xóa user.

    Returns:
        True nếu thành công, False nếu không tìm thấy
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def get_violation_stats() -> Dict[str, Any]:
    """
    Thống kê vi phạm.

    Returns:
        {
            "total_today": int,          -- đếm vi phạm hôm nay (theo date của timestamp)
            "total_week": int,           -- đếm vi phạm 7 ngày gần nhất
            "by_type": {                -- đếm theo loại vi phạm
                "NO_HELMET": int,
                "PLATE_NOT_REGISTERED": int,
                "PLATE_UNREADABLE": int,
                "MULTIPLE": int,
            }
        }
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Today: date(timestamp) = date('now', 'localtime')
        cursor.execute("SELECT COUNT(*) FROM violation_events WHERE date(timestamp) = date('now', 'localtime')")
        total_today = cursor.fetchone()[0]

        # Last 7 days
        cursor.execute(
            "SELECT COUNT(*) FROM violation_events WHERE timestamp >= datetime('now', 'localtime', '-7 days')"
        )
        total_week = cursor.fetchone()[0]

        # By violation_type (all time — change to 7 days if preferred)
        by_type: Dict[str, int] = {
            "NO_HELMET": 0,
            "PLATE_NOT_REGISTERED": 0,
            "PLATE_UNREADABLE": 0,
            "MULTIPLE": 0,
            "RIDING_THROUGH_GATE": 0,
        }
        cursor.execute(
            '''SELECT violation_type, COUNT(*) as cnt
               FROM violation_events
               GROUP BY violation_type'''
        )
        for row in cursor.fetchall():
            vt = row["violation_type"]
            if vt in by_type:
                by_type[vt] = row["cnt"]

        return {
            "total_today": total_today,
            "total_week": total_week,
            "by_type": by_type,
        }
    finally:
        conn.close()


def get_old_violation_snapshot_paths(older_than_days: int = 90) -> List[str]:
    """
    Trả về danh sách snapshot_path cần xóa (cũ hơn older_than_days ngày).
    Chỉ trả về path, không xóa gì cả.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # date('now', '-N days') = date N days ago
        cutoff = f"-{older_than_days} days"
        cursor.execute(
            "SELECT snapshot_path FROM violation_events "
            "WHERE snapshot_path IS NOT NULL "
            "AND timestamp < datetime('now', ?)",
            (cutoff,)
        )
        return [row["snapshot_path"] for row in cursor.fetchall()]
    finally:
        conn.close()


def clear_violation_snapshot_paths(older_than_days: int = 90) -> int:
    """
    Xóa file snapshot cũ và set snapshot_path = NULL trong DB.
    Giữ nguyên record vi phạm, chỉ null đường dẫn ảnh.
    Trả về số record đã null.
    """
    paths = get_old_violation_snapshot_paths(older_than_days)
    count = 0
    for path in paths:
        full_path = path if os.path.isabs(path) else os.path.join(SNAPSHOTS_DIR, os.path.basename(path))
        try:
            if os.path.exists(full_path):
                os.unlink(full_path)
        except OSError:
            pass  # file already gone, that's fine
        count += 1

    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cutoff = f"-{older_than_days} days"
            cursor.execute(
                "UPDATE violation_events SET snapshot_path = NULL "
                "WHERE snapshot_path IS NOT NULL "
                "AND timestamp < datetime('now', ?)",
                (cutoff,)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()


# ─── Face recognition tables ─────────────────────────────────────────────────────

def _init_face_tables():
    """Create face tables if they don't exist (idempotent)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS face_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label_name TEXT NOT NULL,
                vehicle_id INTEGER,
                embedding BLOB NOT NULL,
                photo_path TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (vehicle_id) REFERENCES registered_vehicles(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS face_match_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                matched_label TEXT,
                similarity REAL,
                vehicle_id INTEGER,
                snapshot_path TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (vehicle_id) REFERENCES registered_vehicles(id) ON DELETE SET NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


# Initialize face tables on module import
_init_face_tables()


def add_face_embedding(
    label_name: str,
    embedding: bytes,
    photo_path: str = None,
    vehicle_id: int = None,
) -> int:
    """Lưu một face embedding mới."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO face_embeddings (label_name, vehicle_id, embedding, photo_path) VALUES (?, ?, ?, ?)",
            (label_name, vehicle_id, embedding, photo_path),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_face_embeddings() -> List[dict]:
    """Lấy tất cả face embeddings metadata (không trả bytes)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, label_name, vehicle_id, photo_path, created_at FROM face_embeddings ORDER BY created_at ASC"
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_face_embedding_by_id(embedding_id: int) -> Optional[dict]:
    """Lấy một embedding theo ID (bao gồm bytes)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, label_name, vehicle_id, embedding, photo_path, created_at FROM face_embeddings WHERE id = ?",
            (embedding_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_face_embedding(embedding_id: int) -> bool:
    """Xóa một face embedding theo ID."""
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM face_embeddings WHERE id = ?", (embedding_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def add_face_match_event(
    matched_label: str = None,
    similarity: float = None,
    vehicle_id: int = None,
    snapshot_path: str = None,
) -> int:
    """Ghi một sự kiện face match."""
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO face_match_events (timestamp, matched_label, similarity, vehicle_id, snapshot_path) VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), matched_label, similarity, vehicle_id, snapshot_path),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()


def get_face_match_events(limit: int = 50, offset: int = 0) -> List[dict]:
    """Lấy danh sách face match events gần nhất."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, matched_label, similarity, vehicle_id, snapshot_path, created_at "
            "FROM face_match_events ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
