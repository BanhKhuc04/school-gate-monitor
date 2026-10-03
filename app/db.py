"""
Database operations using sqlite3 thuần.
Schema: registered_vehicles, violation_events (xem PLAN.md)
"""
import sqlite3
import threading
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from app.config import DB_PATH, SNAPSHOTS_DIR, STATS_TZ_OFFSET_HOURS, STATS_TZ_OFFSET_MINUTES


def vn_to_utc_range(date_str: str) -> tuple[str, str]:
    """
    T2.6 — chuyển 1 ngày local (Asia/Bangkok, UTC+7) sang khoảng UTC [start, end).

    Args:
        date_str: 'YYYY-MM-DD' trong múi VN.

    Returns:
        (utc_start_iso, utc_end_iso) — start là 00:00:00 VN của date_str,
        end là 00:00:00 VN của ngày kế tiếp. Khoảng [start, end) inclusive
        start, exclusive end — phù hợp query SQL >= AND <.
    """
    from app.config import STATS_TZ_OFFSET_HOURS as _OFF
    # Parse date naive
    y, m, d = date_str.split("-")
    start_local = datetime(int(y), int(m), int(d), 0, 0, 0)
    end_local = start_local + timedelta(days=1)
    # Convert to UTC by subtracting offset
    start_utc = start_local - timedelta(hours=_OFF)
    end_utc = end_local - timedelta(hours=_OFF)
    return (
        start_utc.strftime("%Y-%m-%d %H:%M:%S"),
        end_utc.strftime("%Y-%m-%d %H:%M:%S"),
    )


