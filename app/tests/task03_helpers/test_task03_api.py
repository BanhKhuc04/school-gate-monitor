"""Tests cho Task 3 API — datasets, jobs, candidates, export/import.

Sử dụng fixture task03_app + task03_client để cô lập khỏi runtime DB.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _sample(target_id: str = "s1", review_id: str = "r1") -> dict:
    return {
        "target_id": target_id,
        "review_id": review_id,
        "gate_id": "main",
        "label": {"verdict": "correct", "target_text": "89F123792",
                  "top_line": "89F1", "bottom_line": "23792"},
        "source": {
            "gate_id": "main", "camera_id": "main-front", "run_id": "run_1",
            "frame_seq": 1, "source_epoch": 0,
            "crop_sha256": "abc", "crop_media_id": "abc.jpg",
            "image_w": 200, "image_h": 100,
        },
    }


def test_list_datasets_requires_admin(task03_client):
    # Anonymous: 401
    resp = task03_client.get("/api/training/datasets")
    assert resp.status_code in (401, 403)
    # Teacher: 403 (chỉ admin)
    teacher_headers = {"Authorization": f"Bearer {_get_token(task03_client, 'teacher')}"}
    resp = task03_client.get("/api/training/datasets", headers=teacher_headers)
    assert resp.status_code == 403
    # Admin OK
    admin_headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    resp = task03_client.get("/api/training/datasets", headers=admin_headers)
    assert resp.status_code == 200


def test_create_dataset_and_add_samples(task03_client):
    headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    resp = task03_client.post("/api/training/datasets",
                              json={"name": "ocr_v1", "engine": "plate_ocr", "notes": "test"},
                              headers=headers)
    assert resp.status_code == 200, resp.text
    ds_id = resp.json()["dataset_id"]
    # Add samples
    resp = task03_client.post(f"/api/training/datasets/{ds_id}/samples",
                              json={"samples": [_sample("s1"), _sample("s2")]},
                              headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["added"] == 2
    # List
    resp = task03_client.get(f"/api/training/datasets/{ds_id}/samples", headers=headers)
    assert resp.json()["count"] == 2


def test_freeze_then_add_samples_blocked(task03_client):
    headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    resp = task03_client.post("/api/training/datasets",
                              json={"name": "freeze_v1", "engine": "plate_ocr"},
                              headers=headers)
    ds_id = resp.json()["dataset_id"]
    task03_client.post(f"/api/training/datasets/{ds_id}/samples",
                       json={"samples": [_sample("s1")]}, headers=headers)
    resp = task03_client.post(f"/api/training/datasets/{ds_id}/freeze", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["sample_count"] == 1
    # Sau freeze không thêm được
    resp = task03_client.post(f"/api/training/datasets/{ds_id}/samples",
                              json={"samples": [_sample("extra")]}, headers=headers)
    assert resp.status_code == 400


def test_split_creates_distinct_train_val_test(task03_client):
    headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    resp = task03_client.post("/api/training/datasets",
                              json={"name": "split_v1", "engine": "plate_ocr"},
                              headers=headers)
    ds_id = resp.json()["dataset_id"]
    samples = []
    for g in range(20):
        for i in range(5):
            samples.append(_sample(target_id=f"s{g}_{i}",
                                   review_id=f"r{g}_{i}"))
            samples[-1]["encounter_id"] = f"enc_{g}"
    task03_client.post(f"/api/training/datasets/{ds_id}/samples",
                       json={"samples": samples}, headers=headers)
    resp = task03_client.post(f"/api/training/datasets/{ds_id}/split",
                              json={"seed": 42, "ratios": {"train": 0.7, "val": 0.15, "test": 0.15}},
                              headers=headers)
    assert resp.status_code == 200
    counts = resp.json()["counts"]
    assert counts["train"] + counts["val"] + counts["test"] == 100
    assert counts["train"] > counts["val"]


def test_leakage_endpoint(task03_client):
    headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    resp = task03_client.post("/api/training/datasets",
                              json={"name": "lk_v1", "engine": "plate_ocr"},
                              headers=headers)
    ds_id = resp.json()["dataset_id"]
    samples = []
    for g in range(5):
        for i in range(3):
            s = _sample(target_id=f"s{g}_{i}", review_id=f"r{g}_{i}")
            s["encounter_id"] = f"enc_{g}"
            samples.append(s)
    task03_client.post(f"/api/training/datasets/{ds_id}/samples",
                       json={"samples": samples}, headers=headers)
    task03_client.post(f"/api/training/datasets/{ds_id}/split",
                       json={"seed": 1}, headers=headers)
    resp = task03_client.get(f"/api/training/datasets/{ds_id}/leakage",
                              headers=headers)
    assert resp.status_code == 200
    assert "findings" in resp.json()


def test_patch_bbox_updates_version_and_history(task03_client):
    headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    resp = task03_client.post("/api/training/datasets",
                              json={"name": "bb_v1", "engine": "plate_detector"},
                              headers=headers)
    ds_id = resp.json()["dataset_id"]
    s = _sample("bb1", "rv_bb1")
    s["bbox"] = [0.1, 0.1, 0.5, 0.5]
    task03_client.post(f"/api/training/datasets/{ds_id}/samples",
                       json={"samples": [s]}, headers=headers)
    # PATCH ok với expected_version=0
    resp = task03_client.patch(
        f"/api/training/datasets/{ds_id}/samples/bb1/bbox",
        json={"bbox": [0.2, 0.2, 0.6, 0.6], "expected_version": 0,
              "reason": "test_edit"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bbox"] == [0.2, 0.2, 0.6, 0.6]
    assert body["version"] == 1
    assert body["history_len"] == 1
    # PATCH lần 2 với expected_version cũ → 409
    resp = task03_client.patch(
        f"/api/training/datasets/{ds_id}/samples/bb1/bbox",
        json={"bbox": [0.3, 0.3, 0.7, 0.7], "expected_version": 0,
              "reason": "stale"},
        headers=headers,
    )
    assert resp.status_code == 409
    # PATCH với bbox invalid → 400
    resp = task03_client.patch(
        f"/api/training/datasets/{ds_id}/samples/bb1/bbox",
        json={"bbox": [0.9, 0.9, 0.1, 0.1], "expected_version": 1,
              "reason": "invalid"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_patch_bbox_blocked_when_frozen(task03_client):
    headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    resp = task03_client.post("/api/training/datasets",
                              json={"name": "fbb_v1", "engine": "plate_detector"},
                              headers=headers)
    ds_id = resp.json()["dataset_id"]
    s = _sample("fbb1", "rv_fbb1")
    s["bbox"] = [0.1, 0.1, 0.5, 0.5]
    task03_client.post(f"/api/training/datasets/{ds_id}/samples",
                       json={"samples": [s]}, headers=headers)
    task03_client.post(f"/api/training/datasets/{ds_id}/freeze", headers=headers)
    resp = task03_client.patch(
        f"/api/training/datasets/{ds_id}/samples/fbb1/bbox",
        json={"bbox": [0.2, 0.2, 0.6, 0.6], "expected_version": 0,
              "reason": "after_freeze"},
        headers=headers,
    )
    assert resp.status_code == 409


def test_patch_bbox_requires_admin(task03_client):
    headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    resp = task03_client.post("/api/training/datasets",
                              json={"name": "rbb_v1", "engine": "plate_detector"},
                              headers=headers)
    ds_id = resp.json()["dataset_id"]
    s = _sample("rbb1", "rv_rbb1")
    s["bbox"] = [0.1, 0.1, 0.5, 0.5]
    task03_client.post(f"/api/training/datasets/{ds_id}/samples",
                       json={"samples": [s]}, headers=headers)
    # Security không được phép
    sec = {"Authorization": f"Bearer {_get_token(task03_client, 'security')}"}
    resp = task03_client.patch(
        f"/api/training/datasets/{ds_id}/samples/rbb1/bbox",
        json={"bbox": [0.2, 0.2, 0.6, 0.6], "expected_version": 0,
              "reason": "by_security"},
        headers=sec,
    )
    assert resp.status_code in (401, 403)


def test_create_job_then_cancel(task03_client):
    headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    # Tạo dataset + freeze để job có snapshot
    resp = task03_client.post("/api/training/datasets",
                              json={"name": "job_v1", "engine": "plate_ocr"},
                              headers=headers)
    ds_id = resp.json()["dataset_id"]
    task03_client.post(f"/api/training/datasets/{ds_id}/samples",
                       json={"samples": [_sample("s1")]}, headers=headers)
    task03_client.post(f"/api/training/datasets/{ds_id}/freeze", headers=headers)
    # Tạo job
    resp = task03_client.post("/api/training/jobs",
                              json={"dataset_id": ds_id, "target": "plate_ocr",
                                    "config": {"epochs": 1}},
                              headers=headers)
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    # Get job
    resp = task03_client.get(f"/api/training/jobs/{job_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["state"] == "queued"
    # Cancel
    resp = task03_client.post(f"/api/training/jobs/{job_id}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["cancelled"] is True
    # Cancel 2 lần — idempotent
    resp = task03_client.post(f"/api/training/jobs/{job_id}/cancel", headers=headers)
    assert resp.json()["cancelled"] is False


def test_candidates_promote_and_rollback(task03_client, tmp_path):
    headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    # Tạo dataset
    resp = task03_client.post("/api/training/datasets",
                              json={"name": "cand_v1", "engine": "plate_ocr"},
                              headers=headers)
    ds_id = resp.json()["dataset_id"]
    # Tạo job + candidate (qua repo trực tiếp vì API tạo candidate qua runner)
    from app.training import dataset_repo
    import hashlib
    training_db = os.environ["TRAINING_DB_PATH"]
    job_id = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                      config={}, db_path=training_db)
    weights = tmp_path / "weights_api.bin"
    import torch  # type: ignore
    torch.save({"weights": "fake_state_8s"}, str(weights))
    sha = hashlib.sha256(weights.read_bytes()).hexdigest()
    cand_a = dataset_repo.create_candidate(
        job_id=job_id, engine="plate_ocr", target="plate_ocr",
        model_class="EasyOCR.Reader", model_path=str(weights),
        config={"class_mapping": {"alphabet": "0-9A-Z"}}, db_path=training_db,
    )
    # E6: cần model_sha256 + metrics_path file
    metrics_p = tmp_path / "metrics_api.json"
    metrics_p.write_text(json.dumps({"exact_match_pct": 70.0, "cer_avg": 0.1, "total": 30}),
                         encoding="utf-8")
    conn = dataset_repo._connect(training_db)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dataset_candidates SET model_sha256=? WHERE id=?",
                    (sha, cand_a))
        cur.execute("UPDATE dataset_jobs SET state='completed', finished_at=datetime('now'), "
                    "metrics_path=?, runner_type='train' WHERE id=?",
                    (str(metrics_p), job_id))
        conn.commit()
    finally:
        conn.close()
    # Promote
    resp = task03_client.post(f"/api/training/candidates/{cand_a}/promote",
                              json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "pending_runtime"
    # Active (registry) — promotion gate không set active trực tiếp, đó là việc Task 1
    resp = task03_client.get("/api/training/candidates/active",
                              params={"engine": "plate_ocr"}, headers=headers)
    # Có thể chưa có active (pending_runtime) — rollback vẫn work (retire current
    # không có) nhưng cần restore baseline nếu có
    # Rollback
    resp = task03_client.post("/api/training/candidates/rollback",
                              params={"engine": "plate_ocr"}, headers=headers)
    assert resp.json()["rolled_back"] is False  # không có active để rollback


def test_export_requires_frozen(task03_client):
    headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    resp = task03_client.post("/api/training/datasets",
                              json={"name": "unfrozen", "engine": "plate_ocr"},
                              headers=headers)
    ds_id = resp.json()["dataset_id"]
    # Không freeze → 400
    resp = task03_client.post("/api/training/export",
                              json={"dataset_id": ds_id}, headers=headers)
    assert resp.status_code == 400


def test_import_preview_and_apply_round_trip(task03_client, tmp_path):
    headers = {"Authorization": f"Bearer {_get_token(task03_client, 'admin')}"}
    # 1. Tạo dataset + freeze
    resp = task03_client.post("/api/training/datasets",
                              json={"name": "exp_v1", "engine": "plate_ocr"},
                              headers=headers)
    ds_id = resp.json()["dataset_id"]
    task03_client.post(f"/api/training/datasets/{ds_id}/samples",
                       json={"samples": [_sample("s1"), _sample("s2")]}, headers=headers)
    task03_client.post(f"/api/training/datasets/{ds_id}/freeze", headers=headers)
    # 2. Export → ZIP
    resp = task03_client.post("/api/training/export",
                              json={"dataset_id": ds_id}, headers=headers)
    assert resp.status_code == 200, resp.text
    zip_path = resp.json()["zip_path"]
    # 3. Preview
    with open(zip_path, "rb") as f:
        resp = task03_client.post(
            "/api/training/import/preview",
            files={"file": ("out.zip", f, "application/zip")},
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert preview["counts"]["total"] == 2
    # 4. Apply
    with open(zip_path, "rb") as f:
        resp = task03_client.post(
            "/api/training/import/apply",
            files={"file": ("out.zip", f, "application/zip")},
            data={"dataset_name": "imp_v1"},
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["added"] == 2


def _get_token(client, role: str) -> str:
    resp = client.post("/api/auth/login",
                       json={"username": role, "password": "test123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


import os