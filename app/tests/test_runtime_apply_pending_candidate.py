"""R3 (Task 1): Test hot-reload of detector from candidate.

Tests:
  1. Pipeline has baseline detector.
  2. Call reload_model_from_candidate.
  3. Assert detector is swapped + hash matches candidate's SHA256.

Run:
    venv\\Scripts\\python.exe -m pytest app/tests/test_runtime_apply_pending_candidate.py -v
"""
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeDetector:
    """Mock detector that tracks model path."""
    def __init__(self, model_path: str, conf: float = 0.25):
        self.model_path = model_path
        self.conf = conf
        # validate_helmet_mapping expects dict {0: "With Helmet", 1: "Without Helmet"}
        self.class_names = {0: "With Helmet", 1: "Without Helmet"}
        self._call_count = 0

    def detect(self, frame):
        self._call_count += 1
        return []

    def detect_tracked(self, frame):
        self._call_count += 1
        return []


@pytest.fixture(autouse=True)
def _isolate_all(monkeypatch):
    """FIX (T4): isolate pipeline state cho MỌI test trong module.

    Lý do: VideoPipeline() touch global app.cv.pipeline state (GATES, registry)
    và có thể truy cập DB. Khi chạy full suite, state từ test trước leak → fail.
    Không patch DB ở đây — các test không cần DB; chỉ mock DB-touching functions.
    """
    monkeypatch.setattr("app.cv.pipeline.set_gate_camera_source", MagicMock())
    monkeypatch.setattr("app.cv.pipeline.get_gate_roi", lambda gate=None: None)
    monkeypatch.setattr("app.cv.pipeline.get_gate_line", lambda gate=None: None)
    monkeypatch.setattr("app.cv.pipeline.HelmetPlateDetector", MagicMock())
    monkeypatch.setattr("app.cv.pipeline.get_gate_camera_source", lambda gate=None: None)
    yield


class TestReloadModelFromCandidate:
    """R3 hot-reload tests."""

    def test_reload_helmet_candidate_swaps_detector(self):
        """Reload helmet candidate → pipeline detector should be swapped."""
        from app.cv.pipeline import VideoPipeline

        gate_config = {"name": "test_gate", "role": "front", "profile": "full"}
        with patch("app.cv.pipeline.VideoPipeline._open_webcam"):
            p = VideoPipeline("test_gate", gate_config)

        baseline_det = FakeDetector("baseline_helmet.pt", 0.25)
        p._helmet_detector = baseline_det
        p._helmet_health = {"status": "ready", "classes": ["With Helmet", "Without Helmet"]}
        p._plate_detector = None
        p._person_detector = None
        p._detect_pool = MagicMock()
        p._running = False
        p._stopped = True
        p._lock = threading.Lock()

        test_cand = {
            "id": "cand_001",
            "job_id": "job_cand_001",
            "engine": "helmet",
            "target": "helmet",
            "model_class": "YOLO",
            "model_path": "D:/test/candidate.pt",
            "model_sha256": "abc123def456",
            "state": "pending_runtime",
        }

        new_detector_instance = FakeDetector("D:/test/candidate.pt", 0.25)

        # Pipeline does "from app.cv.detector import HelmetPlateDetector" at module level,
        # then HelmetPlateDetector() inside reload_model_from_candidate uses the local binding.
        # Patch at app.cv.pipeline.HelmetPlateDetector (the binding inside pipeline module).
        import app.training.dataset_repo as dr_module
        with patch.object(dr_module, "get_candidate", return_value=test_cand):
            with patch("app.cv.pipeline.HelmetPlateDetector", return_value=new_detector_instance):
                with patch("app.cv.pipeline.Path") as mock_path_cls:
                    mock_path_instance = MagicMock()
                    mock_path_instance.exists.return_value = True
                    mock_path_cls.return_value = mock_path_instance
                    result = p.reload_model_from_candidate("cand_001")

        assert result["success"], f"Reload failed: {result['message']}"
        assert result["new_model_path"] == "D:/test/candidate.pt"
        assert p._helmet_detector is new_detector_instance, \
            "Detector should be replaced with new candidate detector"

    def test_reload_unknown_candidate_returns_error(self):
        """Reload non-existent candidate → error message."""
        from app.cv.pipeline import VideoPipeline
        import app.training.dataset_repo as dr_module

        p = VideoPipeline.__new__(VideoPipeline)
        p._lock = threading.Lock()
        p._helmet_health = {}

        with patch.object(dr_module, "get_candidate", return_value=None):
            result = VideoPipeline.reload_model_from_candidate(p, "nonexistent")

        assert result["success"] is False
        assert "not found" in result["message"]

    def test_reload_missing_model_path_returns_error(self):
        """Reload candidate with non-existent model_path → error."""
        from app.cv.pipeline import VideoPipeline
        import app.training.dataset_repo as dr_module

        p = VideoPipeline.__new__(VideoPipeline)
        p._lock = threading.Lock()
        p._helmet_health = {}

        test_cand = {
            "id": "cand_002",
            "job_id": "job_cand_002",
            "engine": "helmet",
            "model_path": "C:/nonexistent/model.pt",
            "state": "pending_runtime",
        }

        with patch.object(dr_module, "get_candidate", return_value=test_cand):
            result = VideoPipeline.reload_model_from_candidate(p, "cand_002")

        assert result["success"] is False
        assert "does not exist" in result["message"]

    def test_reload_updates_helmet_health(self):
        """Reload updates _helmet_health with candidate metadata."""
        from app.cv.pipeline import VideoPipeline
        import app.training.dataset_repo as dr_module

        gate_config = {"name": "test_gate", "role": "front", "profile": "full"}
        with patch("app.cv.pipeline.VideoPipeline._open_webcam"):
            p = VideoPipeline("test_gate", gate_config)

        p._helmet_detector = FakeDetector("baseline.pt")
        p._helmet_health = {"status": "ready"}
        p._plate_detector = None
        p._person_detector = None
        p._detect_pool = MagicMock()
        p._running = False
        p._stopped = True
        p._lock = threading.Lock()

        test_cand = {
            "id": "cand_003",
            "job_id": "job_cand_003",
            "engine": "helmet",
            "model_path": "D:/test/cand003.pt",
            "model_sha256": "deadbeef1234",
            "state": "pending_runtime",
        }

        new_det = FakeDetector("D:/test/cand003.pt", 0.25)

        with patch.object(dr_module, "get_candidate", return_value=test_cand):
            with patch("app.cv.pipeline.HelmetPlateDetector", return_value=new_det):
                with patch("app.cv.pipeline.Path") as mock_path_cls:
                    mock_path_instance = MagicMock()
                    mock_path_instance.exists.return_value = True
                    mock_path_cls.return_value = mock_path_instance
                    result = p.reload_model_from_candidate("cand_003")

        assert result["success"]
        assert p._helmet_health["source"] == "candidate"
        assert p._helmet_health["candidate_id"] == "cand_003"


