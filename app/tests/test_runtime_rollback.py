"""R3 (Task 1): Test rollback to baseline model.

Tests:
  1. Pipeline has candidate detector.
  2. Rollback to baseline.
  3. Assert detector path matches HELMET_MODEL_PATH.

Run:
    venv\\Scripts\\python.exe -m pytest app/tests/test_runtime_rollback.py -v
"""
import os
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeDetector:
    """Mock detector tracking model path."""
    def __init__(self, model_path: str):
        self.model_path = model_path
        # validate_helmet_mapping expects dict {0: "With Helmet", 1: "Without Helmet"}
        self.class_names = {0: "With Helmet", 1: "Without Helmet"}


class TestRollbackToBaseline:
    """R3 rollback tests."""

    def test_rollback_helmet_to_baseline(self):
        """Rollback helmet detector → should call HelmetPlateDetector with baseline path."""
        from app.cv.pipeline import VideoPipeline
        from app.config import HELMET_MODEL_PATH

        p = VideoPipeline.__new__(VideoPipeline)
        p._helmet_detector = FakeDetector("candidate_model.pt")
        p._helmet_health = {"status": "ready", "source": "candidate", "model_path": "candidate.pt"}
        p._plate_detector = None
        p._person_detector = None
        p._lock = threading.Lock()

        call_args = []

        def mock_detector_init(model_path, conf_threshold=0.25):
            call_args.append(model_path)
            inst = FakeDetector(model_path)
            inst.conf_threshold = conf_threshold
            return inst

        # Patch at app.cv.pipeline.HelmetPlateDetector (the binding the method uses)
        with patch("app.cv.pipeline.HelmetPlateDetector", side_effect=mock_detector_init):
            result = VideoPipeline.rollback_to_baseline(p, "helmet")

        assert result["success"], f"Rollback failed: {result['message']}"
        assert "baseline" in result["message"].lower()
        assert len(call_args) > 0, "HelmetPlateDetector should have been called"
        assert call_args[0] == HELMET_MODEL_PATH, \
            f"Expected baseline path={HELMET_MODEL_PATH}, got {call_args[0]}"

    def test_rollback_unknown_engine_returns_error(self):
        """Rollback unknown engine → error."""
        from app.cv.pipeline import VideoPipeline

        p = VideoPipeline.__new__(VideoPipeline)
        p._lock = threading.Lock()

        result = VideoPipeline.rollback_to_baseline(p, "unknown_engine")

        assert result["success"] is False
        assert "Unknown engine" in result["message"]

    def test_rollback_updates_helmet_health(self):
        """Rollback updates _helmet_health to baseline source."""
        from app.cv.pipeline import VideoPipeline

        p = VideoPipeline.__new__(VideoPipeline)
        p._helmet_detector = FakeDetector("candidate.pt")
        p._helmet_health = {"status": "ready", "source": "candidate"}
        p._plate_detector = None
        p._person_detector = None
        p._lock = threading.Lock()

        def mock_detector_init(model_path, conf_threshold=0.25):
            inst = FakeDetector(model_path)
            return inst

        with patch("app.cv.pipeline.HelmetPlateDetector", side_effect=mock_detector_init):
            result = VideoPipeline.rollback_to_baseline(p, "helmet")

        assert result["success"]
        assert p._helmet_health["source"] == "baseline"

    def test_rollback_uses_correct_threshold(self):
        """Rollback uses the correct conf_threshold per detector type."""
        from app.cv.pipeline import VideoPipeline
        from app.config import HELMET_CONF_THRESHOLD

        p = VideoPipeline.__new__(VideoPipeline)
        p._helmet_detector = FakeDetector("candidate.pt")
        p._helmet_health = {}
        p._plate_detector = None
        p._person_detector = None
        p._lock = threading.Lock()

        call_args = []

        def mock_detector_init(model_path, conf_threshold=0.25):
            call_args.append(conf_threshold)
            inst = FakeDetector(model_path)
            inst.conf_threshold = conf_threshold
            return inst

        with patch("app.cv.pipeline.HelmetPlateDetector", side_effect=mock_detector_init):
            result = VideoPipeline.rollback_to_baseline(p, "helmet")

        assert result["success"]
        assert len(call_args) > 0, "Should have called HelmetPlateDetector"
        assert call_args[0] == HELMET_CONF_THRESHOLD, \
            f"Expected conf_threshold={HELMET_CONF_THRESHOLD}, got {call_args[0]}"


class TestHotReloadAndRollbackFlow:
    """R3: Full flow test — reload then rollback."""

    def test_reload_then_rollback_cycle(self):
        """Reload candidate → rollback to baseline → state restored."""
        from app.cv.pipeline import VideoPipeline
        from app.config import HELMET_MODEL_PATH

        p = VideoPipeline.__new__(VideoPipeline)
        p._helmet_detector = FakeDetector("candidate.pt")
        p._helmet_health = {"status": "ready", "source": "candidate", "model_path": "candidate.pt"}
        p._plate_detector = None
        p._person_detector = None
        p._lock = threading.Lock()

        # Mock get_candidate for reload
        import app.training.dataset_repo as dr_module
        test_cand = {
            "id": "cand_test",
            "engine": "helmet",
            "model_path": "candidate.pt",
            "state": "pending_runtime",
        }

        reload_det = FakeDetector("candidate.pt")

        with patch.object(dr_module, "get_candidate", return_value=test_cand):
            with patch("app.cv.pipeline.HelmetPlateDetector", return_value=reload_det):
                with patch("app.cv.pipeline.Path") as mock_path_cls:
                    mock_path_instance = MagicMock()
                    mock_path_instance.exists.return_value = True
                    mock_path_cls.return_value = mock_path_instance
                    reload_result = VideoPipeline.reload_model_from_candidate(p, "cand_test")

        assert reload_result["success"]

        # Rollback
        rollback_calls = []

        def mock_rollback_init(model_path, conf_threshold=0.25):
            rollback_calls.append(model_path)
            inst = FakeDetector(model_path)
            return inst

        with patch("app.cv.pipeline.HelmetPlateDetector", side_effect=mock_rollback_init):
            rollback_result = VideoPipeline.rollback_to_baseline(p, "helmet")

        assert rollback_result["success"]
        assert p._helmet_health["source"] == "baseline"
        assert len(rollback_calls) > 0
        assert rollback_calls[0] == HELMET_MODEL_PATH


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
