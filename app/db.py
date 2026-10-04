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


def normalize_plate(plate: str) -> str | None:
    """Standalone plate normalization — no easyocr dependency (mirrors app/cv/ocr.py)."""
    if not plate:
        return None
    import re
    plate = plate.upper()
    plate = re.sub(r'[^A-Z0-9]', '', plate)
    return plate if len(plate) >= 4 else None


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

        # ── 1. Tạo tất cả bảng mới (CREATE IF NOT EXISTS — an toàn chạy lại nhiều lần) ──
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registered_vehicles (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number  TEXT NOT NULL UNIQUE,
                student_name  TEXT NOT NULL,
                student_class TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS violation_events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp      TEXT NOT NULL,
                plate_read     TEXT,
                plate_matched  TEXT,
                helmet_status  TEXT NOT NULL,
                violation_type TEXT NOT NULL,
                snapshot_path  TEXT,
                posture_status TEXT,
                created_at     TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_violation_events_timestamp
            ON violation_events(timestamp)
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL CHECK (role IN ('admin', 'security', 'management')),
                homeroom_class TEXT,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS violation_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                violation_id INTEGER NOT NULL,
                actor_username TEXT NOT NULL,
                action TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (violation_id) REFERENCES violation_events(id)
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_audit_log_violation
            ON violation_audit_log(violation_id)
        ''')

        # Đợt 2, Bước 4: audit log cho tác vụ hệ thống (cleanup tự động, backup — Bước 6)
        # Tách khỏi violation_audit_log vì bảng đó có FK bắt buộc tới violation_id,
        # không hợp với job không gắn với 1 vi phạm cụ thể (cleanup xóa nhiều vi phạm
        # cùng lúc, backup thậm chí không liên quan tới violation).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_maintenance_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                success INTEGER NOT NULL DEFAULT 0,
                detail_json TEXT
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_maintenance_log_started
            ON system_maintenance_log(started_at)
        ''')

        # Vùng nhận diện (ROI) per-gate — xem app/cv/roi.py. points_json là
        # danh sách [[x,y],...] tỉ lệ % khung hình, hoặc thiếu row = chưa cấu hình.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gate_roi (
                gate_id    TEXT PRIMARY KEY,
                points_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        # Nguồn camera per-gate chọn qua /admin/camera — override GATES[gate_id]["source"]
        # đọc từ env var. Thiếu row = dùng mặc định trong app/config.py.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gate_camera_source (
                gate_id    TEXT PRIMARY KEY,
                source     TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        # ── 2. Migrations cho bảng đã tồn tại (ALTER TABLE — an toàn nếu cột đã có) ──
        # posture_status + plate_format_valid (từ trước)
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN posture_status TEXT")
        except sqlite3.OperationalError:
            pass
        # Danh sách lỗi cụ thể (vd. "NO_HELMET,PLATE_NOT_REGISTERED") — violation_type
        # chỉ ghi "MULTIPLE" khi có nhiều lỗi, cột này để giao diện hiện rõ từng lỗi
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN violation_details TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN plate_format_valid INTEGER")
        except sqlite3.OperationalError:
            pass

        # Feature 10: audit trail — trạng thái xử lý vi phạm
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
        except sqlite3.OperationalError:
            pass

        # Feature 4: video clip ngắn kèm ảnh
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN clip_path TEXT")
        except sqlite3.OperationalError:
            pass

        # Đợt 2, Bước 1: độ tin cậy biển số (PlateVoter) + camera nào ghi nhận
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN plate_confidence REAL")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN gate_id TEXT")
        except sqlite3.OperationalError:
            pass

        # Đợt 2, Bước 3: ghép 1 lượt xe từ 2 camera trước+sau
        # linked_violation_id trỏ sang bản ghi vi phạm ở gate kia (NULL nếu chưa ghép)
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN linked_violation_id INTEGER")
        except sqlite3.OperationalError:
            pass
        # correlation_status: NULL = chưa thử ghép, 'unmatched' = đã thử không thấy,
        # 'matched' = đã ghép, 'needs_review' = có ứng viên nhưng chưa đủ tự tin
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN correlation_status TEXT")
        except sqlite3.OperationalError:
            pass

        # Feature 9: giáo viên chủ nhiệm — homeroom_class (thêm sau vì bảng users đã tạo ở bước 1)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN homeroom_class TEXT")
        except sqlite3.OperationalError:
            pass

        # ── 3. Rebuild bảng users nếu CHECK constraint cũ chặn role='teacher' ──
        # Chỉ rebuild khi bảng đã tồn tại VÀ CHECK chưa có 'teacher'.
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
        row = cursor.fetchone()
        users_table_sql = row["sql"] if row else ""
        if row is not None and "'teacher'" not in users_table_sql.lower():
            print("[DB] Rebuilding users table to support 'teacher' role...")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'security', 'management', 'teacher')),
                    homeroom_class TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            ''')
            cursor.execute('''
                INSERT INTO users_new (id, username, password_hash, role, homeroom_class, created_at)
                SELECT id, username, password_hash, role,
                       NULLIF(homeroom_class, '') AS homeroom_class, created_at
                FROM users
            ''')
            cursor.execute("DROP TABLE users")
            cursor.execute("ALTER TABLE users_new RENAME TO users")
            print("[DB] Users table rebuilt with 'teacher' role support.")

            # Verify: thử insert dummy teacher để chắc CHECK mới hoạt động
            try:
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role, homeroom_class) "
                    "VALUES ('__teacher_check__', 'dummy', 'teacher', 'test')"
                )
                cursor.execute("DELETE FROM users WHERE username = '__teacher_check__'")
                print("[DB] CHECK constraint for 'teacher' role verified OK.")
            except sqlite3.IntegrityError as e:
                print(f"[DB] WARNING: 'teacher' role CHECK still blocked after rebuild: {e}")

        conn.commit()
        print("[DB] Database initialized")
    finally:
        conn.close()

    # Face recognition removed (masks defeat it) — drop any leftover tables from older DBs.
    conn2 = get_connection()
    try:
        conn2.execute("DROP TABLE IF EXISTS face_embeddings")
        conn2.execute("DROP TABLE IF EXISTS face_match_events")
        conn2.commit()
    finally:
        conn2.close()


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


def list_vehicles(student_class: str = None) -> List[dict]:
    """Liệt kê tất cả xe đã đăng ký. Feature 9: teacher scope filter."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if student_class:
            cursor.execute(
                'SELECT * FROM registered_vehicles WHERE student_class = ? ORDER BY created_at DESC',
                (student_class,)
            )
        else:
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
                       posture_status: str = None,
                       plate_format_valid: Optional[bool] = None,
                       clip_path: str = None,
                       plate_confidence: Optional[float] = None,
                       gate_id: str = None,
                       status: str = 'pending',
                       violation_details: Optional[str] = None) -> int:
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
        plate_format_valid: biển đọc được có khớp định dạng VN không (None nếu không có plate_read)
        clip_path: Đường dẫn video clip ngắn (Feature 4)
        plate_confidence: độ tin cậy đọc biển số 0.0-1.0 (đợt 2, Bước 1 — PlateVoter)
        gate_id: camera nào tạo ra bản ghi này (đợt 2, Bước 1 — cần cho Bước 3 ghép 2 camera)
        status: 'pending' (mặc định) | 'needs_review' (AI không chắc chắn — Bước 1)
        violation_details: danh sách lỗi cụ thể, phân cách bằng dấu phẩy (khi
            violation_type='MULTIPLE' — để giao diện hiện rõ từng lỗi)

    Returns:
        ID của sự kiện mới
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO violation_events
                   (timestamp, plate_read, plate_matched, helmet_status, violation_type, snapshot_path, posture_status, plate_format_valid, clip_path, plate_confidence, gate_id, status, violation_details)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (timestamp, plate_read, plate_matched, helmet_status, violation_type, snapshot_path, posture_status,
                 None if plate_format_valid is None else int(plate_format_valid), clip_path,
                 plate_confidence, gate_id, status, violation_details)
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
    student_class: Optional[str] = None,  # Feature 9: teacher scope filter
    status: Optional[str] = None,  # Đợt 2, Bước 1: lọc riêng 'needs_review'
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
        student_class: Lọc theo lớp học sinh (Feature 9 — teacher scope)
        status: Lọc theo trạng thái xử lý (e.g. 'needs_review')

    Returns:
        {"total": int, "limit": int, "offset": int, "items": [dict]}
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Build WHERE clause dynamically
        conditions = []
        params: List = []

        if date_from:
            conditions.append('ve.timestamp >= ?')
            params.append(date_from)
        if date_to:
            conditions.append('ve.timestamp <= ?')
            params.append(date_to)
        if violation_type:
            # Lọc "Không đội mũ" cũng phải ra cả bản ghi MULTIPLE có lỗi đó
            conditions.append("(ve.violation_type = ? OR ',' || COALESCE(ve.violation_details, '') || ',' LIKE ?)")
            params.extend([violation_type, f'%,{violation_type},%'])
        if plate:
            conditions.append('(ve.plate_read LIKE ? OR ve.plate_matched LIKE ?)')
            like_val = f'%{plate}%'
            params.extend([like_val, like_val])
        if student_class:
            conditions.append('rv.student_class = ?')
            params.append(student_class)
        if status:
            conditions.append('ve.status = ?')
            params.append(status)

        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        # Total count (ignoring LIMIT/OFFSET)
        cursor.execute(f'SELECT COUNT(*) FROM violation_events ve LEFT JOIN registered_vehicles rv ON rv.plate_number = ve.plate_matched WHERE {where_clause}', params)
        total = cursor.fetchone()[0]

        # Paginated results — LEFT JOIN registered_vehicles để lấy tên/lớp học sinh
        query = f'''
            SELECT ve.*, rv.student_name, rv.student_class
            FROM violation_events ve
            LEFT JOIN registered_vehicles rv ON rv.plate_number = ve.plate_matched
            WHERE {where_clause}
            ORDER BY ve.timestamp DESC
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