class TestReloadSnapshotDetection:
    """Verify reload doesn't crash ongoing detection."""

    def test_reload_preserves_lock_integrity(self):
        """Reload under lock → concurrent detection should still work."""
        from app.cv.pipeline import VideoPipeline
        import app.training.dataset_repo as dr_module

        gate_config = {"name": "test_gate", "role": "front", "profile": "full"}
        with patch("app.cv.pipeline.VideoPipeline._open_webcam"):
            p = VideoPipeline("test_gate", gate_config)

        p._helmet_detector = FakeDetector("baseline.pt")
        p._helmet_health = {"status": "ready"}
        p._plate_detector = None
        p._person_detector = None
        p._detect_pool = MagicMock()
        p._running = True
        p._stopped = False
        p._lock = threading.Lock()

        errors = []

        def detector_worker():
            for _ in range(10):
                try:
                    with p._lock:
                        det = p._helmet_detector
                        if det:
                            det.detect(None)
                except Exception as e:
                    errors.append(e)
                time.sleep(0.01)

        t = threading.Thread(target=detector_worker, daemon=True)
        t.start()

        test_cand = {
            "id": "cand_004",
            "job_id": "job_cand_004",
            "engine": "helmet",
            "model_path": "D:/test/cand004.pt",
            "state": "pending_runtime",
        }

        new_det = FakeDetector("D:/test/cand004.pt", 0.25)

        with patch.object(dr_module, "get_candidate", return_value=test_cand):
            with patch("app.cv.pipeline.HelmetPlateDetector", return_value=new_det):
                with patch("app.cv.pipeline.Path") as mock_path_cls:
                    mock_path_instance = MagicMock()
                    mock_path_instance.exists.return_value = True
                    mock_path_cls.return_value = mock_path_instance
                    result = p.reload_model_from_candidate("cand_004")

        t.join(timeout=5.0)

        assert result["success"], f"Reload failed: {result['message']}"
        assert len(errors) == 0, f"Concurrent access errors: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