def vn_today_range() -> tuple[str, str]:
    """T2.6 — khoảng UTC tương ứng với 'hôm nay' theo Asia/Bangkok.

    Returns (utc_start, utc_end) — dùng để query ngày hôm nay theo giờ VN
    bất kể máy chủ đang ở múi nào.
    """
    from app.config import STATS_TZ_OFFSET_HOURS as _OFF
    # Dùng utcnow + offset thay vì datetime.now() để tránh phụ thuộc
    # system TZ. Nếu server ở UTC thì datetime.now() = UTC và cần +7h;
    # nếu server ở VN thì datetime.now() đã là VN và KHÔNG được +7h nữa.
    utc_now = datetime.utcnow()
    vn_today_str = (utc_now + timedelta(hours=_OFF)).strftime("%Y-%m-%d")
    return vn_to_utc_range(vn_today_str)


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

        # FR6 — recognition_reviews: gom tất cả proposal plate để admin/bảo vệ
        # duyệt đúng/sai mà không viết lại chuỗi bằng chứng vi phạm. Một
        # review_id = một crop biển cần xác nhận. Schema chuẩn hoá theo
        # plan FR6: review_id, crop media id/hash, camera/gate/run/epoch/frame,
        # proposal raw/canonical, model hash/config version, quality + observed_at.
        # `version` column = optimistic concurrency token; tăng mỗi feedback.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recognition_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id TEXT NOT NULL UNIQUE,
                violation_id INTEGER,
                encounter_id TEXT,
                gate_id TEXT NOT NULL,
                camera_id TEXT,
                run_id TEXT,
                source_epoch INTEGER NOT NULL,
                frame_seq INTEGER,
                observed_at TEXT NOT NULL,
                crop_media_id TEXT,
                crop_sha256 TEXT,
                proposal_raw TEXT NOT NULL,
                proposal_canonical TEXT NOT NULL,
                proposal_top_line TEXT,
                proposal_bottom_line TEXT,
                proposal_confidence REAL,
                proposal_engine TEXT NOT NULL,
                proposal_model_hash TEXT,
                proposal_config_version TEXT,
                quality_score REAL,
                blur_score REAL,
                contrast_score REAL,
                status TEXT NOT NULL DEFAULT 'pending',
                version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (violation_id) REFERENCES violation_events(id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_recognition_reviews_gate ON recognition_reviews(gate_id, observed_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_recognition_reviews_status ON recognition_reviews(status, observed_at DESC)')
        # Migration: thêm version column cho review cũ (FR6 optimistic concurrency).
        try:
            cursor.execute("ALTER TABLE recognition_reviews ADD COLUMN version INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        # FR6 — recognition_review_feedback: lưu LỊCH SỬ sửa của mỗi review.
        # KHÔNG ghi đè nhãn — mỗi lần duyệt tạo 1 row mới. Người dùng cuối
        # có thể xem lịch sử sửa để biết trước đó có sửa gì.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recognition_review_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id TEXT NOT NULL,
                reviewer_username TEXT NOT NULL,
                reviewer_role TEXT NOT NULL,
                verdict TEXT NOT NULL,
                corrected_text TEXT,
                expected_version INTEGER NOT NULL,
                note TEXT,
                idempotency_key TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (review_id) REFERENCES recognition_reviews(review_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_review_feedback_review ON recognition_review_feedback(review_id, created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_review_feedback_idempotency ON recognition_review_feedback(idempotency_key)')

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

        # R4 — bảng idempotency cho CSV import. import_id + payload_hash là
        # khóa chống submit lặp; result_json lưu response cũ để replay.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS import_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_id TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(import_id, payload_hash)
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_import_log_import_id
            ON import_log(import_id)
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

        # Đợt 1 (CURSOR_SYSTEM_STABILITY_PLAN_2026_09_30.md): một cổng vật lý
        # có thể có nhiều camera (vd. Imou trước/sau). Bảng `cameras` lưu
        # `camera_id` ổn định + vai trò `front`/`rear`. Track chỉ có ý
        # nghĩa trong bộ khóa `(camera_id, source_epoch, track_id)` — đây
        # là khóa tổng hợp cho việc chống trộn dữ liệu giữa hai nguồn.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cameras (
                camera_id     TEXT PRIMARY KEY,
                gate_id       TEXT NOT NULL,
                role          TEXT NOT NULL CHECK (role IN ('front', 'rear', 'aux')),
                source        TEXT NOT NULL,
                enabled       INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            )
        ''')
        # Index để tra cứu camera theo gate.
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cameras_gate
            ON cameras(gate_id, role)
        ''')

        # Đợt 1: từng `encounter_id` (1 lượt xe) có thể có nhiều camera
        # đóng góp quan sát. Bảng `encounter_observations` lưu raw evidence
        # theo `(encounter_id, camera_id)` — bằng chứng đã xác nhận ở mỗi
        # camera. Đây là nền tảng cho ghép trước/sau: mỗi camera đều có thể
        # ghi quan sát riêng mà không tạo event mới.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS encounter_observations (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id    TEXT NOT NULL,
                camera_id       TEXT NOT NULL,
                gate_id         TEXT NOT NULL,
                observed_at     TEXT NOT NULL,
                source_epoch    INTEGER NOT NULL,
                issues_json     TEXT,
                snapshot_path   TEXT,
                clip_path       TEXT,
                plate_read      TEXT,
                plate_matched   TEXT,
                helmet_status   TEXT,
                created_at      TEXT NOT NULL
            )
        ''')
        # T2.4 — provenance snapshot trên encounter_observations: tên/lớp tại
        # thời điểm ghi observation. KHÔNG đổi khi hồ sơ xe sau đó bị update.
        # NULL nếu biển không match hồ sơ (không suy đoán).
        try:
            cursor.execute(
                "ALTER TABLE encounter_observations ADD COLUMN student_name_at_event TEXT"
            )
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute(
                "ALTER TABLE encounter_observations ADD COLUMN student_class_at_event TEXT"
            )
        except sqlite3.OperationalError:
            pass
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_encounter_obs_encounter
            ON encounter_observations(encounter_id, camera_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_encounter_obs_camera
            ON encounter_observations(camera_id, observed_at DESC)
        ''')

        # Đợt 1 (System Stability): mapping 1 gate ↔ nhiều camera với role
        # (front/rear/aux). Mỗi camera có camera_id ổn định. Pipeline chọn
        # camera theo từng giai đoạn (front cho hành vi/mũ/crossing, rear
        # cho biển số + crop OCR). enabled=0 = tạm tắt, không xóa row.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gate_cameras (
                camera_id  TEXT PRIMARY KEY,
                gate_id    TEXT NOT NULL,
                role       TEXT NOT NULL CHECK (role IN ('front', 'rear', 'aux')),
                source     TEXT NOT NULL,
                enabled    INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gate_cameras_gate ON gate_cameras(gate_id)')

        # Compatibility with both recovered and deployed camera schemas.
        observation_columns = {r[1] for r in cursor.execute("PRAGMA table_info(encounter_observations)")}
        for name, definition in {
            "plate_confidence": "REAL", "posture_status": "TEXT", "extra_json": "TEXT",
            "issues_json": "TEXT", "snapshot_path": "TEXT", "clip_path": "TEXT",
            "plate_matched": "TEXT",
        }.items():
            if name not in observation_columns:
                cursor.execute(f"ALTER TABLE encounter_observations ADD COLUMN {name} {definition}")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_encounter_observation_identity "
                       "ON encounter_observations(encounter_id, camera_id, source_epoch)")

        # ── 2. Migrations cho bảng đã tồn tại (ALTER TABLE — an toàn nếu cột đã có) ──
        # posture_status + plate_format_valid (từ trước)
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN posture_status TEXT")
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

        # Đợt 1 (System Stability): phân biệt camera_id (nguồn hình cụ thể)
        # với gate_id (cổng vật lý). NULL = record cũ hoặc camera mặc định.
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN camera_id TEXT")
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

        # UT5: ảnh crop cận cảnh quanh bbox group vi phạm (giữ full-frame làm
        # ngữ cảnh, crop làm ảnh chính để bảo vệ/admin nhìn rõ chi tiết).
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN crop_snapshot_path TEXT")
        except sqlite3.OperationalError:
            pass

        # UT1: track_id của person khi vi phạm xảy ra (lưu cùng bản ghi để trace
        # nguồn, mặc dù backend không dùng lại — frontend có thể).
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN track_id INTEGER")
        except sqlite3.OperationalError:
            pass

        # Đợt 4: đường cắt gate (gate_line) — 2 điểm tọa độ chuẩn hóa [x1,y1,x2,y2] dạng
        # JSON. Nếu chưa cấu hình → NULL → RIDING_THROUGH_GATE dùng pose fallback cũ.
        # Đợt 4, D4.1: mở rộng gate_roi để lưu gate_line thay vì tạo bảng riêng
        # (giữ gần ROI, cùng pipeline cấu hình gate).
        try:
            cursor.execute("ALTER TABLE gate_roi ADD COLUMN gate_line_json TEXT")
        except sqlite3.OperationalError:
            pass

        # UT8: mở rộng bảng registered_vehicles với thông tin hồ sơ học sinh
        try:
            cursor.execute("ALTER TABLE registered_vehicles ADD COLUMN photo_path TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE registered_vehicles ADD COLUMN dob TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE registered_vehicles ADD COLUMN phone TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE registered_vehicles ADD COLUMN student_id TEXT")
        except sqlite3.OperationalError:
            pass

        # Đợt E2.1: encounter_id, issues[], observed_at, source_epoch
        # encounter_id: hex 1-lượt-xe (1 nhóm vi phạm từ cùng lượt tracker).
        # Nhiều violation cùng encounter = "1 lượt cập nhật nhiều issue" theo plan;
        # đợt D (ghép 2 camera) liên kết 2 encounter_id nếu khớp.
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN encounter_id TEXT")
        except sqlite3.OperationalError:
            pass
        # issues_json: danh sách Issue {code, status, reason, sample_count,
        # evidence_ref}. JSON vì schema issue có thể mở rộng sau. NULL = chưa
        # populate issues (record cũ, hoặc đơn lỗi MULTIPLE).
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN issues_json TEXT")
        except sqlite3.OperationalError:
            pass
        # observed_at: thời điểm quan sát đầu tiên (ISO). Khác timestamp
        # (thời điểm ghi log DB). NULL = fallback timestamp.
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN observed_at TEXT")
        except sqlite3.OperationalError:
            pass
        # E1: source_epoch từ pipeline truyền xuống DB. NULL = record cũ.
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN source_epoch INTEGER")
        except sqlite3.OperationalError:
            pass
        # Index cho encounter_id — query lấy tất cả issue của cùng lượt.
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_violation_events_encounter "
                           "ON violation_events(encounter_id)")
        except sqlite3.OperationalError:
            pass

        # S5: evidence_state — 'pending' (chưa ghi) | 'persisted' (snapshot+DB ok)
        # | 'failed' (imwrite/DB lỗi — alert không phát). NULL = record cũ,
        # coi như 'persisted' để không phá nghiệm vụ cũ.
        try:
            cursor.execute("ALTER TABLE violation_events ADD COLUMN evidence_state TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_violation_events_evidence_state "
                           "ON violation_events(evidence_state)")
        except sqlite3.OperationalError:
            pass

        # T2.4 — version: optimistic concurrency cho status update. Tăng mỗi
        # lần update_violation_status thành công. Client gửi expected_version,
        # mismatch → 409 (atomic CAS).
        try:
            cursor.execute(
                "ALTER TABLE violation_events ADD COLUMN version INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass

        # T2.4 — provenance snapshot: tên/lớp học sinh tại thời điểm ghi event.
        # Snapshot KHÔNG đổi khi hồ sơ xe hiện tại được sửa (đổi lớp, đổi tên).
        # NULL = event không match biển nào trong hồ sơ (không suy đoán).
        try:
            cursor.execute(
                "ALTER TABLE violation_events ADD COLUMN student_name_at_event TEXT"
            )
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute(
                "ALTER TABLE violation_events ADD COLUMN student_class_at_event TEXT"
            )
        except sqlite3.OperationalError:
            pass

        # UT8: bảng danh sách mã số hợp lệ (admin import trước) — public
        # register page kiểm tra student_id có trong roster mới cho đăng ký.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS student_roster (
                student_id   TEXT PRIMARY KEY,
                student_name TEXT NOT NULL,
                student_class TEXT NOT NULL,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')

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


def add_vehicle(plate_number: str, student_name: str, student_class: str,
                 photo_path: str | None = None, dob: str | None = None,
                 phone: str | None = None, student_id: str | None = None) -> int:
    """
    Thêm xe mới.

    Args:
        plate_number: Biển số (sẽ được chuẩn hóa)
        student_name: Tên học sinh
        student_class: Lớp
        photo_path, dob, phone, student_id: UT8 — field mở rộng, tùy chọn
            (trang /register công khai truyền vào lúc tạo mới, thay vì phải
            tạo xong rồi gọi update_vehicle() riêng).

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
                '''INSERT INTO registered_vehicles
                   (plate_number, student_name, student_class, photo_path, dob, phone, student_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (plate, student_name, student_class, photo_path, dob, phone, student_id)
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
                   student_name: str = None, student_class: str = None,
                   photo_path: str | None = None, dob: str | None = None,
                   phone: str | None = None, student_id: str | None = None) -> bool:
    """Cập nhật thông tin xe. UT8: thêm photo/dob/phone/student_id.

    Với các field mở rộng (UT8), phân biệt:
    - Tham số là None (mặc định) → KHÔNG cập nhật (giữ nguyên giá trị cũ).
    - Tham số là chuỗi rỗng "" → set NULL (xoá giá trị).
    - Tham số là chuỗi khác rỗng → set giá trị mới.
    Với 3 field cũ (plate_number/student_name/student_class), giữ hành vi cũ
    (None = giữ nguyên, không có "" semantics) để không phá code cũ.
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()

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

            # UT8: 4 field mở rộng. Chuỗi rỗng = set NULL.
            for col, val in (('photo_path', photo_path), ('dob', dob), ('phone', phone), ('student_id', student_id)):
                if val is None:
                    continue  # giữ nguyên
                updates.append(f'{col} = ?')
                params.append(val if val != "" else None)

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
                       crop_snapshot_path: str | None = None,
                       track_id: int | None = None,
                       encounter_id: str | None = None,
                       issues_json: str | None = None,
                       observed_at: str | None = None,
                       source_epoch: int | None = None,
                       camera_id: str | None = None,
                       evidence_state: str | None = None) -> int:
    """
    Thêm sự kiện vi phạm.

    Args:
        timestamp: ISO timestamp
        plate_read: Biển số đọc được (thô)
        plate_matched: Biển số khớp trong whitelist
        helmet_status: 'helmet' | 'no_helmet' | 'unknown'
        violation_type: 'NO_HELMET' | 'PLATE_NOT_REGISTERED' | 'RIDING_THROUGH_GATE' | ...
        snapshot_path: Đường dẫn ảnh chụp (full-frame)
        posture_status: 'standing' | 'riding' | 'unknown' | None
        plate_format_valid: biển đọc được có khớp định dạng VN không (None nếu không có plate_read)
        clip_path: Đường dẫn video clip ngắn (Feature 4)
        plate_confidence: độ tin cậy đọc biển số 0.0-1.0 (đợt 2, Bước 1 — PlateVoter)
        gate_id: camera nào tạo ra bản ghi này (đợt 2, Bước 1 — cần cho Bước 3 ghép 2 camera)
        status: 'pending' (mặc định) | 'needs_review' (AI không chắc chắn — Bước 1)
        crop_snapshot_path: Đường dẫn ảnh crop cận cảnh quanh bbox group vi phạm (UT5)
        track_id: track_id của person lúc vi phạm (UT1 — lưu để trace)
        encounter_id: UUID/hex 1-lượt-xe (E2.1). Nhiều record cùng encounter_id
            = cùng lượt. NULL = record cũ hoặc đơn lỗi MULTIPLE không có id lượt.
        issues_json: JSON string danh sách Issue {code, status, reason,
            sample_count, evidence_ref} (E2.1). NULL = record cũ hoặc đơn lỗi.
        observed_at: ISO thời điểm quan sát đầu tiên (E2.1). Khác timestamp.
            NULL = fallback timestamp.
        source_epoch: epoch từ pipeline (E1+R). NULL = record cũ.
        evidence_state: 'pending' | 'persisted' | 'failed' (S5). NULL = record cũ,
            mặc định 'persisted' để không phá nghiệp vụ cũ.

    Returns:
        ID của sự kiện mới
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # T2.4 — provenance snapshot: nếu plate_matched trỏ tới xe đã
            # đăng ký, snapshot student_name + student_class NGAY tại thời
            # điểm ghi event. Snapshot này KHÔNG đổi khi hồ sơ xe sau đó
            # được update (đổi lớp, đổi tên, archive).
            snapshot_name = None
            snapshot_class = None
            if plate_matched:
                vrow = cursor.execute(
                    "SELECT student_name, student_class FROM registered_vehicles WHERE plate_number = ?",
                    (plate_matched,),
                ).fetchone()
                if vrow is not None:
                    snapshot_name = vrow["student_name"]
                    snapshot_class = vrow["student_class"]
            cursor.execute(
                '''INSERT INTO violation_events
                   (timestamp, plate_read, plate_matched, helmet_status, violation_type, snapshot_path, posture_status, plate_format_valid, clip_path, plate_confidence, gate_id, status, crop_snapshot_path, track_id, encounter_id, issues_json, observed_at, source_epoch, camera_id, evidence_state, student_name_at_event, student_class_at_event)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (timestamp, plate_read, plate_matched, helmet_status, violation_type, snapshot_path, posture_status,
                 None if plate_format_valid is None else int(plate_format_valid), clip_path,
                 plate_confidence, gate_id, status, crop_snapshot_path, track_id,
                 encounter_id, issues_json, observed_at, source_epoch, camera_id,
                 evidence_state or 'persisted', snapshot_name, snapshot_class)
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
            conditions.append('ve.violation_type = ?')
            params.append(violation_type)
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


def list_violation_encounters(
    limit: int = 50,
    offset: int = 0,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    student_class: Optional[str] = None,
    plate: Optional[str] = None,
    violation_type: Optional[str] = None,
) -> dict:
    """
    Pre-E3 fix plan: gom encounter TRƯỚC khi phân trang.

    Trả về:
        - total: Tổng số encounter_id KHÁC NHAU khớp filter (KHÔNG phải số
          violation row trong trang đang lấy). Đảm bảo frontend hiển thị
          phân trang đúng khi có nhiều violation trong cùng encounter.
        - limit/offset: Phân trang theo số encounter (không phải số row).
        - items: List[dict] encounter, mỗi item có:
            + encounter_id, gate_id, observed_at, plate_read, plate_matched,
              helmet_status, issues[], violation_ids[], snapshot_path,
              crop_snapshot_path, clip_path, display_status.
            + display_status ∈ {red, yellow, gray, resolved} — đã tính sẵn
              (priority resolved>confirmed>conflict>deferred>pending).

    Hợp đồng: KHÔNG tải toàn bộ dữ liệu vào Python để gom — dùng SQL gom
    theo encounter_id rồi JOIN lại metadata. Cho phép test với >200 bản ghi
    mà vẫn nhanh.

    Args:
        limit: Số encounter tối đa mỗi trang (1-200, mặc định 50).
        offset: Bỏ qua N encounter đầu (>=0, mặc định 0).
        date_from/date_to: ISO timestamp filter (inclusive).
        student_class: Filter lớp (teacher scope).
    """
    import json as _json
    from collections import OrderedDict

    conn = get_connection()
    try:
        if not conn.in_transaction:
            conn.execute("BEGIN")
        cursor = conn.cursor()

        conditions = []
        params: List = []

        if date_from:
            conditions.append('ve.timestamp >= ?')
            params.append(date_from)
        if date_to:
            conditions.append('ve.timestamp <= ?')
            params.append(date_to)
        if student_class:
            conditions.append('rv.student_class = ?')
            params.append(student_class)

        if plate:
            conditions.append('(ve.plate_read LIKE ? OR ve.plate_matched LIKE ?)')
            params.extend([f'%{plate}%', f'%{plate}%'])
        if violation_type:
            conditions.append("(ve.violation_type = ? OR EXISTS (SELECT 1 FROM json_each(CASE WHEN json_valid(ve.issues_json) THEN ve.issues_json ELSE '[]' END) issue WHERE json_extract(issue.value, '$.code') = ?))")
            params.extend([violation_type, violation_type])

        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        # 1. Tổng số encounter_id KHÁC NHAU khớp filter (count distinct).
        cursor.execute(
            f'''
            SELECT COUNT(DISTINCT COALESCE(NULLIF(ve.encounter_id, ''), 'legacy-' || ve.id))
            FROM violation_events ve
            LEFT JOIN registered_vehicles rv ON rv.plate_number = ve.plate_matched
            WHERE {where_clause}
            ''',
            params,
        )
        total = cursor.fetchone()[0]

        # 2. Lấy distinct encounter_ids của "trang hiện tại" — theo thứ tự
        #    mới nhất của violation đầu tiên trong encounter (ORDER BY MIN(timestamp)).
        #    Chia offset/limit theo số encounter, KHÔNG phải số row.
        #    QUAN TRỌNG: phải GROUP BY cùng biểu thức COALESCE(NULLIF(...),'legacy-')
        #    dùng cho COUNT DISTINCT. Nếu GROUP BY encounter_id (chỉ cột gốc) thì
        #    các row encounter_id=NULL sẽ bị gộp vào 1 nhóm duy nhất → sai.
        eid_expr = "COALESCE(NULLIF(ve.encounter_id, ''), 'legacy-' || ve.id)"
        page_query = f'''
            SELECT {eid_expr} AS encounter_id,
                   MIN(ve.timestamp) AS first_ts
            FROM violation_events ve
            LEFT JOIN registered_vehicles rv ON rv.plate_number = ve.plate_matched
            WHERE {where_clause}
            GROUP BY {eid_expr}
            ORDER BY first_ts DESC, encounter_id DESC
            LIMIT ? OFFSET ?
        '''
        cursor.execute(page_query, params + [limit, offset])
        page_encounters = [dict(r) for r in cursor.fetchall()]

        if not page_encounters:
            return {'total': total, 'limit': limit, 'offset': offset, 'items': []}

        page_encounter_ids = [e['encounter_id'] for e in page_encounters]

        # 3. Lấy TẤT CẢ violation rows của các encounter trong trang này.
        placeholders = ','.join('?' * len(page_encounter_ids))
        scope_clause = ' AND rv.student_class = ?' if student_class else ''
        rows_query = f'''
            SELECT ve.*, rv.student_name, rv.student_class,
                   COALESCE(NULLIF(ve.encounter_id, ''), 'legacy-' || ve.id) AS eid
            FROM violation_events ve
            LEFT JOIN registered_vehicles rv ON rv.plate_number = ve.plate_matched
            WHERE COALESCE(NULLIF(ve.encounter_id, ''), 'legacy-' || ve.id)
                  IN ({placeholders}) {scope_clause}
            ORDER BY ve.timestamp ASC, ve.id ASC
        '''
        cursor.execute(rows_query, page_encounter_ids + ([student_class] if student_class else []))
        all_rows = [dict(r) for r in cursor.fetchall()]

        # 4. Gom theo encounter_id trong Python (chỉ trong tập encounter_ids của trang)
        groups: "OrderedDict[str, dict]" = OrderedDict()
        _PRIO = {"resolved": 4, "confirmed": 3, "conflict": 2,
                 "deferred": 1, "pending": 0}

        for row in all_rows:
            eid = row.get('eid') or f"legacy-{row['id']}"
            if eid not in groups:
                groups[eid] = {
                    "id": row["id"],
                    "timestamp": row.get("timestamp"),
                    "status": row.get("status") or "pending",
                    "student_name": row.get("student_name"),
                    "student_class": row.get("student_class"),
                    "violation_type": row.get("violation_type"),
                    "evidence_state": row.get("evidence_state"),
                    "encounter_id": eid,
                    "gate_id": row.get('gate_id'),
                    "observed_at": row.get('observed_at') or row.get('timestamp'),
                    "plate_read": row.get('plate_read'),
                    "plate_matched": row.get('plate_matched'),
                    "helmet_status": row.get('helmet_status'),
                    "issues": [],
                    "violation_ids": [],
                    "snapshot_path": row.get('snapshot_path'),
                    "crop_snapshot_path": row.get('crop_snapshot_path'),
                    "clip_path": row.get('clip_path'),
                }
            bucket = groups[eid]
            # Union snapshot (lấy ảnh đầu tiên)
            if not bucket["snapshot_path"] and row.get('snapshot_path'):
                bucket["snapshot_path"] = row['snapshot_path']
                bucket["crop_snapshot_path"] = row.get('crop_snapshot_path')
                bucket["clip_path"] = row.get('clip_path')
            bucket["violation_ids"].append(row["id"])
            # Parse + dedup issues_json
            if row.get('issues_json'):
                try:
                    parsed = _json.loads(row['issues_json'])
                    if isinstance(parsed, list):
                        existing = {it.get('code'): it for it in bucket['issues']}
                        for it in parsed:
                            code = it.get('code')
                            if code not in existing or _PRIO.get(it.get('status'), 0) > _PRIO.get(existing[code].get('status'), 0):
                                existing[code] = it
                        bucket['issues'] = list(existing.values())
                except Exception:
                    pass

        # 5. Tính display_status cho mỗi group:
        #    resolved > red (confirmed) > yellow (pending/deferred/conflict) > gray.
        #    Quan trọng: nếu vừa có resolved vừa có confirmed → red (vẫn còn lỗi).
        #    Nếu chỉ toàn resolved → resolved.
        #    Nếu chỉ có resolved + pending/deferred → yellow (cần xem xét).
        for bucket in groups.values():
            issues = bucket['issues']
            has_resolved = any(it.get('status') == 'resolved' for it in issues)
            has_confirmed = any(it.get('status') == 'confirmed' for it in issues)
            has_pending_or_deferred = any(it.get('status') in ('pending', 'deferred', 'conflict') for it in issues)
            has_any = len(issues) > 0
            all_resolved = all(it.get('status') == 'resolved' for it in issues) if has_any else False

            if has_any and all_resolved:
                bucket['display_status'] = 'resolved'
            elif has_confirmed:
                # Có ít nhất 1 confirmed chưa resolved → đỏ
                bucket['display_status'] = 'red'
            elif has_pending_or_deferred:
                bucket['display_status'] = 'yellow'
            elif has_resolved:
                # Chỉ có resolved nhưng không có confirmed/pending → xem là resolved
                bucket['display_status'] = 'resolved'
            else:
                bucket['display_status'] = 'gray'

        # 6. Sắp xếp lại theo thứ tự first_ts DESC của page_encounters
        ordered_items = [groups[eid] for eid in page_encounter_ids if eid in groups]

        return {
            'total': total,
            'limit': limit,
            'offset': offset,
            'items': ordered_items,
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


def update_user_atomic(user_id: int, role: str = None, password_hash: str = None,
                        homeroom_class: str | None = None) -> dict:
    """
    T2.4 — atomic update user với last-admin check trong transaction.

    Trước khi UPDATE role, hàm này re-count số admin hiện tại TRONG cùng
    transaction với UPDATE. Nếu user này là admin DUY NHẤT và đang bị demote
    → return error (không mutate). Tránh race condition giữa count và
    update mà API cũ có thể bị (check-then-act ngoài transaction).

    Args:
        user_id, role, password_hash, homeroom_class: xem update_user().

    Returns:
        dict {"ok": True} | {"ok": False, "error": <reason>}
        error ∈ {"not_found", "last_admin_demote", "last_admin_delete_when_admin"}
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Lock row hiện tại
            cursor.execute(
                "SELECT id, role FROM users WHERE id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if row is None:
                return {"ok": False, "error": "not_found"}
            current_role = row["role"]
            # Nếu đang demote một admin → đếm lại admin TRONG transaction này
            if role is not None and current_role == "admin" and role != "admin":
                cursor.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin'"
                )
                admin_count = cursor.fetchone()[0]
                if admin_count <= 1:
                    return {"ok": False, "error": "last_admin_demote"}
            # Build update
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
                return {"ok": False, "error": "no_change"}
            params.append(user_id)
            cursor.execute(
                f'UPDATE users SET {", ".join(updates)} WHERE id = ?',
                params,
            )
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()