def create_user(username: str, password_hash: str, role: str, homeroom_class: str | None = None) -> int:
    """
    Tạo user mới.

    Args:
        username: Tên đăng nhập (UNIQUE)
        password_hash: bcrypt hash
        role: 'admin' | 'security' | 'management' | 'teacher'
        homeroom_class: Lớp chủ nhiệm (bắt buộc khi role='teacher')

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
                'INSERT INTO users (username, password_hash, role, homeroom_class) VALUES (?, ?, ?, ?)',
                (username, password_hash, role, homeroom_class)
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
        cursor.execute('SELECT id, username, role, homeroom_class, created_at FROM users ORDER BY created_at ASC')
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Tìm user theo ID."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, role, homeroom_class, created_at FROM users WHERE id = ?', (user_id,))
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


def update_user(user_id: int, role: str = None, password_hash: str = None,
                homeroom_class: str | None = None) -> bool:
    """
    Cập nhật user.

    Args:
        user_id: ID user cần sửa
        role: role mới (hoặc None để không đổi)
        password_hash: bcrypt hash mới (hoặc None để không đổi)
        homeroom_class: lớp chủ nhiệm (None = không đổi)

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
            if homeroom_class is not None:
                updates.append('homeroom_class = ?')
                params.append(homeroom_class)
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
                "NO_PLATE": int,
                "PLATE_OBSCURED": int,
                "PLATE_UNREADABLE": int,
                "MULTIPLE": int,
                "RIDING_THROUGH_GATE": int,
                "TOO_MANY_RIDERS": int,
            },
            "trend": [{"date": "YYYY-MM-DD", "count": int}, ...],  -- 14 ngày gần nhất, đủ ngày kể cả count=0
            "by_class": [{"class_name": str, "count": int}, ...],  -- "Không xác định" cho vi phạm không khớp biển số đăng ký
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
            "NO_PLATE": 0,
            "PLATE_OBSCURED": 0,
            "PLATE_UNREADABLE": 0,
            "MULTIPLE": 0,
            "RIDING_THROUGH_GATE": 0,
            "TOO_MANY_RIDERS": 0,
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

        # Xu hướng 14 ngày gần nhất — đủ điểm để vẽ biểu đồ đường mà không quá dày.
        # Điền đủ 0 cho ngày không có vi phạm (không chỉ trả về ngày có dữ liệu),
        # để trục thời gian trên chart liên tục, không bị nhảy cóc.
        cursor.execute(
            '''SELECT date(timestamp) as day, COUNT(*) as cnt
               FROM violation_events
               WHERE timestamp >= datetime('now', 'localtime', '-14 days')
               GROUP BY day'''
        )
        counts_by_day = {row["day"]: row["cnt"] for row in cursor.fetchall()}
        trend = []
        for i in range(13, -1, -1):
            day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            trend.append({"date": day, "count": counts_by_day.get(day, 0)})

        # Theo lớp — chỉ tính được cho vi phạm có plate_matched trùng xe đã đăng ký
        # (join registered_vehicles); vi phạm không khớp biển số gộp vào "Không xác định".
        cursor.execute(
            '''SELECT COALESCE(rv.student_class, 'Không xác định') as class_name, COUNT(*) as cnt
               FROM violation_events ve
               LEFT JOIN registered_vehicles rv ON rv.plate_number = ve.plate_matched
               GROUP BY class_name
               ORDER BY cnt DESC'''
        )
        by_class = [{"class_name": row["class_name"], "count": row["cnt"]} for row in cursor.fetchall()]

        return {
            "total_today": total_today,
            "total_week": total_week,
            "by_type": by_type,
            "trend": trend,
            "by_class": by_class,
        }
    finally:
        conn.close()


