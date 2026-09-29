"""
Verify correlation ghép ĐÚNG: chèn 2 violation cùng biển số, cách nhau 5s,
gate khác nhau, rồi trigger correlation thật (như pipeline sẽ làm).

Verify 2 case:
1. Plate giống hệt → status='matched'
2. Plate lệch 1 ký tự, ratio~0.875 ≥ 0.85 → status='needs_review'
"""
import datetime
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.db import init_db, add_violation_event, get_connection


def main():
    # Dùng DB test riêng
    test_db = Path(__file__).parent.parent / "data" / "_verify_step3.db"
    test_db.unlink(missing_ok=True)
    import app.db
    app.db.DB_PATH = str(test_db)
    init_db()

    ts = datetime.datetime.now().isoformat()

    # Case 1: plate giống hệt → matched
    e1_main = add_violation_event(
        timestamp=ts, plate_read="29A12345", plate_matched="29A12345",
        helmet_status="no_helmet", violation_type="NO_HELMET", gate_id="main",
    )
    e1_sec = add_violation_event(
        timestamp=ts, plate_read="29A12345", plate_matched="29A12345",
        helmet_status="no_helmet", violation_type="NO_HELMET", gate_id="secondary",
    )

    # Case 2: plate lệch 1 ký tự → needs_review
    e2_main = add_violation_event(
        timestamp=ts, plate_read="29A12346", plate_matched="29A12346",  # lệch 1
        helmet_status="no_helmet", violation_type="NO_HELMET", gate_id="main",
    )
    e2_sec = add_violation_event(
        timestamp=ts, plate_read="29A12345", plate_matched="29A12345",
        helmet_status="no_helmet", violation_type="NO_HELMET", gate_id="secondary",
    )

    # Case 3: plate khác hẳn → không ghép
    e3_main = add_violation_event(
        timestamp=ts, plate_read="29A12345", plate_matched="29A12345",
        helmet_status="no_helmet", violation_type="NO_HELMET", gate_id="main",
    )
    e3_sec = add_violation_event(
        timestamp=ts, plate_read="50B99999", plate_matched="50B99999",
        helmet_status="no_helmet", violation_type="NO_HELMET", gate_id="secondary",
    )

    # Trigger correlation cho từng event (giả lập pipeline._try_correlate)
    from app.cv.event_correlator import find_correlation_candidate
    from app.db import find_correlation_candidates, link_violation_events

    results = {}
    for case_name, new_id in [("case1_matched", e1_sec), ("case2_needs_review", e2_sec), ("case3_unmatched", e3_sec)]:
        new_event = {
            "id": new_id, "gate_id": "secondary",
            "timestamp": ts,
            "plate_read": dict(get_connection().execute(
                "SELECT plate_read, plate_matched, status FROM violation_events WHERE id=?", (new_id,)
            ).fetchone()) if False else None,  # workaround — fetch sau
        }
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT plate_read, plate_matched, status FROM violation_events WHERE id=?", (new_id,)
            ).fetchone()
            new_event.update(dict(row))
        finally:
            conn.close()

        candidates = find_correlation_candidates(new_event, window_sec=15)
        best, status = find_correlation_candidate(new_event, candidates, min_similarity=0.85)
        if best is not None:
            ok = link_violation_events(new_id, best["id"], status=status)
            results[case_name] = {
                "linked": ok, "best_id": best["id"], "correlation_status": status,
                "candidates_count": len(candidates),
            }
        else:
            results[case_name] = {
                "linked": False, "best_id": None, "correlation_status": status,
                "candidates_count": len(candidates),
            }

    print(json.dumps(results, indent=2, ensure_ascii=False))

    # Cleanup
    test_db.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
