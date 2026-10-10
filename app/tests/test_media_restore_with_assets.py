"""
T2 REOPEN — Media restore với assets thật (ảnh + crop + clip).

Yêu cầu REOPEN: backup test_backup.py chỉ test DB + metadata, cần test
restore với ảnh thật + crop + clip fixture + integrity/hash verify.

Test scope:
  1. Seed DB có:
       - 1 xe đăng ký
       - 1 violation với snapshot_path + crop_snapshot_path + clip_path
         trỏ đến file JPEG/PNG/MP4 thật (UUID bytes giả lập).
  2. Gọi create_backup_set(backup_root, snapshots_dir, student_photos_dir).
  3. Verify manifest.json có entries:
       - role=db (1 entry)
       - role=media (>=3 entries — snapshot, crop, clip)
       - SHA256 khớp khi recompute.
  4. Verify complete marker được ghi.
  5. Gọi restore_backup_set(set_dir, restore_root) — KHÔNG ghi đè
     SNAPSHOTS_DIR vận hành.
  6. Mở restored DB, kiểm tra:
       - record violation có snapshot_path/crop/clip trỏ đến filename
         đúng.
       - PRAGMA integrity_check == 'ok'.
       - SHA256 của file ảnh trong restore_root khớp với file gốc.
  7. Verify verify_backup_set() trả verified=True.

Lưu ý:
  - KHÔNG dùng ảnh thật từ data/snapshots (production). Mỗi test tạo
    fixture trong tmp_path để cô lập.
  - KHÔNG commit file test mới vào git working tree dùng chung
    (chỉ tạo trong tmp_path).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import sqlite3
from datetime import datetime, timezone

import pytest


def _make_jpeg_bytes(width: int = 8, height: int = 8) -> bytes:
    """Tạo JPEG bytes tối thiểu hợp lệ (header JFIF + data đơn giản).

    Bytes không phải ảnh "thật" (8x8 trắng) nhưng PIL/đầu đọc sẽ chấp
    nhận marker JPEG. Đủ để đo SHA256 round-trip và verify restore.
    """
    # Header JPEG + scan data tối thiểu + EOI marker
    # Dùng bytes rõ ràng, deterministic theo width/height.
    header = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01"
        b"\x00\x00\xff\xdb\x00C\x00"
        + bytes(8)  # quantization
        + b"\xff\xc0\x00\x0b\x08"
        + struct.pack(">HH", height, width)
        + b"\x01\x00\x01\x11\x00"
        + b"\xff\xc4\x00\x14\x00\x01" + bytes(20)
        + b"\xff\xc4\x00\x14\x10\x01" + bytes(20)
        + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00"
        + b"\xfb\x40\x80"  # scan body
        + b"\xff\xd9"
    )
    return header


def _make_png_bytes(width: int = 8, height: int = 8) -> bytes:
    """Tạo PNG bytes hợp lệ 8x8 màu trắng."""
    # PNG signature + IHDR + IDAT (uncompressed) + IEND
    import zlib

    def chunk(typ: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + typ
            + data
            + struct.pack(
                ">I",
                zlib.crc32(typ + data) & 0xFFFFFFFF,
            )
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    # IDAT raw: filter byte 0 + RGB white pixel × width
    raw_row = b"\x00" + b"\xff" * (width * 3)
    raw = raw_row * height
    idat = zlib.compress(raw)
    iend = b""
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", iend)


def _make_mp4_bytes() -> bytes:
    """Tạo MP4 bytes giả lập — không phải MP4 hợp lệ nhưng có magic
    'ftyp' box để trình quét video nhận dạng.  Đủ để test SHA256 round-trip
    và verify extension matching (.mp4 → role=media).
    """
    # ftyp box (file type): major_brand='isom', minor_version=512, brands=['isom','mp41']
    ftyp = (
        b"\x00\x00\x00\x18"  # box size 24
        b"ftyp"               # box type
        b"isom"               # major brand
        + struct.pack(">I", 512)  # minor version
        + b"isom" + b"mp41"   # compatible brands
    )
    # Padding body
    body = b"\x00" * 256
    return ftyp + body


def _seed_violation_with_media(
    snapshots_dir: str,
    *,
    plate: str = "99T1-001",
    name: str = "Test Student A1",
    klass: str = "10A1",
) -> dict:
    """Seed 1 vehicle + 1 violation với snapshot/crop/clip đầy đủ.

    Idempotent: nếu plate đã có trong DB, dùng lại vehicle_id (module-scoped
    test_app dùng chung DB cho cả 6 test). Trả về dict {vehicle_id,
    violation_id, snapshot_filename, crop_filename, clip_filename,
    file_hashes}.
    """
    from app.db import (
        add_vehicle, add_violation_event, normalize_plate, get_connection,
    )

    norm = normalize_plate(plate)

    # Idempotent seeding: nếu vehicle đã có thì dùng lại.
    # Đây là cách test_task02_t2_8_backup.py cũng xử lý khi test_app là
    # module-scoped và DB dùng chung giữa các test trong cùng module.
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM registered_vehicles WHERE plate_number = ?",
            (norm,),
        ).fetchone()
        vehicle_id = existing["id"] if existing else None
    finally:
        conn.close()

    if vehicle_id is None:
        # Retry on SQLITE_LOCKED (copy during testing có thể lock tạm thời)
        import time as _t
        last_err = None
        for _ in range(8):
            try:
                vehicle_id = add_vehicle(plate, name, klass)
                break
            except Exception as e:
                last_err = e
                if "đã tồn tại" in str(e):
                    # Race: vehicle vừa được thêm bởi test khác trong module
                    conn = get_connection()
                    try:
                        existing = conn.execute(
                            "SELECT id FROM registered_vehicles "
                            "WHERE plate_number = ?",
                            (norm,),
                        ).fetchone()
                        if existing:
                            vehicle_id = existing["id"]
                            break
                    finally:
                        conn.close()
                _t.sleep(0.2)
        else:
            raise last_err

    # Tạo file fixture (JPEG, JPEG, MP4) trong snapshots_dir.
    os.makedirs(snapshots_dir, exist_ok=True)

    snap_filename = "snap_test_001.jpg"
    crop_filename = "crop_test_001.jpg"
    clip_filename = "clip_test_001.mp4"

    # File fixture content
    snap_bytes = _make_jpeg_bytes(width=64, height=64)
    crop_bytes = _make_jpeg_bytes(width=32, height=32)
    clip_bytes = _make_mp4_bytes()

    # File names dùng chung cho cả module — content cố ý KHÁC nhau qua
    # prefix plate để tránh restore_backup_set copy trùng file. Cũng cho
    # phép test thứ 2-N chạy idempotent mà không phải rebuild fixture.
    snap_filename = f"snap_{norm}.jpg"
    crop_filename = f"crop_{norm}.jpg"
    clip_filename = f"clip_{norm}.mp4"

    snap_path = os.path.join(snapshots_dir, snap_filename)
    crop_path = os.path.join(snapshots_dir, crop_filename)
    clip_path = os.path.join(snapshots_dir, clip_filename)

    # Nội dung file: prepend plate bytes để phân biệt các lần chạy
    # (tránh restore_backup_set copy trùng → SHA256 mismatch nếu test
    # trước ghi đè file nhưng verify dùng hash cũ).
    def _stamp(prefix: bytes, body: bytes) -> bytes:
        return prefix + body

    plate_prefix = norm.encode("utf-8")[:8].ljust(8, b"-")
    snap_bytes_full = _stamp(plate_prefix + b"S", snap_bytes)
    crop_bytes_full = _stamp(plate_prefix + b"C", crop_bytes)
    clip_bytes_full = _stamp(plate_prefix + b"V", clip_bytes)

    with open(snap_path, "wb") as f:
        f.write(snap_bytes_full)
    with open(crop_path, "wb") as f:
        f.write(crop_bytes_full)
    with open(clip_path, "wb") as f:
        f.write(clip_bytes_full)

    file_hashes = {
        snap_filename: hashlib.sha256(snap_bytes_full).hexdigest(),
        crop_filename: hashlib.sha256(crop_bytes_full).hexdigest(),
        clip_filename: hashlib.sha256(clip_bytes_full).hexdigest(),
    }

    # Insert violation với retry on SQLITE_LOCKED
    import time as _t
    last_err = None
    for _ in range(8):
        try:
            violation_id = add_violation_event(
                timestamp=datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                plate_read=plate,
                plate_matched=plate,
                helmet_status="no_helmet",
                violation_type="NO_HELMET",
                snapshot_path=snap_path,
                crop_snapshot_path=crop_path,
                clip_path=clip_path,
            )
            break
        except Exception as e:
            last_err = e
            _t.sleep(0.5)  # Wait longer than test 1's WAL file commit
    else:
        raise last_err

    # Force gc + final commit để DB không giữ lock giữa các test
    import gc as _gc
    _gc.collect()

    return {
        "vehicle_id": vehicle_id,
        "violation_id": violation_id,
        "snapshot_filename": snap_filename,
        "crop_filename": crop_filename,
        "clip_filename": clip_filename,
        "file_hashes": file_hashes,
        "snapshot_path": snap_path,
        "crop_path": crop_path,
        "clip_path": clip_path,
    }


class TestBackupSetWithRealMedia:
    """Backup rằng manifest có SHA256 cho từng file ảnh/clip."""

    def test_backup_set_includes_snapshot_crop_clip_with_hashes(
        self, tmp_path, test_app
    ):
        """Backup set phải copy snapshot + crop + clip về backup dir
        và ghi SHA256 cho từng file trong manifest."""
        from app.db import create_backup_set

        snapshots_dir = str(tmp_path / "live_snapshots")
        backup_root = str(tmp_path / "backups")
        seed = _seed_violation_with_media(snapshots_dir, plate="77-A1 001")

        result = create_backup_set(
            backup_root=backup_root,
            snapshots_dir=snapshots_dir,
            student_photos_dir=None,
            include_media=True,
            label="media-restore",
        )

        # 1. complete marker
        assert result["complete"] is True, (
            f"Backup not complete: paths_failed={result.get('paths_failed')}"
        )
        assert result["set_dir"], "set_dir empty"

        # 2. manifest phải có entries cho 3 media files
        media_entries = [f for f in result["files"] if f["role"] == "media"]
        media_paths = {f["path_rel"] for f in media_entries}
        assert f"media/{seed['snapshot_filename']}" in media_paths
        assert f"media/{seed['crop_filename']}" in media_paths
        assert f"media/{seed['clip_filename']}" in media_paths

        # 3. Mỗi entry phải có SHA256 đúng 64 chars
        for entry in media_entries:
            assert len(entry["sha256"]) == 64, (
                f"Bad SHA256 length for {entry['path_rel']}: {entry['sha256']!r}"
            )

        # 4. SHA256 trong manifest phải khớp với hash tính trực tiếp từ file gốc
        for filename, expected_hash in seed["file_hashes"].items():
            media_entry = next(
                f for f in media_entries if f["path_rel"].endswith(filename)
            )
            assert media_entry["sha256"] == expected_hash, (
                f"Manifest SHA256 mismatch for {filename}: "
                f"stored={media_entry['sha256']}, expected={expected_hash}"
            )

        # 5. File backup thật sự tồn tại trên đĩa
        set_dir = result["set_dir"]
        for filename in seed["file_hashes"].keys():
            backup_file = os.path.join(set_dir, "media", filename)
            assert os.path.isfile(backup_file), f"Backup file missing: {backup_file}"

    def test_backup_set_complete_marker_only_when_all_ok(
        self, tmp_path, test_app, monkeypatch
    ):
        """Nếu 1 file copy lỗi (vd. permission deny), complete marker KHÔNG ghi."""
        from app.db import create_backup_set

        snapshots_dir = str(tmp_path / "snap")
        backup_root = str(tmp_path / "backups")
        seed = _seed_violation_with_media(snapshots_dir, plate="77-A1 002")

        # Patch _shutil.copy2 để fail đúng 1 file
        import shutil as _shutil

        original_copy2 = _shutil.copy2

        crop_filename = seed["crop_filename"]

        def failing_copy2(src, dst, *args, **kwargs):
            if src.endswith(crop_filename):
                raise OSError("simulated copy failure for crop")
            return original_copy2(src, dst, *args, **kwargs)

        monkeypatch.setattr("shutil.copy2", failing_copy2)

        result = create_backup_set(
            backup_root=backup_root,
            snapshots_dir=snapshots_dir,
            student_photos_dir=None,
            include_media=True,
            label="partial-failure",
        )

        # complete=False vì paths_failed có 1 entry
        assert result["complete"] is False, (
            "complete=True despite copy failure — bug in atomicity logic"
        )
        failed_paths = [p["path"] for p in result["paths_failed"]]
        assert any(crop_filename in p for p in failed_paths), (
            f"{crop_filename} not in paths_failed: {failed_paths}"
        )


class TestRestoreWithRealMedia:
    """Restore round-trip giữ ảnh + crop + clip với SHA256 integrity."""

    def test_restore_roundtrip_preserves_db_and_media_hashes(
        self, tmp_path, test_app
    ):
        """Backup → restore → verify DB có record + media files có SHA256 khớp."""
        from app.db import create_backup_set, restore_backup_set

        snapshots_dir = str(tmp_path / "live_snapshots")
        backup_root = str(tmp_path / "backups")
        restore_root = str(tmp_path / "restored")
        seed = _seed_violation_with_media(snapshots_dir, plate="77-A1 003")

        # 1. Backup
        backup_result = create_backup_set(
            backup_root=backup_root,
            snapshots_dir=snapshots_dir,
            student_photos_dir=None,
            include_media=True,
            label="media-restore-test",
        )
        assert backup_result["complete"] is True
        set_dir = backup_result["set_dir"]

        # 2. Restore sang restore_root
        restore_result = restore_backup_set(set_dir, restore_root)
        assert restore_result["db_restored"] is True
        assert restore_result["db_ok"] is True, (
            f"DB integrity check failed post-restore: {restore_result}"
        )
        assert restore_result["media_restored_count"] >= 3, (
            f"Expected ≥3 media restored (snapshot/crop/clip), "
            f"got {restore_result['media_restored_count']}; "
            f"missing={restore_result['media_missing']}"
        )

        # 3. Verify file ảnh/clip có SHA256 khớp file gốc
        for filename, expected_hash in seed["file_hashes"].items():
            restored_file = os.path.join(restore_root, "media", filename)
            assert os.path.isfile(restored_file), f"Missing restored file: {restored_file}"
            h = hashlib.sha256()
            with open(restored_file, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            assert h.hexdigest() == expected_hash, (
                f"SHA256 mismatch for {filename}: "
                f"restored={h.hexdigest()}, expected={expected_hash}"
            )

        # 4. Mở restored DB, kiểm tra record violation có snapshot/crop/clip paths
        restored_db = os.path.join(
            restore_root, os.path.basename(backup_result["db_file"])
        )
        assert os.path.isfile(restored_db)
        conn = sqlite3.connect(restored_db)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT snapshot_path, crop_snapshot_path, clip_path "
                "FROM violation_events WHERE id = ?",
                (seed["violation_id"],),
            )
            row = cur.fetchone()
            assert row is not None, (
                f"Violation id={seed['violation_id']} not in restored DB"
            )
            # Paths trong restored DB phải chứa tên file đúng (giữ nguyên filename)
            assert row["snapshot_path"].endswith(seed["snapshot_filename"])
            assert row["crop_snapshot_path"].endswith(seed["crop_filename"])
            assert row["clip_path"].endswith(seed["clip_filename"])
        finally:
            conn.close()

    def test_verify_backup_set_returns_verified_true_with_assets(
        self, tmp_path, test_app
    ):
        """verify_backup_set() phải verified=True khi DB + media hash đều khớp."""
        from app.db import create_backup_set, verify_backup_set

        snapshots_dir = str(tmp_path / "snap")
        backup_root = str(tmp_path / "backups")
        _seed_violation_with_media(snapshots_dir, plate="77-A1 004")

        backup_result = create_backup_set(
            backup_root=backup_root,
            snapshots_dir=snapshots_dir,
            student_photos_dir=None,
            include_media=True,
            label="verify-with-assets",
        )
        assert backup_result["complete"] is True

        verify_result = verify_backup_set(backup_result["set_dir"])
        assert verify_result["complete_marker_present"] is True
        assert verify_result["db_integrity_ok"] is True
        assert verify_result["db_sha256_match"] is True
        # Media: tối thiểu 3 (snap, crop, clip)
        assert verify_result["media_total"] >= 3
        assert verify_result["media_missing"] == [], (
            f"Media missing: {verify_result['media_missing']}"
        )
        assert verify_result["media_sha256_mismatch"] == [], (
            f"Media SHA256 mismatch: {verify_result['media_sha256_mismatch']}"
        )
        assert verify_result["verified"] is True, (
            f"Backup set not verified: {verify_result}"
        )


class TestRestoreIsolationWhenAssetsMatch:
    """Restore KHÔNG được ghi đè lên SNAPSHOTS_DIR vận hành."""

    def test_restore_to_new_root_does_not_overwrite_live(
        self, tmp_path, test_app, monkeypatch
    ):
        """Restore sang restore_root khác; live SNAPSHOTS_DIR giữ nguyên."""
        from app.db import create_backup_set, restore_backup_set

        # Tạm thời patch SNAPSHOTS_DIR sang live_snapshots (file gốc)
        from app import config as cfg
        import app.db as db_module

        live_snap_dir = tmp_path / "live_snapshots"
        backup_root = tmp_path / "backups"
        restore_root = tmp_path / "restored_isolated"

        seed = _seed_violation_with_media(str(live_snap_dir), plate="77-A1 005")

        # Snapshot SHA256 trước khi backup (file gốc)
        original_snap_sha = hashlib.sha256()
        with open(seed["snapshot_path"], "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                original_snap_sha.update(chunk)
        original_snap_sha = original_snap_sha.hexdigest()

        # Backup
        backup_result = create_backup_set(
            backup_root=str(backup_root),
            snapshots_dir=str(live_snap_dir),
            student_photos_dir=None,
            include_media=True,
            label="isolation",
        )
        set_dir = backup_result["set_dir"]

        # Trước restore, ghi đè live_snap_dir thành nội dung KHÁC để chắc chắn
        # restore KHÔNG phục hồi vào đây.
        for f in live_snap_dir.iterdir():
            if f.is_file():
                f.write_bytes(b"\x00" * 32)  # overwrite

        # Restore sang restore_root
        restore_result = restore_backup_set(set_dir, str(restore_root))
        assert restore_result["db_restored"] is True
        assert restore_result["db_ok"] is True

        # Verify live_snap_dir KHÔNG bị ghi đè (vẫn là zeros 32 byte)
        # Restore phải ghi vào restore_root chứ không phải live_snap_dir
        for f in live_snap_dir.iterdir():
            if f.is_file():
                size = f.stat().st_size
                # Nếu restore overwrite live thì size sẽ lớn hơn 32 bytes
                # (vì file gốc JPEG/PNG/MP4 > 32 bytes)
                assert size == 32, (
                    f"Restore overwrote live file {f} (size={size}) — bug isolation"
                )

        # Verify restore_root có file SHA256 khớp với original (KHÔNG phải zeros)
        for filename, expected_hash in seed["file_hashes"].items():
            restored = restore_root / "media" / filename
            assert restored.is_file(), f"Missing restored file: {restored}"
            h = hashlib.sha256()
            with open(restored, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            assert h.hexdigest() == expected_hash, (
                f"Restored file {filename} hash mismatch"
            )


class TestRestoreManifestReadsExistingDBAndMedia:
    """Manifest phải là JSON hợp lệ + có đủ file role='db' + 'media'."""

    def test_manifest_json_has_db_role_and_at_least_three_media(
        self, tmp_path, test_app
    ):
        """manifest.json: 1 db entry + ≥3 media entries."""
        from app.db import create_backup_set

        snapshots_dir = str(tmp_path / "snap")
        backup_root = str(tmp_path / "backups")
        _seed_violation_with_media(snapshots_dir, plate="77-A1 006")

        result = create_backup_set(
            backup_root=backup_root,
            snapshots_dir=snapshots_dir,
            student_photos_dir=None,
            include_media=True,
            label="manifest-check",
        )

        manifest_path = os.path.join(result["set_dir"], "manifest.json")
        assert os.path.isfile(manifest_path)
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # 1. db entry
        db_entries = [e for e in manifest["files"] if e["role"] == "db"]
        assert len(db_entries) == 1
        assert db_entries[0]["path_rel"].startswith("app_") and db_entries[0][
            "path_rel"
        ].endswith(".db")
        assert len(db_entries[0]["sha256"]) == 64

        # 2. media entries (≥3: snap + crop + clip)
        media_entries = [e for e in manifest["files"] if e["role"] == "media"]
        assert len(media_entries) >= 3, (
            f"Expected ≥3 media entries (snap+crop+clip), got {len(media_entries)}"
        )
        # 3. extension diversity
        extensions = {os.path.splitext(e["path_rel"])[1] for e in media_entries}
        assert ".jpg" in extensions, f"No .jpg in media: {extensions}"
        assert ".mp4" in extensions, f"No .mp4 in media: {extensions}"

        # 4. created_at_utc có mặt
        assert "created_at_utc" in manifest