# ─── Feature 10: Violation audit trail ────────────────────────────────────────────

def update_violation_status(violation_id: int, status: str, actor_username: str, note: str = None) -> bool:
    """
    Cập nhật trạng thái vi phạm và ghi audit log.
    Feature 10.

    Args:
        violation_id: ID vi phạm
        status: 'reviewed' | 'resolved' | 'reopened'
        actor_username: username người thực hiện
        note: ghi chú tùy ý

    Returns:
        True nếu cập nhật thành công, False nếu violation_id không tồn tại
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Check violation exists
            cursor.execute("SELECT id FROM violation_events WHERE id = ?", (violation_id,))
            if cursor.fetchone() is None:
                return False
            # Update status
            cursor.execute(
                "UPDATE violation_events SET status = ? WHERE id = ?",
                (status, violation_id)
            )
            # Insert audit log (append-only, never overwrites)
            cursor.execute(
                "INSERT INTO violation_audit_log (violation_id, actor_username, action, note) VALUES (?, ?, ?, ?)",
                (violation_id, actor_username, status, note)
            )
            conn.commit()
            return True
        finally:
            conn.close()


def get_violation_audit_log(violation_id: int) -> list[dict]:
    """
    Lấy lịch sử audit log của một vi phạm.
    Feature 10.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM violation_audit_log WHERE violation_id = ? ORDER BY created_at ASC",
            (violation_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# ─── Đợt 2, Bước 4: System maintenance log ───────────────────────────────────

def log_maintenance_run(job_name: str, started_at: str, finished_at: str,
                        success: bool, detail: dict | None = None) -> int:
    """
    Ghi 1 lần chạy của maintenance job (cleanup tự động, backup — Bước 6) vào
    system_maintenance_log. Tái dùng `_write_lock` như mọi hàm ghi khác — chạy
    nền không cần chiếm lock lâu nhưng vẫn phải qua lock để khớp pattern.

    Trả về id của row vừa insert (dùng cho test xác nhận ghi đúng).
    """
    import json
    detail_json = json.dumps(detail) if detail is not None else None
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO system_maintenance_log "
                "(job_name, started_at, finished_at, success, detail_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (job_name, started_at, finished_at, 1 if success else 0, detail_json),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()


def list_maintenance_log(limit: int = 20) -> list[dict]:
    """
    Trả về các lần chạy maintenance gần nhất, mới nhất trước.
    Dùng cho API GET /api/system/maintenance-log (admin).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM system_maintenance_log ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# ─── Đợt 2, Bước 6: Backup SQLite online (không copy file thô) ───────────────

def backup_database(dest_path: str) -> None:
    """
    Backup an toàn app.db đang chạy, dùng SQLite online backup API
    (`sqlite3.Connection.backup()`) — API chính thức SQLite team làm riêng cho
    việc "backup DB đang chạy", từ Python 3.7+. Không copy file thô
    (rủi ro đọc giữa lúc ghi dở dang → backup hỏng/thiếu transaction).

    Chặn bởi `_write_lock` để tránh backup giữa lúc có transaction ghi đang mở
    (an toàn kép — dù `.backup()` tự nó đã an toàn ở cấp SQLite).
    Đảm bảo thư mục đích đã tồn tại (KHÔNG tự mkdir — caller quyết định policy).

    Raises:
        OSError: nếu không mở/ghi được file đích (do caller truyền path hợp lệ).
    """
    with _write_lock:
        source = get_connection()
        try:
            dest = sqlite3.connect(dest_path)
            try:
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()


def list_backup_files(backup_dir: str) -> list[dict]:
    """
    Liệt kê file backup trong `backup_dir`, mới nhất trước.
    Mỗi entry: {filename, path, size_mb, mtime_iso}.

    KHÔNG touch DB — chỉ list file vật lý. Dùng cho API GET /api/system/backup/list.
    """
    import glob as _glob
    out: list[dict] = []
    if not os.path.exists(backup_dir):
        return out
    for path in _glob.glob(os.path.join(backup_dir, "app_*.db")):
        try:
            stat = os.stat(path)
            out.append({
                "filename": os.path.basename(path),
                "path": path,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "mtime_iso": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
        except OSError:
            continue
    # Mới nhất trước
    out.sort(key=lambda r: r["mtime_iso"], reverse=True)
    return out


# ─── Feature 2 + 6: Repeat offender tracking ──────────────────────────────────

def get_student_violation_summary(student_class: str = None) -> list[dict]:
    """
    Group violation_events theo plate_matched, JOIN registered_vehicles.
    Feature 2 + 6.

    Trả về mỗi xe đã đăng ký: {vehicle_id, plate_number, student_name, student_class,
                                total_violations, violations_in_window, is_repeat_offender, last_violation_at}
    is_repeat_offender = violations_in_window >= REPEAT_OFFENDER_THRESHOLD
    Nếu student_class truyền vào, filter theo đúng lớp đó (dùng cho Feature 9).
    Xe chưa từng vi phạm vẫn xuất hiện với count=0 (LEFT JOIN từ registered_vehicles).
    """
    from app.config import REPEAT_OFFENDER_WINDOW_DAYS, REPEAT_OFFENDER_THRESHOLD

    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Lấy tổng vi phạm + vi phạm trong window cho mỗi xe
        cursor.execute('''
            SELECT
                rv.id AS vehicle_id,
                rv.plate_number,
                rv.student_name,
                rv.student_class,
                COUNT(ve.id) AS total_violations,
                SUM(CASE
                    WHEN ve.timestamp >= datetime('now', ?)
                    THEN 1 ELSE 0
                END) AS violations_in_window,
                MAX(ve.timestamp) AS last_violation_at
            FROM registered_vehicles rv
            LEFT JOIN violation_events ve ON ve.plate_matched = rv.plate_number
            WHERE (? IS NULL OR rv.student_class = ?)
            GROUP BY rv.id
            ORDER BY violations_in_window DESC, total_violations DESC
        ''', (f"-{REPEAT_OFFENDER_WINDOW_DAYS} days", student_class, student_class))

        rows = []
        for row in cursor.fetchall():
            violations_in_window = row["violations_in_window"] or 0
            rows.append({
                "vehicle_id": row["vehicle_id"],
                "plate_number": row["plate_number"],
                "student_name": row["student_name"],
                "student_class": row["student_class"],
                "total_violations": row["total_violations"] or 0,
                "violations_in_window": violations_in_window,
                "is_repeat_offender": violations_in_window >= REPEAT_OFFENDER_THRESHOLD,
                "last_violation_at": row["last_violation_at"],
            })
        return rows
    finally:
        conn.close()


def get_violations_by_vehicle(vehicle_id: int, limit: int = 100) -> list[dict]:
    """
    Toàn bộ lịch sử vi phạm của 1 xe/học sinh, sắp theo timestamp DESC.
    Feature 6 — dùng cho trang timeline.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ve.*, rv.student_name, rv.student_class
            FROM violation_events ve
            LEFT JOIN registered_vehicles rv ON rv.plate_number = ve.plate_matched
            WHERE ve.plate_matched = (
                SELECT plate_number FROM registered_vehicles WHERE id = ?
            )
            ORDER BY ve.timestamp DESC
            LIMIT ?
        ''', (vehicle_id, limit))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_vehicle_by_id(vehicle_id: int) -> Optional[dict]:
    """Tìm xe theo ID. Feature 6."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registered_vehicles WHERE id = ?", (vehicle_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_old_violation_media_paths(older_than_days: int = 90) -> tuple[List[str], List[str]]:
    """
    Trả về (snapshot_paths, clip_paths) cần xóa (cũ hơn older_than_days ngày).
    Chỉ trả về paths, không xóa gì cả.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cutoff = f"-{older_than_days} days"
        cursor.execute(
            "SELECT snapshot_path, clip_path FROM violation_events "
            "WHERE (snapshot_path IS NOT NULL OR clip_path IS NOT NULL) "
            "AND timestamp < datetime('now', ?)",
            (cutoff,)
        )
        snapshot_paths = []
        clip_paths = []
        for row in cursor.fetchall():
            if row["snapshot_path"]:
                snapshot_paths.append(row["snapshot_path"])
            if row["clip_path"]:
                clip_paths.append(row["clip_path"])
        return snapshot_paths, clip_paths
    finally:
        conn.close()


def get_old_violation_snapshot_paths(older_than_days: int = 90) -> List[str]:
    """
    Trả về danh sách snapshot_path cần xóa (cũ hơn older_than_days ngày).
    Chỉ trả về path, không xóa gì cả.
    """
    snapshot_paths, _ = get_old_violation_media_paths(older_than_days)
    return snapshot_paths


def clear_violation_snapshot_paths(older_than_days: int = 90) -> int:
    """
    Xóa file snapshot + clip cũ và set snapshot_path/clip_path = NULL trong DB.
    Giữ nguyên record vi phạm, chỉ null đường dẫn ảnh/video.
    Trả về số record đã null.
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cutoff = f"-{older_than_days} days"

            # Lấy cả snapshot_path và clip_path cần xóa
            cursor.execute(
                "SELECT snapshot_path, clip_path FROM violation_events "
                "WHERE (snapshot_path IS NOT NULL OR clip_path IS NOT NULL) "
                "AND timestamp < datetime('now', ?)",
                (cutoff,)
            )
            rows = cursor.fetchall()

            for row in rows:
                for path in (row['snapshot_path'], row['clip_path']):
                    if path:
                        full_path = path if os.path.isabs(path) else os.path.join(SNAPSHOTS_DIR, os.path.basename(path))
                        try:
                            if os.path.exists(full_path):
                                os.unlink(full_path)
                        except OSError:
                            pass

            # Null cả snapshot_path VÀ clip_path
            cursor.execute(
                "UPDATE violation_events "
                "SET snapshot_path = NULL, clip_path = NULL "
                "WHERE (snapshot_path IS NOT NULL OR clip_path IS NOT NULL) "
                "AND timestamp < datetime('now', ?)",
                (cutoff,)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()


# ─── Đợt 2, Bước 3: Ghép 1 lượt xe từ 2 camera (trước + sau) ────────────────

def find_correlation_candidates(new_event: dict, window_sec: float) -> list[dict]:
    """
    Tìm các violation_events ở gate khác, cùng cửa sổ thời gian ±window_sec,
    chưa bị ghép với ai (linked_violation_id IS NULL), để event_correlator.py
    chấm điểm chọn ứng viên tốt nhất.

    Args:
        new_event: dict tối thiểu có {'id', 'gate_id', 'timestamp', 'status'}.
            'gate_id' có thể None (chỉ có 1 gate) → trả về list rỗng.
        window_sec: cửa sổ ±giây quanh timestamp.

    Returns:
        List các dict row (id, gate_id, plate_read, plate_matched, status,
        timestamp). Rỗng nếu new_event.gate_id None hoặc không có ứng viên.
    """
    if not new_event.get("gate_id"):
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT id, gate_id, plate_read, plate_matched, status, timestamp
               FROM violation_events
               WHERE id != ?
                 AND gate_id != ?
                 AND linked_violation_id IS NULL
                 AND datetime(timestamp) BETWEEN datetime(?, ?) AND datetime(?, ?)
               ORDER BY timestamp ASC''',
            (
                new_event["id"],
                new_event["gate_id"],
                new_event["timestamp"], f"-{window_sec} seconds",
                new_event["timestamp"], f"+{window_sec} seconds",
            ),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def mark_correlation_unmatched(violation_id: int, status: str = 'unmatched') -> None:
    """
    Đánh dấu 1 violation là đã thử ghép nhưng KHÔNG tự ghép được (không có
    ứng viên phù hợp, hoặc có ứng viên nhưng không đủ tin cậy để tự ghép).

    status mặc định 'unmatched' (không tìm được ứng viên nào — chỉ 1 camera
    thấy xe này, bình thường). Truyền status='needs_review' khi
    event_correlator.find_correlation_candidate() trả về (None, 'needs_review')
    — tức CÓ ứng viên nhưng 1 trong 2 bên đã không chắc biển số từ Bước 1,
    hoặc bên mình không đọc được biển — bug đã gặp: nếu luôn hardcode
    'unmatched' ở đây, tín hiệu "cần người kiểm tra" từ event_correlator.py bị
    mất, người xem không biết đây là case mơ hồ cần chú ý.

    Dùng để phân biệt 'chưa thử' (NULL) vs 'đã thử không có' — tránh poll
    correlation job chạy đè lặp đi lặp lại.
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE violation_events SET correlation_status = ? "
                "WHERE id = ? AND correlation_status IS NULL",
                (status, violation_id),
            )
            conn.commit()
        finally:
            conn.close()


def link_violation_events(id_a: int, id_b: int, status: str = 'matched') -> bool:
    """
    Ghép 2 bản ghi vi phạm thành 1 lượt xe từ 2 camera (trước + sau).
    Cập nhật CẢ 2 record: linked_violation_id trỏ sang nhau, correlation_status
    đặt theo tham số. Chặn bởi _write_lock để tránh race khi 2 gate cùng
    insert event gần nhau và cả 2 cố ghép cùng lúc — chỉ 1 transaction thắng,
    transaction còn lại sẽ thấy linked_violation_id IS NULL đã bị set, fail
    UPDATE (rowcount=0) và trả False để caller biết đã có người ghép trước.

    Args:
        id_a, id_b: 2 ID violation_events cần ghép.
        status: 'matched' (tự tin ghép) | 'needs_review' (có ứng viên nhưng chưa đủ tự tin).

    Returns:
        True nếu ghép thành công, False nếu 1 trong 2 record đã bị ghép trước đó.
    """
    if id_a == id_b:
        return False
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Atomically claim both rows — chỉ update nếu cả 2 vẫn còn unlinked.
            # WHERE linked_violation_id IS NULL đảm bảo không ghi đè lên ghép đã có.
            cursor.execute(
                '''UPDATE violation_events
                   SET linked_violation_id = ?, correlation_status = ?
                   WHERE id = ? AND linked_violation_id IS NULL''',
                (id_b, status, id_a),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return False
            cursor.execute(
                '''UPDATE violation_events
                   SET linked_violation_id = ?, correlation_status = ?
                   WHERE id = ? AND linked_violation_id IS NULL''',
                (id_a, status, id_b),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return False
            conn.commit()
            return True
        finally:
            conn.close()


# ─── Vùng nhận diện (ROI) per-gate — xem app/cv/roi.py ───────────────────────

def get_gate_roi(gate_id: str) -> list | None:
    """Trả về danh sách điểm [[x,y],...] đã lưu cho gate, None nếu chưa cấu hình."""
    import json
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT points_json FROM gate_roi WHERE gate_id = ?", (gate_id,))
        row = cursor.fetchone()
        if not row:
            return None
        points = json.loads(row["points_json"])
        return points or None
    finally:
        conn.close()


def set_gate_roi(gate_id: str, points: list) -> None:
    """Lưu (hoặc thay thế) vùng ROI cho gate. `points=[]` nghĩa là tắt ROI."""
    import json
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO gate_roi (gate_id, points_json, updated_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(gate_id) DO UPDATE SET
                       points_json = excluded.points_json,
                       updated_at = excluded.updated_at''',
                (gate_id, json.dumps(points)),
            )
            conn.commit()
        finally:
            conn.close()


# ─── Nguồn camera per-gate — chọn qua /admin/camera ──────────────────────────

def get_gate_camera_source(gate_id: str) -> str | None:
    """Trả về source đã lưu cho gate, None nếu chưa từng đổi (dùng mặc định env)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT source FROM gate_camera_source WHERE gate_id = ?", (gate_id,))
        row = cursor.fetchone()
        return row["source"] if row else None
    finally:
        conn.close()


def set_gate_camera_source(gate_id: str, source: str) -> None:
    """Lưu (hoặc thay thế) nguồn camera cho gate."""
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO gate_camera_source (gate_id, source, updated_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(gate_id) DO UPDATE SET
                       source = excluded.source,
                       updated_at = excluded.updated_at''',
                (gate_id, source),
            )
            conn.commit()
        finally:
            conn.close()

