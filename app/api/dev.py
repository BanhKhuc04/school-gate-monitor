"""
Dev/test-only endpoints — FOR AUTOMATED TESTING ONLY.
Must be secured or removed before production deployment.
"""
from datetime import datetime
from fastapi import APIRouter

from app.cv.pipeline import get_pipeline

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/trigger-test-alert")
def trigger_test_alert(
    violation_type: str = "NO_HELMET",
    plate_read: str = "TEST123",
):
    """
    Push a fake violation alert into the WebSocket queue.
    Only for automated testing — does NOT log to DB.
    Requires any authenticated user.
    """
    try:
        pipeline = get_pipeline()
        alert = {
            "type": "violation",
            "violation_type": violation_type,
            "plate_read": plate_read,
            "plate_matched": None,
            "timestamp": datetime.now().isoformat(),
        }
        pipeline._alert_queue.put(alert)
        return {"ok": True, "alert": alert}
    except Exception as e:
        return {"ok": False, "error": str(e)}
