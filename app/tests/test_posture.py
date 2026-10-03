"""
pytest tests for Step 20: posture_status column + RIDING_THROUGH_GATE stats.
"""
import pytest
import numpy as np
from unittest.mock import patch
from fastapi import status
from app.cv.detector import Detection


class TestRunPostureDetectionGroupDict:
    """
    Regression test: _run_posture_detection must read the person out of the
    group dict (group['_person']), not getattr(group, '_person', None) —
    getattr on a dict never matches a dict key, which silently forced every
    group to posture_status='unknown' regardless of the actual pose.
    """

    def test_uses_person_bbox_from_group_dict(self):
        from app.cv.pipeline import VideoPipeline

        from concurrent.futures import ThreadPoolExecutor
        pipeline = VideoPipeline.__new__(VideoPipeline)  # skip __init__ (no camera/models)
        pipeline._detect_pool = ThreadPoolExecutor(max_workers=1)
        pipeline._source_epoch = 0
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        person = Detection(class_name="person", confidence=0.9, bbox=(10, 10, 100, 190))
        vehicle = Detection('motorcycle', .9, (20,90,140,190), 7)
        groups = [{"_person": person, '_vehicle':vehicle, 'track_id':42, 'vehicle_track_id':7,
                   "helmet_dets": [], "plate_dets": []}]

        with patch("app.cv.pose.PostureDetector.detect_pose") as mock_detect:
            points=[{'x':0,'y':0,'confidence':0} for _ in range(17)]
            for index,xy in {5:(50,40),6:(50,40),11:(50,100),12:(50,100),
                             13:(50,130),14:(50,130),15:(80,130),16:(80,130)}.items():
                points[index]={'x':xy[0],'y':xy[1],'confidence':.9}
            mock_detect.return_value = points
            try:
                result = pipeline._run_posture_detection(frame, groups)
            finally:
                pipeline._detect_pool.shutdown(wait=True)

        assert mock_detect.called, "detect_pose was never reached — person lookup still broken"
        assert result[0]["posture_status"] == "riding"


class TestPostureStatusColumn:
    """Test that posture_status is correctly stored in violation_events."""

    def test_add_violation_with_posture_status(self, client):
        """add_violation_event accepts posture_status kwarg."""
        from app.tests.conftest import auth_headers

        # Login
        client.post("/api/auth/login", json={"username": "admin", "password": "test123"})

        # The add_violation_event is called internally by the pipeline
        # We test indirectly via the existing vehicle add + check DB directly
        import app.db as db_module
        import datetime

        # Directly insert a violation with posture_status
        event_id = db_module.add_violation_event(
            timestamp=datetime.datetime.now().isoformat(),
            plate_read="TEST001",
            plate_matched="TEST001",
            helmet_status="no_helmet",
            violation_type="RIDING_THROUGH_GATE",
            snapshot_path=None,
            posture_status="riding",
        )
        assert isinstance(event_id, int)
        assert event_id > 0

    def test_add_violation_without_posture_status(self, client):
        """posture_status is optional (None by default)."""
        import app.db as db_module
        import datetime

        event_id = db_module.add_violation_event(
            timestamp=datetime.datetime.now().isoformat(),
            plate_read="TEST002",
            plate_matched=None,
            helmet_status="unknown",
            violation_type="PLATE_UNREADABLE",
            snapshot_path=None,
        )
        assert isinstance(event_id, int)

    def test_violation_stats_includes_riding_through_gate(self, client):
        """get_violation_stats includes RIDING_THROUGH_GATE in by_type."""
        import app.db as db_module

        stats = db_module.get_violation_stats()
        assert "by_type" in stats
        assert "RIDING_THROUGH_GATE" in stats["by_type"]
        assert isinstance(stats["by_type"]["RIDING_THROUGH_GATE"], int)


class TestRidingThroughGateViolation:
    """Test that RIDING_THROUGH_GATE violations can be created via the API."""

    def test_list_violations_includes_riding_through_gate(self, client):
        """list_violations returns records with RIDING_THROUGH_GATE."""
        import app.db as db_module
        import datetime

        # Insert test violation
        db_module.add_violation_event(
            timestamp=datetime.datetime.now().isoformat(),
            plate_read="RIDE001",
            plate_matched=None,
            helmet_status="unknown",
            violation_type="RIDING_THROUGH_GATE",
            snapshot_path=None,
            posture_status="riding",
        )

        from app.tests.conftest import auth_headers
        client.post("/api/auth/login", json={"username": "admin", "password": "test123"})

        r = client.get("/api/violations", headers=auth_headers(client, "admin"))
        assert r.status_code == status.HTTP_200_OK
        items = r.json()["items"]
        riding_items = [i for i in items if i["violation_type"] == "RIDING_THROUGH_GATE"]
        assert len(riding_items) > 0
        # Check posture_status is present in response
        first_riding = riding_items[0]
        assert "posture_status" in first_riding
