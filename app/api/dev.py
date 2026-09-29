"""
Dev/test-only endpoints — FOR AUTOMATED TESTING ONLY.
Must be secured or removed before production deployment.
"""
from datetime import datetime
from fastapi import APIRouter, Depends
from app.auth import require_role

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/trigger-test-alert")
def trigger_test_alert(
    violation_type: str = "NO_HELMET",
    plate_read: str = "TEST123",
    snapshot_url: str | None = None,
    _current_user: dict = Depends(require_role("security", "admin")),
):
    """
    Push a fake violation alert into the WebSocket queue.
    Only for automated testing — does NOT log to DB.
    Requires admin role.

    Bypasses ALERT_COOLDOWN so tests are deterministic regardless of when
    the real camera last triggered an alert.
    """
    try:
        from app.cv.pipeline import get_pipeline
        pipeline = get_pipeline()
        alert = {
            "type": "violation",
            "violation_type": violation_type,
            "plate_read": plate_read,
            "plate_matched": None,
            "plate_format_valid": None,
            "snapshot_url": snapshot_url,
            "timestamp": datetime.now().isoformat(),
        }
        # ponytail: bypass cooldown — put directly in queue so tests are reliable.
        # Real camera-triggered alerts go through _push_alert() with cooldown.
        pipeline._alert_queue.put(alert)
        return {"ok": True, "alert": alert}
    except Exception as e:
        return {"ok": False, "error": str(e)}
