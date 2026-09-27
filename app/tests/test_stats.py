"""
pytest tests for get_violation_stats() trend/by_class additions (dashboard analytics).
"""
import datetime


def test_trend_has_14_days_including_zero_count_days(client):
    from app.db import get_violation_stats

    stats = get_violation_stats()
    trend = stats["trend"]
    assert len(trend) == 14
    # Dates must be consecutive, ending today (localtime), regardless of whether
    # any violation happened on a given day (zero-count days must still appear).
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    assert trend[-1]["date"] == today
    for point in trend:
        assert "date" in point and "count" in point
        assert point["count"] >= 0


def test_by_class_groups_matched_plate_to_registered_vehicle(client):
    from app.db import add_vehicle, add_violation_event, get_violation_stats

    add_vehicle("29X99999", "Nguyen Van Test", "12A9")
    add_violation_event(
        timestamp=datetime.datetime.now().isoformat(),
        plate_read="29X99999",
        plate_matched="29X99999",
        helmet_status="no_helmet",
        violation_type="NO_HELMET",
    )
    stats = get_violation_stats()
    classes = {c["class_name"]: c["count"] for c in stats["by_class"]}
    assert classes.get("12A9", 0) >= 1


def test_by_class_unmatched_plate_falls_into_unknown_bucket(client):
    from app.db import add_violation_event, get_violation_stats

    add_violation_event(
        timestamp=datetime.datetime.now().isoformat(),
        plate_read="",
        plate_matched=None,
        helmet_status="unknown",
        violation_type="PLATE_UNREADABLE",
    )
    stats = get_violation_stats()
    classes = {c["class_name"]: c["count"] for c in stats["by_class"]}
    assert classes.get("Không xác định", 0) >= 1