def delete_user_atomic(user_id: int, requesting_username: str) -> dict:
    """
    T2.4 — atomic delete user với last-admin check + self-delete check.

    Returns:
        dict {"ok": True} | {"ok": False, "error": <reason>}
        error ∈ {"not_found", "self_delete", "last_admin"}
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, role, username FROM users WHERE id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if row is None:
                return {"ok": False, "error": "not_found"}
            if row["username"] == requesting_username:
                return {"ok": False, "error": "self_delete"}
            if row["role"] == "admin":
                # Re-count admin TRONG transaction này
                cursor.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin'"
                )
                admin_count = cursor.fetchone()[0]
                if admin_count <= 1:
                    return {"ok": False, "error": "last_admin"}
            cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            return {"ok": True}
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
    Thống kê vi phạm — T2.6: múi giờ Asia/Bangkok + issues[] aggregation.

    Lưu ý quan trọng:
    - timestamp lưu UTC (ISO 8601 'YYYY-MM-DD HH:MM:SS').
    - "hôm nay" / "7 ngày qua" tính theo Asia/Bangkok (UTC+7) chứ không
      theo system localtime. T2.6 tránh lệch biên giờ khi server ở múi
      khác.
    - by_issue: đếm theo code trong issues_json (HỢP ĐỒNG Task 1). Cũ
      (chưa có issues_json) đếm theo violation_type qua adapter.

    Returns:
        {
            "total_today": int,         -- event hôm nay theo VN
            "total_week": int,          -- event 7 ngày qua theo VN
            "total_encounters_today": int,  -- encounter_id duy nhất hôm nay
            "by_type": {               -- đếm theo violation_type (legacy)
                "NO_HELMET": int,
                ...
            },
            "by_issue": {              -- T2.6: đếm theo issues[].code
                "NO_HELMET": int,
                "PLATE_NOT_REGISTERED": int,
                ...
            },
            "by_issue_status": {       -- T2.6: đếm issue theo status
                "confirmed": int,
                "deferred": int,
                "conflict": int,
                "pending": int,
                "resolved": int,
            },
            "trend": [{"date": "YYYY-MM-DD", "count": int}, ...],
            "by_class": [{"class_name": str, "count": int}, ...],
            "tz_info": {"tz_offset_hours": 7, "server_now_utc": "..."},
        }
    """
    import json as _json
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Today: dùng VN timezone để tính 'hôm nay'
        today_start, today_end = vn_today_range()
        cursor.execute(
            "SELECT COUNT(*) FROM violation_events "
            "WHERE timestamp >= ? AND timestamp < ?",
            (today_start, today_end),
        )
        total_today = cursor.fetchone()[0]

        # Tổng encounter_id duy nhất hôm nay — T2.6 tách bạch event/encounter
        cursor.execute(
            "SELECT COUNT(DISTINCT encounter_id) FROM violation_events "
            "WHERE encounter_id IS NOT NULL "
            "AND timestamp >= ? AND timestamp < ?",
            (today_start, today_end),
        )
        row = cursor.fetchone()
        total_encounters_today = row[0] if row and row[0] else 0

        # Last 7 days — VN timezone
        # Tính ngày VN cách đây 7 ngày (theo VN), chuyển sang UTC range
        utc_now = datetime.utcnow()
        vn_now = utc_now + timedelta(hours=STATS_TZ_OFFSET_HOURS)
        week_ago_vn = (vn_now - timedelta(days=7)).strftime("%Y-%m-%d")
        week_start_utc, _ = vn_to_utc_range(week_ago_vn)
        cursor.execute(
            "SELECT COUNT(*) FROM violation_events WHERE timestamp >= ?",
            (week_start_utc,),
        )
        total_week = cursor.fetchone()[0]

        # By violation_type (legacy column — fallback khi issues_json rỗng)
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

        # T2.6 — by_issue: đếm theo issues[].code. Dùng json_each để iterate.
        # Một event có N issues → đếm N lần (đúng nghiệp vụ: 1 lượt có 2 lỗi
        # = 2 issue). Legacy (issues_json rỗng/NULL) fallback theo violation_type
        # để không đếm sai.
        by_issue: Dict[str, int] = {
            "NO_HELMET": 0,
            "PLATE_NOT_REGISTERED": 0,
            "NO_PLATE": 0,
            "PLATE_OBSCURED": 0,
            "PLATE_UNREADABLE": 0,
            "RIDING_THROUGH_GATE": 0,
            "TOO_MANY_RIDERS": 0,
            "MULTIPLE": 0,
            "OTHER": 0,
        }
        by_issue_status: Dict[str, int] = {
            "confirmed": 0,
            "deferred": 0,
            "conflict": 0,
            "pending": 0,
            "resolved": 0,
        }
        # Lấy tất cả violation_events có issues_json hợp lệ + status enum
        cursor.execute(
            "SELECT issues_json, violation_type FROM violation_events"
        )
        for row in cursor.fetchall():
            issues_str = row["issues_json"]
            vt = row["violation_type"]
            try:
                issues = _json.loads(issues_str) if issues_str else []
            except (ValueError, TypeError):
                issues = []
            if not issues:
                # Legacy: dùng violation_type như 'issue' duy nhất
                code = vt or "OTHER"
                if code in by_issue:
                    by_issue[code] += 1
                else:
                    by_issue["OTHER"] += 1
                by_issue_status["confirmed"] += 1
            else:
                for issue in issues:
                    code = issue.get("code") if isinstance(issue, dict) else None
                    status = issue.get("status") if isinstance(issue, dict) else None
                    if not code:
                        continue
                    if code in by_issue:
                        by_issue[code] += 1
                    else:
                        by_issue["OTHER"] += 1
                    if status in by_issue_status:
                        by_issue_status[status] += 1

        # Xu hướng 14 ngày gần nhất — dùng VN timezone
        # Lấy tất cả event trong 14 ngày VN gần nhất
        # Dùng utcnow + offset để đảm bảo đúng bất kể system TZ
        utc_now = datetime.utcnow()
        vn_now = utc_now + timedelta(hours=STATS_TZ_OFFSET_HOURS)
        counts_by_day: Dict[str, int] = {}
        for i in range(14):
            day_vn = (vn_now - timedelta(days=i)).strftime("%Y-%m-%d")
            day_start_utc, day_end_utc = vn_to_utc_range(day_vn)
            cursor.execute(
                "SELECT COUNT(*) FROM violation_events "
                "WHERE timestamp >= ? AND timestamp < ?",
                (day_start_utc, day_end_utc),
            )
            cnt = cursor.fetchone()[0]
            counts_by_day[day_vn] = cnt

        trend = []
        for i in range(13, -1, -1):
            day = (vn_now - timedelta(days=i)).strftime("%Y-%m-%d")
            trend.append({"date": day, "count": counts_by_day.get(day, 0)})

        # Theo lớp — dùng student_class_at_event nếu có (provenance), fallback về
        # current student_class qua join (legacy data không có provenance).
        cursor.execute(
            '''SELECT COALESCE(ve.student_class_at_event, rv.student_class, 'Không xác định') as class_name,
                      COUNT(*) as cnt
               FROM violation_events ve
               LEFT JOIN registered_vehicles rv ON rv.plate_number = ve.plate_matched
               GROUP BY class_name
               ORDER BY cnt DESC'''
        )
        by_class = [{"class_name": row["class_name"], "count": row["cnt"]} for row in cursor.fetchall()]

        return {
            "total_today": total_today,
            "total_week": total_week,
            "total_encounters_today": total_encounters_today,
            "by_type": by_type,
            "by_issue": by_issue,
            "by_issue_status": by_issue_status,
            "trend": trend,
            "by_class": by_class,
            "tz_info": {
                "tz_offset_hours": STATS_TZ_OFFSET_HOURS,
                "server_now_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }
    finally:
        conn.close()


# ─── Feature 10: Violation audit trail ────────────────────────────────────────────

def update_violation_status(violation_id: int, status: str, actor_username: str,
                             note: str = None,
                             expected_version: int | None = None) -> dict:
    """
    Cập nhật trạng thái vi phạm và ghi audit log.
    Feature 10 + T2.4 — optimistic concurrency.

    Args:
        violation_id: ID vi phạm
        status: 'reviewed' | 'resolved' | 'reopened'
        actor_username: username người thực hiện
        note: ghi chú tùy ý
        expected_version: version client thấy; nếu khác version hiện tại → 409.
            None = bỏ qua kiểm tra (legacy/dev path; production PHẢI truyền).

    Returns:
        dict:
          - on success: {"ok": True, "version": <new_version>}
          - not found: {"ok": False, "error": "not_found"}
          - conflict: {"ok": False, "error": "version_conflict",
                       "current_version": <int>}
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, version FROM violation_events WHERE id = ?",
                (violation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return {"ok": False, "error": "not_found"}
            current_version = row["version"] or 0
            if expected_version is not None and expected_version != current_version:
                return {
                    "ok": False,
                    "error": "version_conflict",
                    "current_version": current_version,
                }
            new_version = current_version + 1
            cursor.execute(
                "UPDATE violation_events SET status = ?, version = ? WHERE id = ?",
                (status, new_version, violation_id),
            )
            # Insert audit log (append-only, never overwrites) — cùng transaction
            cursor.execute(
                "INSERT INTO violation_audit_log (violation_id, actor_username, action, note) VALUES (?, ?, ?, ?)",
                (violation_id, actor_username, status, note),
            )
            conn.commit()
            return {"ok": True, "version": new_version}
        finally:
            conn.close()


def update_violation_issues(violation_id: int, issues_json: str | None,
                              observed_at: str | None = None,
                              encounter_id: str | None = None) -> bool:
    """E2.1: cập nhật issues[] (JSON) cho 1 violation_event.

    Idempotent — gọi nhiều lần cùng nội dung là không lỗi. Kết quả OCR/mũ
    đến trễ sẽ được merge vào cùng event (không tạo row mới, không lùi
    trạng thái xử lý nghiệp vụ).

    Args:
        violation_id: ID bản ghi cần cập nhật.
        issues_json: JSON string danh sách Issue. None = không thay đổi.
        observed_at: ISO thời điểm quan sát đầu tiên. None = không thay đổi
            (giữ giá trị cũ). Nếu record chưa có observed_at thì set.
        encounter_id: hex 1-lượt. None = không thay đổi.

    Returns:
        True nếu cập nhật thành công, False nếu violation_id không tồn tại.
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, observed_at FROM violation_events WHERE id = ?",
                           (violation_id,))
            row = cursor.fetchone()
            if row is None:
                return False
            # Build dynamic SET: chỉ cập nhật field được truyền.
            sets: List[str] = []
            params: List = []
            if issues_json is not None:
                sets.append("issues_json = ?")
                params.append(issues_json)
            if observed_at is not None:
                # observed_at chỉ set nếu chưa có (giữ frame quan sát đầu).
                if row["observed_at"] is None:
                    sets.append("observed_at = ?")
                    params.append(observed_at)
            if encounter_id is not None:
                sets.append("encounter_id = ?")
                params.append(encounter_id)
            if not sets:
                return True
            params.append(violation_id)
            cursor.execute(
                f"UPDATE violation_events SET {', '.join(sets)} WHERE id = ?",
                params,
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


# ─── R4 — Idempotency helpers cho CSV import ──────────────────────────────────
import json as _json

def save_import_log(import_id: str, payload_hash: str, result: dict) -> bool:
    """Lưu kết quả import để replay cùng import_id + payload_hash.
    Trả về True nếu lưu thành công; False nếu (import_id, payload_hash) đã tồn tại.
    """
    with _write_lock:
        conn = get_connection()
        try:
            cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO import_log (import_id, payload_hash, result_json, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (import_id, payload_hash,
                     _json.dumps(result, ensure_ascii=False, default=str),
                     datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
        finally:
            conn.close()


def get_import_log(import_id: str, payload_hash: str) -> dict | None:
    """Lấy kết quả đã lưu cho (import_id, payload_hash). None nếu không có."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT result_json FROM import_log WHERE import_id = ? AND payload_hash = ?",
            (import_id, payload_hash),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _json.loads(row["result_json"])
    finally:
        conn.close()


def payload_hash_from_bytes(data: bytes) -> str:
    """SHA256 hex của file CSV bytes — dùng cho idempotency key."""
    import hashlib as _hashlib
    return _hashlib.sha256(data).hexdigest()


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


def compute_backup_manifest(backup_path: str) -> dict:
    """
    T2.8 — tính manifest cho 1 file backup DB.

    Manifest bao gồm:
      - filename, size_bytes, sha256, created_at_utc
      - integrity: 'ok' | 'corrupt' | 'unreadable'

    Mục đích:
      - Verify backup KHÔNG bị tham nhũng trước khi restore.
      - Cung cấp checksum cho audit (so với manifest cũ để phát hiện file
        bị overwrite hoặc sai vị trí).
      - Phân biệt backup 'complete' (integrity='ok') với file dở dang
        (integrity khác 'ok').

    Args:
        backup_path: đường dẫn tuyệt đối tới file backup.

    Returns:
        dict manifest. integrity='unreadable' nếu không mở được file.
    """
    import hashlib as _hashlib
    result = {
        "filename": os.path.basename(backup_path),
        "path": backup_path,
        "size_bytes": 0,
        "sha256": "",
        "created_at_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "integrity": "unreadable",
    }
    if not os.path.exists(backup_path):
        return result
    try:
        size = os.path.getsize(backup_path)
        result["size_bytes"] = size
        # SHA256 đọc theo chunk để không nạp hết file vào RAM
        h = _hashlib.sha256()
        with open(backup_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        result["sha256"] = h.hexdigest()
        # integrity_check
        conn = sqlite3.connect(backup_path)
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            row = cur.fetchone()
            if row and row[0] == "ok":
                result["integrity"] = "ok"
            else:
                result["integrity"] = "corrupt"
        finally:
            conn.close()
    except OSError:
        result["integrity"] = "unreadable"
    return result


# ─── R3: Backup theo bộ DB + media + manifest + complete marker ─────────────
# F04 — codex review: backup hiện chỉ có 1 file DB; chưa có manifest của
# bộ dữ liệu (snapshot/crop/clip/student_photos), chưa có complete marker
# atomic, retention chưa gom theo bộ.
#
# Helper create_backup_set() thực hiện:
#   1. Backup DB qua backup_database().
#   2. Copy snapshot/crop/clip (SNAPSHOTS_DIR) và student_photos nếu được
#      truyền vào. Mỗi file copy với sha256 để verify.
#   3. Tạo manifest.json với danh sách file + size + sha256 + role
#      (db|media|photo).
#   4. Verify integrity DB; verify từng media file theo sha256 (best-effort).
#   5. Atomic write marker file `complete` chỉ khi TẤT CẢ phần verify xong.
#   6. Nếu có phần fail → KHÔNG ghi marker, trả status='incomplete' với
#      paths_failed[].
#
# Helper verify_backup_set(): đọc manifest + verify lại; trả dict có
# 'complete' bool + 'db_integrity' + 'media_missing'.
#
# Helper restore_backup_set(): copy manifest files + DB sang root mới
# (KHÔNG ghi đè DB/media vận hành), mở verify integrity DB, trả dict có
# 'db_ok' + 'media_restored_count' + 'media_missing'.
#
# Helper prune_backup_sets(): dọn bộ backup cũ theo retention policy (giữ
# N bộ mới nhất). Dọn TOÀN BỘ bộ (DB + media + manifest), không để lại
# blob vô hạn.

def create_backup_set(
    backup_root: str,
    snapshots_dir: str,
    student_photos_dir: str | None = None,
    include_media: bool = True,
    label: str | None = None,
    cancel_event=None,
) -> dict:
    """Tạo 1 bộ backup DB + media + manifest trong `backup_root`.

    Args:
        backup_root: thư mục cha. Helper sẽ tạo 1 subdir theo timestamp UTC.
        snapshots_dir: thư mục chứa snapshot/crop/clip để copy.
        student_photos_dir: thư mục ảnh hồ sơ (tùy chọn).
        include_media: có copy media không (mặc định True).
        label: nhãn tuỳ ý (vd. 'hourly' | 'end_of_shift').

    Returns:
        dict {
          'set_dir': đường dẫn subdir bộ backup,
          'db_file': tên file DB,
          'media_dir': tên subdir media (hoặc None),
          'manifest_file': 'manifest.json',
          'complete': bool — True nếu marker complete được ghi,
          'files': list[dict] các entry (path_rel, size_bytes, sha256, role),
          'paths_failed': list[dict] các file copy/verify fail,
        }
    """
    import hashlib as _hashlib
    import shutil as _shutil

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    safe_label = "".join(c if c.isalnum() or c in "-_." else "_" for c in (label or "set"))
    set_dir_name = f"{ts}_{safe_label}"
    set_dir = os.path.join(backup_root, set_dir_name)
    os.makedirs(set_dir, exist_ok=True)

    db_name = f"app_{ts}.db"
    db_path = os.path.join(set_dir, db_name)
    files_meta: list[dict] = []
    paths_failed: list[dict] = []

    # 1. Backup DB
    try:
        backup_database(db_path)
        size = os.path.getsize(db_path)
        with open(db_path, "rb") as f:
            h = _hashlib.sha256()
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        files_meta.append({
            "path_rel": db_name,
            "size_bytes": size,
            "sha256": h.hexdigest(),
            "role": "db",
        })
    except Exception as e:
        paths_failed.append({"path": db_name, "reason": f"db_backup: {e}"})

    # 2. Copy media (nếu bật)
    media_dir_name = "media"
    media_dir_path = os.path.join(set_dir, media_dir_name) if include_media else None
    if include_media:
        try:
            os.makedirs(media_dir_path, exist_ok=True)
        except Exception as e:
            paths_failed.append({"path": media_dir_name, "reason": f"mkdir: {e}"})
            media_dir_path = None

        if media_dir_path and os.path.isdir(snapshots_dir):
            for entry in os.listdir(snapshots_dir):
                if cancel_event is not None and cancel_event.is_set():
                    paths_failed.append({"path": media_dir_name, "reason": "shutdown_cancelled"})
                    break
                src = os.path.join(snapshots_dir, entry)
                if not os.path.isfile(src):
                    continue
                dst_name = entry
                dst = os.path.join(media_dir_path, dst_name)
                try:
                    _shutil.copy2(src, dst)
                    size = os.path.getsize(dst)
                    with open(dst, "rb") as f:
                        h = _hashlib.sha256()
                        while True:
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            h.update(chunk)
                    files_meta.append({
                        "path_rel": f"{media_dir_name}/{dst_name}",
                        "size_bytes": size,
                        "sha256": h.hexdigest(),
                        "role": "media",
                    })
                except Exception as e:
                    paths_failed.append({"path": dst_name, "reason": f"copy: {e}"})

        # student_photos (nếu có)
        if media_dir_path and student_photos_dir and os.path.isdir(student_photos_dir):
            try:
                photos_subdir = os.path.join(media_dir_path, "student_photos")
                os.makedirs(photos_subdir, exist_ok=True)
            except Exception as e:
                paths_failed.append({"path": "student_photos", "reason": f"mkdir: {e}"})
            else:
                for entry in os.listdir(student_photos_dir):
                    if cancel_event is not None and cancel_event.is_set():
                        paths_failed.append({"path": "student_photos", "reason": "shutdown_cancelled"})
                        break
                    src = os.path.join(student_photos_dir, entry)
                    if not os.path.isfile(src):
                        continue
                    dst = os.path.join(photos_subdir, entry)
                    try:
                        _shutil.copy2(src, dst)
                        size = os.path.getsize(dst)
                        with open(dst, "rb") as f:
                            h = _hashlib.sha256()
                            while True:
                                chunk = f.read(65536)
                                if not chunk:
                                    break
                                h.update(chunk)
                        files_meta.append({
                            "path_rel": f"{media_dir_name}/student_photos/{entry}",
                            "size_bytes": size,
                            "sha256": h.hexdigest(),
                            "role": "photo",
                        })
                    except Exception as e:
                        paths_failed.append({"path": entry, "reason": f"copy: {e}"})

    # 3. Verify DB integrity (sau khi backup đã ghi xong)
    db_integrity_ok = False
    db_entry = next((f for f in files_meta if f["role"] == "db"), None)
    if db_entry:
        try:
            db_full = db_path  # biến local; không phụ thuộc dict["path"]
            conn = sqlite3.connect(db_full)
            try:
                cur = conn.cursor()
                cur.execute("PRAGMA integrity_check")
                row = cur.fetchone()
                db_integrity_ok = bool(row and row[0] == "ok")
                if not db_integrity_ok:
                    paths_failed.append({"path": db_entry["path_rel"],
                                         "reason": f"integrity_check={row[0] if row else 'None'}"})
            finally:
                conn.close()
        except Exception as e:
            paths_failed.append({"path": db_entry["path_rel"],
                                 "reason": f"integrity_open: {e}"})

    # 4. Manifest
    manifest = {
        "set_dir": set_dir_name,
        "label": label,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "db_integrity_ok": db_integrity_ok,
        "files": files_meta,
    }
    manifest_path = os.path.join(set_dir, "manifest.json")
    try:
        import json as _json
        with open(manifest_path, "w", encoding="utf-8") as f:
            _json.dump(manifest, f, indent=2)
    except Exception as e:
        paths_failed.append({"path": "manifest.json", "reason": f"write: {e}"})

    # 5. Complete marker (chỉ khi DB integrity_ok + không có fail copy/mà ít)
    complete_marker = os.path.join(set_dir, "complete")
    complete = (
        db_integrity_ok
        and not (cancel_event is not None and cancel_event.is_set())
        and len(paths_failed) == 0
        and len(files_meta) > 0
    )
    if complete:
        try:
            with open(complete_marker, "w", encoding="utf-8") as f:
                f.write(datetime.now(timezone.utc).isoformat())
        except Exception as e:
            paths_failed.append({"path": "complete", "reason": f"write: {e}"})
            complete = False

    return {
        "set_dir": set_dir,
        "db_file": db_name if db_entry else None,
        "media_dir": media_dir_name if include_media else None,
        "manifest_file": "manifest.json",
        "complete": complete,
        "files": files_meta,
        "paths_failed": paths_failed,
        "created_at_utc": manifest["created_at_utc"],
    }


def list_backup_sets(backup_root: str) -> list[dict]:
    """Liệt kê các bộ back đầy đủ (có complete marker) trong `backup_root`.

    Mỗi entry: {set_dir, mtime_iso, db_file, media_dir, manifest_file,
    complete, files_count}.
    """
    import json as _json
    if not os.path.isdir(backup_root):
        return []
    sets = []
    for name in os.listdir(backup_root):
        d = os.path.join(backup_root, name)
        if not os.path.isdir(d):
            continue
        complete_marker = os.path.join(d, "complete")
        if not os.path.isfile(complete_marker):
            continue
        manifest_path = os.path.join(d, "manifest.json")
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                m = _json.load(f)
        except OSError:
            m = {}
        try:
            stat = os.stat(d)
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            mtime = ""
        sets.append({
            "set_dir": name,
            "mtime_iso": mtime,
            "db_file": next((f["path_rel"] for f in m.get("files", [])
                             if f.get("role") == "db"), None),
            "media_dir": "media" if any(
                f.get("role") == "media" for f in m.get("files", [])
            ) else None,
            "manifest_file": "manifest.json",
            "complete": True,
            "files_count": len(m.get("files", [])),
        })
    sets.sort(key=lambda r: r["mtime_iso"], reverse=True)
    return sets


def verify_backup_set(set_dir: str) -> dict:
    """Verify lại 1 bộ backup: mở DB integrity_check, so sha256 media files.

    Returns:
        dict {
          'complete_marker_present': bool,
          'db_integrity_ok': bool,
          'db_sha256_match': bool,
          'media_total': int,
          'media_missing': list[str],
          'media_sha256_mismatch': list[str],
          'verified': bool — True nếu TẤT CẢ pass,
        }
    """
    import json as _json
    import hashlib as _hashlib
    result = {
        "complete_marker_present": False,
        "db_integrity_ok": False,
        "db_sha256_match": False,
        "media_total": 0,
        "media_missing": [],
        "media_sha256_mismatch": [],
        "verified": False,
    }
    if not os.path.isdir(set_dir):
        return result
    result["complete_marker_present"] = os.path.isfile(os.path.join(set_dir, "complete"))
    manifest_path = os.path.join(set_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return result
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = _json.load(f)
    except OSError:
        return result
    files = manifest.get("files", [])
    # Verify DB
    db_entry = next((f for f in files if f.get("role") == "db"), None)
    if db_entry:
        db_full = os.path.join(set_dir, db_entry["path_rel"])
        if os.path.isfile(db_full):
            try:
                conn = sqlite3.connect(db_full)
                try:
                    cur = conn.cursor()
                    cur.execute("PRAGMA integrity_check")
                    row = cur.fetchone()
                    result["db_integrity_ok"] = bool(row and row[0] == "ok")
                finally:
                    conn.close()
            except Exception:
                result["db_integrity_ok"] = False
            try:
                h = _hashlib.sha256()
                with open(db_full, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        h.update(chunk)
                result["db_sha256_match"] = h.hexdigest() == db_entry.get("sha256")
            except OSError:
                result["db_sha256_match"] = False
    # Verify media (best-effort)
    for entry in files:
        if entry.get("role") not in ("media", "photo"):
            continue
        result["media_total"] += 1
        full = os.path.join(set_dir, entry["path_rel"])
        if not os.path.isfile(full):
            result["media_missing"].append(entry["path_rel"])
            continue
        try:
            h = _hashlib.sha256()
            with open(full, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            if h.hexdigest() != entry.get("sha256"):
                result["media_sha256_mismatch"].append(entry["path_rel"])
        except OSError:
            result["media_sha256_mismatch"].append(entry["path_rel"])

    result["verified"] = (
        result["complete_marker_present"]
        and result["db_integrity_ok"]
        and result["db_sha256_match"]
        and not result["media_missing"]
        and not result["media_sha256_mismatch"]
    )
    return result


def restore_backup_set(set_dir: str, restore_root: str) -> dict:
    """Restore 1 bộ backup sang thư mục MỚI — KHÔNG ghi đè vận hành.

    Args:
        set_dir: đường dẫn tới subdir bộ backup.
        restore_root: thư mục mới để chứa DB + media sau restore.

    Returns:
        dict {
          'db_restored': bool,
          'db_ok': bool (verify integrity_check post-restore),
          'media_restored_count': int,
          'media_missing': list[str],
          'restore_root': str,
        }
    """
    import json as _json
    import shutil as _shutil
    out = {
        "db_restored": False,
        "db_ok": False,
        "media_restored_count": 0,
        "media_missing": [],
        "restore_root": restore_root,
    }
    if not os.path.isdir(set_dir):
        return out
    manifest_path = os.path.join(set_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return out
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = _json.load(f)
    except OSError:
        return out
    os.makedirs(restore_root, exist_ok=True)
    for entry in manifest.get("files", []):
        rel = entry.get("path_rel", "")
        if not rel:
            continue
        src = os.path.join(set_dir, rel)
        if not os.path.isfile(src):
            out["media_missing"].append(rel)
            continue
        dst = os.path.join(restore_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            _shutil.copy2(src, dst)
        except OSError:
            out["media_missing"].append(rel)
            continue
        if entry.get("role") == "db":
            out["db_restored"] = True
            # Verify post-restore
            try:
                conn = sqlite3.connect(dst)
                try:
                    cur = conn.cursor()
                    cur.execute("PRAGMA integrity_check")
                    row = cur.fetchone()
                    out["db_ok"] = bool(row and row[0] == "ok")
                finally:
                    conn.close()
            except Exception:
                out["db_ok"] = False
        else:
            out["media_restored_count"] += 1
    return out


def prune_backup_sets(backup_root: str, keep_count: int) -> list[str]:
    """Dọn các bộ backup cũ (giữ `keep_count` bộ mới nhất theo mtime).

    Dọn TOÀN BỘ subdir bộ (DB + media + manifest + complete marker) —
    KHÔNG xóa file DB lẻ theo BACKUP_KEEP_COUNT cũ.

    Returns:
        list tên các bộ đã xóa.
    """
    import shutil as _shutil
    sets = list_backup_sets(backup_root)
    deleted: list[str] = []
    for s in sets[keep_count:]:
        try:
            full = os.path.join(backup_root, s["set_dir"])
            _shutil.rmtree(full, ignore_errors=True)
            deleted.append(s["set_dir"])
        except OSError:
            continue
    return deleted


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


def get_violations_by_vehicle(vehicle_id: int, limit: int = 100, offset: int = 0) -> dict:
    """
    Toàn bộ lịch sử vi phạm của 1 xe/học sinh, sắp theo timestamp DESC.
    Feature 6 — dùng cho trang timeline.
    T2.3 — thêm `offset` cho server pagination; trả `{items, total, limit, offset}`.

    Backward-compat: callers cũ gọi `get_violations_by_vehicle(vid)` vẫn hoạt
    động — nhận cùng shape dict (cũ là list, mới là dict có key 'items'). Caller
    nào expect list → migrate sang `response['items']`.
    """
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Subquery lấy plate_number của vehicle
        cursor.execute(
            "SELECT plate_number FROM registered_vehicles WHERE id = ?",
            (vehicle_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return {"items": [], "total": 0, "limit": safe_limit, "offset": safe_offset}
        plate = row["plate_number"]

        # Total
        cursor.execute(
            "SELECT COUNT(*) FROM violation_events WHERE plate_matched = ?",
            (plate,),
        )
        total = cursor.fetchone()[0]

        # Page — stable sort: timestamp DESC, id DESC (id tie-break tránh nhảy trang)
        cursor.execute('''
            SELECT ve.*, rv.student_name, rv.student_class
            FROM violation_events ve
            LEFT JOIN registered_vehicles rv ON rv.plate_number = ve.plate_matched
            WHERE ve.plate_matched = ?
            ORDER BY ve.timestamp DESC, ve.id DESC
            LIMIT ? OFFSET ?
        ''', (plate, safe_limit, safe_offset))
        items = [dict(r) for r in cursor.fetchall()]
        return {
            "items": items,
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
        }
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


def clear_violation_snapshot_paths(older_than_days: int = 90, dry_run: bool = False) -> dict:
    """
    Xóa file snapshot + clip cũ hơn `older_than_days` ngày; set các cột path
    trong DB = NULL. Giữ nguyên record vi phạm.

    T2.7 — an toàn hơn:
    - Validate path thực nằm trong SNAPSHOTS_DIR root (resolve + is_relative_to).
    - Không theo symlink ra ngoài root.
    - PermissionError/OSError KHÔNG clear DB reference của record đó; record
      vẫn giữ path để retry lần sau.
    - Tôn trọng `evidence_state='hold'` (që inspection): KHÔNG xóa record này.
    - Không xóa crop_snapshot_path nếu full-frame snapshot_path vẫn còn file
      (chưa xóa được) — partial failure chỉ null đường dẫn đã xóa thành công.
    - Trả về dict {attempted, deleted, missing, failed, paths_failed: [...]}
      thay vì int để admin xem log chính xác.

    Args:
        older_than_days: tuổi tối thiểu (mặc định 90).
        dry_run: nếu True, chỉ liệt kê file sẽ xoá, không đụng DB/disk.

    Returns:
        dict kết quả; nếu có lỗi, paths_failed liệt kê path + reason.
    """
    from pathlib import Path as _Path
    snap_root = _Path(SNAPSHOTS_DIR).resolve()
    result = {
        "attempted": 0,
        "deleted": 0,
        "missing": 0,
        "failed": 0,
        "held": 0,
        "paths_failed": [],
    }
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cutoff = f"-{older_than_days} days"

            # Lấy các record có path cũ + KHÔNG có hold (giữ phục vụ kiểm tra)
            cursor.execute(
                "SELECT id, snapshot_path, clip_path, crop_snapshot_path, evidence_state "
                "FROM violation_events "
                "WHERE (snapshot_path IS NOT NULL OR clip_path IS NOT NULL OR crop_snapshot_path IS NOT NULL) "
                "AND timestamp < datetime('now', ?)",
                (cutoff,),
            )
            rows = cursor.fetchall()

            # Gom tất cả path để xử lý transaction ngắn hơn
            delete_targets = []  # list of (record_id, column, path, full_path)
            for row in rows:
                rec_id = row["id"]
                evidence_state = row["evidence_state"] or "persisted"
                # record hold phục vụ kiểm tra → bỏ qua
                if evidence_state == "hold":
                    result["held"] += 1
                    continue
                for col in ("snapshot_path", "clip_path", "crop_snapshot_path"):
                    rel = row[col]
                    if not rel:
                        continue
                    # Path: có thể là absolute hoặc relative. Nếu absolute → check
                    # trong root; nếu relative → join với SNAPSHOTS_DIR basename.
                    if os.path.isabs(rel):
                        candidate = _Path(rel)
                    else:
                        candidate = snap_root / os.path.basename(rel)
                    try:
                        resolved = candidate.resolve(strict=True)
                    except (OSError, RuntimeError):
                        # File không tồn tại hoặc resolve lỗi → coi như missing
                        # (sẽ null path trong DB để tránh retry mãi)
                        delete_targets.append((rec_id, col, rel, None, "missing"))
                        continue
                    # Validate trong root
                    try:
                        resolved.relative_to(snap_root)
                    except ValueError:
                        # Path ngoài root → KHÔNG xóa, KHÔNG null, ghi nhận lỗi
                        result["paths_failed"].append({"path": rel, "reason": "outside_root"})
                        result["failed"] += 1
                        continue
                    delete_targets.append((rec_id, col, rel, str(resolved), "ok"))

            # Unlink file thực tế — KHÔNG nuốt exception; ghi lỗi chi tiết
            for rec_id, col, rel, full_path, status_marker in delete_targets:
                result["attempted"] += 1
                if status_marker == "missing":
                    # File đã không tồn tại; null trong DB, đếm missing
                    # dry_run=True vẫn đếm missing để biết có bao nhiêu file
                    # sẽ bị cleanup nếu chạy thật — KHÔNG update DB.
                    if not dry_run:
                        cursor.execute(
                            f"UPDATE violation_events SET {col} = NULL WHERE id = ?",
                            (rec_id,),
                        )
                    result["missing"] += 1
                    continue
                if full_path is None:
                    continue
                # dry_run=True: KHÔNG xóa file, KHÔNG update DB, vẫn đếm
                # 'attempted' để admin thấy file sẽ bị xóa nếu chạy thật.
                if dry_run:
                    continue
                try:
                    os.unlink(full_path)
                    # Xóa thành công → null path trong DB
                    cursor.execute(
                        f"UPDATE violation_events SET {col} = NULL WHERE id = ?",
                        (rec_id,),
                    )
                    result["deleted"] += 1
                except PermissionError as e:
                    # File đang được giữ bởi process khác (vd. backup đang copy)
                    # → giữ path trong DB để lần sau retry
                    result["paths_failed"].append({
                        "path": rel, "reason": f"permission_denied: {e}"
                    })
                    result["failed"] += 1
                except FileNotFoundError:
                    # File biến mất giữa resolve và unlink → missing
                    cursor.execute(
                        f"UPDATE violation_events SET {col} = NULL WHERE id = ?",
                        (rec_id,),
                    )
                    result["missing"] += 1
                except OSError as e:
                    # Lỗi khác (vd. đĩa đầy, disk error) → giữ path, ghi lỗi
                    result["paths_failed"].append({
                        "path": rel, "reason": f"os_error: {e}"
                    })
                    result["failed"] += 1

            if not dry_run:
                conn.commit()
            else:
                conn.rollback()
            return result
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


# ─── Gate line (đường cắt) cho RIDING_THROUGH_GATE — Đợt 4, D4.1 ──────────

def get_gate_line(gate_id: str) -> list | None:
    """Trả về [x1,y1,x2,y2] đã lưu cho gate, None nếu chưa cấu hình.

    Trả None khi chưa cấu hình → RIDING_THROUGH_GATE dùng pose fallback cũ,
    không tự động kết luận lỗi khi chưa có đường cắt (theo kế hoạch).
    """
    import json
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT gate_line_json FROM gate_roi WHERE gate_id = ?", (gate_id,))
        row = cursor.fetchone()
        if not row or not row["gate_line_json"]:
            return None
        return json.loads(row["gate_line_json"])
    finally:
        conn.close()


def set_gate_line(gate_id: str, line: list | None) -> None:
    """Lưu đường cắt cho gate. `line=None` nghĩa là tắt (dùng pose fallback).

    `line` phải là [x1, y1, x2, y2] với tọa độ chuẩn hóa [0,1].
    Hai điểm phải khác nhau. Dùng chung bảng gate_roi với ROI.
    """
    import json
    if line is not None:
        if len(line) != 4:
            raise ValueError("gate_line phải có 4 giá trị: [x1,y1,x2,y2]")
        x1, y1, x2, y2 = line
        if not all(0 <= v <= 1 for v in line):
            raise ValueError("gate_line tọa độ phải trong [0,1]")
        if x1 == x2 and y1 == y2:
            raise ValueError("gate_line hai điểm phải khác nhau")

    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Upsert: tạo row nếu chưa có (gate_roi row từ ROI có thể chưa tồn tại)
            cursor.execute(
                '''INSERT INTO gate_roi (gate_id, points_json, gate_line_json, updated_at)
                   VALUES (?, '{}', ?, datetime('now'))
                   ON CONFLICT(gate_id) DO UPDATE SET
                       gate_line_json = excluded.gate_line_json,
                       updated_at = excluded.updated_at''',
                (gate_id, json.dumps(line)),
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


# ─── Đợt 1 (System Stability): gate_cameras (multi-camera per gate) ─────
# Pipeline chọn camera theo role (front/rear/aux) thay vì dùng 1 source cố
# định. Mỗi camera có camera_id ổn định, gate_id chỉ cổng vật lý, role quy
# định camera dùng cho mục đích nào. Bảng gate_camera_source (cũ) vẫn
# dùng cho override admin nhanh — gate_cameras là cấu hình chuẩn.

_VALID_CAMERA_ROLES = ("front", "rear", "aux")


def _normalize_camera_role(role: str) -> str:
    """Validate role; raise ValueError nếu không thuộc tập cho phép."""
    if role not in _VALID_CAMERA_ROLES:
        raise ValueError(
            f"role phải là một trong {_VALID_CAMERA_ROLES!r}, nhận được {role!r}"
        )
    return role


def upsert_camera(camera_id: str, gate_id: str, role: str,
                  source: str, enabled: int = 1) -> bool:
    """Tạo mới hoặc cập nhật mapping camera ↔ gate + role + source.

    Returns True nếu tạo mới, False nếu cập nhật (đã tồn tại).
    Idempotent cho cùng camera_id — gọi lần 2 chỉ UPDATE, không INSERT.
    """
    _normalize_camera_role(role)
    enabled_int = 1 if enabled else 0
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Check tồn tại trước để trả created/updated
            existing = cursor.execute(
                'SELECT 1 FROM gate_cameras WHERE camera_id = ?',
                (camera_id,),
            ).fetchone()
            cursor.execute(
                '''INSERT INTO gate_cameras
                       (camera_id, gate_id, role, source, enabled, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                   ON CONFLICT(camera_id) DO UPDATE SET
                       gate_id    = excluded.gate_id,
                       role       = excluded.role,
                       source     = excluded.source,
                       enabled    = excluded.enabled,
                       updated_at = excluded.updated_at''',
                (camera_id, gate_id, role, source, enabled_int),
            )
            conn.commit()
            return existing is None
        finally:
            conn.close()


def get_camera(camera_id: str) -> dict | None:
    """Lấy thông tin 1 camera theo camera_id. Trả dict hoặc None."""
    conn = get_connection()
    try:
        row = conn.execute(
            '''SELECT camera_id, gate_id, role, source, enabled, created_at, updated_at
               FROM gate_cameras WHERE camera_id = ?''',
            (camera_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "camera_id": row[0],
            "gate_id": row[1],
            "role": row[2],
            "source": row[3],
            "enabled": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }
    finally:
        conn.close()


def list_cameras_for_gate(gate_id: str, only_enabled: bool = True) -> list[dict]:
    """Liệt kê camera thuộc 1 gate, sắp theo role front→rear→aux.

    only_enabled=True (mặc định) chỉ trả camera enabled=1. Set False để lấy
    tất cả (kể cả đang tạm tắt).
    """
    sql = '''SELECT camera_id, gate_id, role, source, enabled, created_at, updated_at
             FROM gate_cameras WHERE gate_id = ?'''
    if only_enabled:
        sql += ' AND enabled = 1'
    # Sắp theo role theo thứ tự front→rear→aux dùng CASE
    sql += ''' ORDER BY CASE role
                    WHEN 'front' THEN 0
                    WHEN 'rear'  THEN 1
                    WHEN 'aux'   THEN 2
                    ELSE 3 END,
                    camera_id'''
    conn = get_connection()
    try:
        rows = conn.execute(sql, (gate_id,)).fetchall()
        return [
            {
                "camera_id": r[0],
                "gate_id": r[1],
                "role": r[2],
                "source": r[3],
                "enabled": r[4],
                "created_at": r[5],
                "updated_at": r[6],
            }
            for r in rows
        ]
    finally:
        conn.close()


def delete_camera(camera_id: str) -> bool:
    """Xóa camera theo camera_id. Trả True nếu xóa được, False nếu không tồn tại."""
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM gate_cameras WHERE camera_id = ?', (camera_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


# ─── Đợt 1 (System Stability): encounter_observations ─────────────────────
# Ghi nhận nhiều camera quan sát cùng 1 lượt xe (encounter). Mỗi row là 1
# observation từ 1 camera tại 1 thời điểm. Unique theo (encounter_id,
# camera_id, source_epoch) → idempotent: insert lần 2 với cùng khóa sẽ
# cập nhật các trường nullable (helmet_status, posture_status, plate_read,
# observed_at...). Dùng để ghép dữ liệu front+rear (Imou trước + Imou
# sau) trong 1 encounter.


def add_encounter_observation(
    encounter_id: str,
    camera_id: str,
    gate_id: str,
    observed_at: str,
    source_epoch: int,
    plate_read: str | None = None,
    plate_confidence: float | None = None,
    helmet_status: str | None = None,
    posture_status: str | None = None,
    extra_json: str | None = None,
) -> int:
    """Thêm (hoặc cập nhật) 1 observation cho encounter.

    Returns: id của row (mới hoặc đã tồn tại).
    Idempotent: gọi 2 lần với cùng (encounter_id, camera_id, source_epoch)
    → vẫn 1 row, các trường nullable được cập nhật bằng giá trị mới.
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # ON CONFLICT chỉ update nếu giá trị mới không NULL (không ghi đè
            # dữ liệu đã có bằng None — tránh mất thông tin khi 1 camera quan
            # sát trước, 1 camera quan sát sau cùng encounter).
            cursor.execute(
                '''INSERT INTO encounter_observations
                       (encounter_id, camera_id, gate_id, observed_at, source_epoch,
                        plate_read, plate_confidence, helmet_status, posture_status,
                        extra_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(encounter_id, camera_id, source_epoch) DO UPDATE SET
                       gate_id          = excluded.gate_id,
                       observed_at      = excluded.observed_at,
                       plate_read       = COALESCE(excluded.plate_read,       encounter_observations.plate_read),
                       plate_confidence = COALESCE(excluded.plate_confidence, encounter_observations.plate_confidence),
                       helmet_status    = COALESCE(excluded.helmet_status,    encounter_observations.helmet_status),
                       posture_status   = COALESCE(excluded.posture_status,   encounter_observations.posture_status),
                       extra_json       = COALESCE(excluded.extra_json,       encounter_observations.extra_json)''',
                (encounter_id, camera_id, gate_id, observed_at, source_epoch,
                 plate_read, plate_confidence, helmet_status, posture_status, extra_json),
            )
            conn.commit()
            row = cursor.execute(
                '''SELECT id FROM encounter_observations
                   WHERE encounter_id = ? AND camera_id = ? AND source_epoch = ?''',
                (encounter_id, camera_id, source_epoch),
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()


def list_observations_for_encounter(encounter_id: str) -> list[dict]:
    """Liệt kê tất cả observation cho 1 encounter, sắp theo observed_at tăng dần."""
    conn = get_connection()
    try:
        rows = conn.execute(
            '''SELECT id, encounter_id, camera_id, gate_id, observed_at, source_epoch,
                       plate_read, plate_confidence, helmet_status, posture_status,
                       extra_json, created_at
               FROM encounter_observations
               WHERE encounter_id = ?
               ORDER BY observed_at ASC, id ASC''',
            (encounter_id,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "encounter_id": r[1],
                "camera_id": r[2],
                "gate_id": r[3],
                "observed_at": r[4],
                "source_epoch": r[5],
                "plate_read": r[6],
                "plate_confidence": r[7],
                "helmet_status": r[8],
                "posture_status": r[9],
                "extra_json": r[10],
                "created_at": r[11],
            }
            for r in rows
        ]
    finally:
        conn.close()



# ─── UT8: student_roster — danh sách mã số hợp lệ cho public register ───

def add_roster_entry(student_id: str, student_name: str, student_class: str) -> int:
    """UT8: thêm 1 mã số vào danh sách hợp lệ (admin import tay từng dòng)."""
    sid = (student_id or "").strip()
    if not sid:
        raise ValueError("student_id không được rỗng")
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO student_roster (student_id, student_name, student_class) VALUES (?, ?, ?)',
                (sid, student_name, student_class),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"Mã số {sid} đã tồn tại trong danh sách")
        finally:
            conn.close()


def bulk_add_roster(rows: list[dict]) -> dict:
    """UT8: import nhiều dòng cùng lúc. Trả về {created, skipped, errors}."""
    created = skipped = 0
    errors: list[dict] = []
    for row in rows:
        try:
            add_roster_entry(row["student_id"], row["student_name"], row["student_class"])
            created += 1
        except ValueError as e:
            errors.append({"student_id": row.get("student_id"), "message": str(e)})
            skipped += 1
    return {"created": created, "skipped": skipped, "errors": errors}


def list_roster() -> list[dict]:
    """UT8: liệt kê toàn bộ roster (admin xem)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, student_name, student_class, created_at FROM student_roster ORDER BY created_at DESC")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_roster_entry(student_id: str) -> dict | None:
    """UT8: tra cứu 1 mã số — dùng cho public register kiểm tra hợp lệ."""
    sid = (student_id or "").strip()
    if not sid:
        return None
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, student_name, student_class FROM student_roster WHERE student_id = ?", (sid,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_roster_entry(student_id: str) -> bool:
    """UT8: xóa 1 mã số khỏi roster."""
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM student_roster WHERE student_id = ?", (student_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def get_vehicle_by_student_id(student_id: str) -> dict | None:
    """UT8: tra cứu xe đã đăng ký theo student_id (dùng cho trang /register
    biết học sinh đã đăng ký xe chưa)."""
    sid = (student_id or "").strip()
    if not sid:
        return None
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registered_vehicles WHERE student_id = ?", (sid,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()



def update_violation_media(event_id: int, clip_path: str) -> None:
    with _write_lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE violation_events SET clip_path = ? WHERE id = ?", (clip_path, event_id))
            conn.commit()
        finally:
            conn.close()


# ─── FR6: Recognition reviews (plate candidate feedback) ───────────────
# Plate recognition cần người duyệt đúng/sai — không tự gán xe/học sinh khi
# chưa có xác nhận. Schema tách biệt khỏi violation_events để chuỗi bằng
# chứng (snapshot/clip/OCR raw) không bị ghi đè khi người dùng sửa nhãn.

VERDICT_CORRECT = "correct"
VERDICT_INCORRECT = "incorrect"
VERDICT_UNREADABLE = "unreadable"
VERDICT_NOT_PLATE = "not_plate"
VERDICT_WRONG_ASSOCIATION = "wrong_association"
ALLOWED_VERDICTS = {
    VERDICT_CORRECT, VERDICT_INCORRECT, VERDICT_UNREADABLE,
    VERDICT_NOT_PLATE, VERDICT_WRONG_ASSOCIATION,
}


def create_recognition_review(
    *,
    review_id: str,
    violation_id: int | None,
    encounter_id: str | None,
    gate_id: str,
    camera_id: str | None,
    run_id: str | None,
    source_epoch: int,
    frame_seq: int | None,
    observed_at: str,
    crop_media_id: str | None,
    crop_sha256: str | None,
    proposal_raw: str,
    proposal_canonical: str,
    proposal_top_line: str | None = None,
    proposal_bottom_line: str | None = None,
    proposal_confidence: float | None = None,
    proposal_engine: str,
    proposal_model_hash: str | None = None,
    proposal_config_version: str | None = None,
    quality_score: float | None = None,
    blur_score: float | None = None,
    contrast_score: float | None = None,
) -> int:
    """Tạo review mới. Idempotent theo review_id (UNIQUE). Trả id row.

    Nếu review_id đã tồn tại: trả id cũ, không ghi đè (đã có feedback sẽ
    không bị xoá nếu proposal thay đổi). Caller phải tạo review_id mới khi
    proposal thực sự thay đổi (vd. crop mới từ cùng track).
    """
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT OR IGNORE INTO recognition_reviews
                   (review_id, violation_id, encounter_id, gate_id, camera_id,
                    run_id, source_epoch, frame_seq, observed_at, crop_media_id,
                    crop_sha256, proposal_raw, proposal_canonical,
                    proposal_top_line, proposal_bottom_line, proposal_confidence,
                    proposal_engine, proposal_model_hash, proposal_config_version,
                    quality_score, blur_score, contrast_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (review_id, violation_id, encounter_id, gate_id, camera_id,
                 run_id, int(source_epoch), frame_seq, observed_at, crop_media_id,
                 crop_sha256, proposal_raw, proposal_canonical,
                 proposal_top_line, proposal_bottom_line, proposal_confidence,
                 proposal_engine, proposal_model_hash, proposal_config_version,
                 quality_score, blur_score, contrast_score),
            )
            if cursor.lastrowid:
                conn.commit()
                return cursor.lastrowid
            # Already exists — return its id (no overwrite).
            cursor.execute(
                'SELECT id FROM recognition_reviews WHERE review_id = ?', (review_id,)
            )
            row = cursor.fetchone()
            return row['id'] if row else -1
        finally:
            conn.close()


def list_recognition_reviews(
    *,
    gate_id: str | None = None,
    camera_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Liệt kê review có phân trang. limit 1–100, offset ≥0, tổng đúng.

    status ∈ {'pending', 'confirmed', 'rejected'} — lọc nhanh để UI render.
    """
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    conn = get_connection()
    try:
        cursor = conn.cursor()
        conditions = ['1=1']
        params: list = []
        if gate_id:
            conditions.append('gate_id = ?')
            params.append(gate_id)
        if camera_id:
            conditions.append('camera_id = ?')
            params.append(camera_id)
        if status:
            conditions.append('status = ?')
            params.append(status)
        where = ' AND '.join(conditions)
        cursor.execute(
            f'SELECT COUNT(*) FROM recognition_reviews WHERE {where}', params
        )
        total = cursor.fetchone()[0]
        cursor.execute(
            f'''SELECT review_id, violation_id, encounter_id, gate_id, camera_id,
                       run_id, source_epoch, frame_seq, observed_at, crop_media_id,
                       crop_sha256, proposal_raw, proposal_canonical,
                       proposal_top_line, proposal_bottom_line, proposal_confidence,
                       proposal_engine, proposal_model_hash, proposal_config_version,
                       quality_score, blur_score, contrast_score, version, status, created_at
                FROM recognition_reviews WHERE {where}
                ORDER BY observed_at DESC, review_id DESC
                LIMIT ? OFFSET ?''',
            params + [limit, offset],
        )
        items = [dict(r) for r in cursor.fetchall()]
        return {'total': total, 'limit': limit, 'offset': offset, 'items': items}
    finally:
        conn.close()


def get_recognition_review(review_id: str) -> dict | None:
    """Lấy 1 review + danh sách feedback hiện có. KHÔNG trả về nếu không tồn tại."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT review_id, violation_id, encounter_id, gate_id, camera_id,
                      run_id, source_epoch, frame_seq, observed_at, crop_media_id,
                      crop_sha256, proposal_raw, proposal_canonical,
                      proposal_top_line, proposal_bottom_line, proposal_confidence,
                      proposal_engine, proposal_model_hash, proposal_config_version,
                      quality_score, blur_score, contrast_score, version, status, created_at
               FROM recognition_reviews WHERE review_id = ?''', (review_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        review = dict(row)
        cursor.execute(
            '''SELECT id, reviewer_username, reviewer_role, verdict,
                      corrected_text, expected_version, note, idempotency_key, created_at
               FROM recognition_review_feedback WHERE review_id = ?
               ORDER BY id ASC''', (review_id,)
        )
        review['feedback'] = [dict(r) for r in cursor.fetchall()]
        return review
    finally:
        conn.close()


def record_review_feedback(
    *,
    review_id: str,
    reviewer_username: str,
    reviewer_role: str,
    verdict: str,
    expected_version: int,
    corrected_text: str | None = None,
    note: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Ghi feedback mới + cập nhật status. Trả dict có:
      - applied: bool
      - conflict: bool (409)
      - feedback_id: int (server-generated, identity for hook/event)
      - new_version: int (version actually committed in DB, server-authoritative)
      - status: str (review status after operation)
      - idempotent_replay: bool (True nếu idempotency_key đã thấy cùng payload)

    Quy tắc:
    - Cùng `idempotency_key` + cùng payload → trả về feedback cũ (idempotent retry).
    - Cùng `idempotency_key` + khác payload → ValueError (lạm dụng key).
    - `expected_version` < version hiện tại → 'conflict' (HTTP 409).
    - verdict không hợp lệ → ValueError.

    VỀ VERSION (quan trọng cho hook downstream):
    - new_version: version DB MÀ REVIEW ĐÃ ĐƯỢC CẬP NHẬT THÀNH (server-authoritative).
      VÍ DỤ: review version=5; POST feedback expected_version=5 thành công →
      new_version=6 (DB đã tăng lên 6).
    - KHÔNG dùng `expected_version` (echo input) làm version — client có thể gửi sai.
    - Hook enqueue dùng (review_id, feedback_id) làm identity, lấy version thật
      qua adapter/DB thay vì từ echo client.
    """
    if verdict not in ALLOWED_VERDICTS:
        raise ValueError(f"verdict không hợp lệ: {verdict!r}")
    with _write_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, status, version FROM recognition_reviews WHERE review_id = ?",
                (review_id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"review_id không tồn tại: {review_id!r}")
            current_version = int(row['version'])
            # Idempotency check
            if idempotency_key:
                cursor.execute(
                    '''SELECT id, verdict, corrected_text, note, expected_version
                       FROM recognition_review_feedback
                       WHERE idempotency_key = ? ORDER BY id DESC LIMIT 1''',
                    (idempotency_key,)
                )
                prev = cursor.fetchone()
                if prev is not None:
                    same = (prev['verdict'] == verdict
                            and (prev['corrected_text'] or '') == (corrected_text or '')
                            and (prev['note'] or '') == (note or '')
                            and prev['expected_version'] == expected_version)
                    if not same:
                        raise ValueError(
                            f"idempotency_key đã dùng với payload khác: {idempotency_key!r}"
                        )
                    return {
                        'applied': True,
                        'idempotent_replay': True,
                        'feedback_id': prev['id'],
                        'status': row['status'],
                        'new_version': current_version,
                    }
            # Conflict check — nếu expected_version thấp hơn version hiện tại
            # (đã có feedback mới hơn), trả 'conflict' mà không ghi.
            if expected_version < current_version:
                return {
                    'applied': False,
                    'conflict': True,
                    'feedback_id': None,
                    'status': row['status'],
                    'new_version': current_version,
                }
            # Insert feedback row.
            cursor.execute(
                '''INSERT INTO recognition_review_feedback
                   (review_id, reviewer_username, reviewer_role, verdict,
                    corrected_text, expected_version, note, idempotency_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (review_id, reviewer_username, reviewer_role, verdict,
                 corrected_text, expected_version, note, idempotency_key)
            )
            feedback_id = cursor.lastrowid
            # Update review status — 'confirmed' nếu verdict=correct, ngược lại 'rejected'.
            new_status = 'confirmed' if verdict == VERDICT_CORRECT else 'rejected'
            new_version = current_version + 1
            cursor.execute(
                "UPDATE recognition_reviews SET status = ?, version = ? WHERE review_id = ?",
                (new_status, new_version, review_id)
            )
            conn.commit()
            return {
                'applied': True,
                'idempotent_replay': False,
                'conflict': False,
                'feedback_id': feedback_id,
                'status': new_status,
                'new_version': new_version,  # actual version DB committed to
            }
        finally:
            conn.close()
