"""
pytest tests for Step 20: posture_status column + RIDING_THROUGH_GATE stats.
"""
import pytest
from fastapi import status


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
