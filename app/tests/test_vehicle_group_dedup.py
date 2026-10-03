"""Two riders on the SAME motorcycle used to create two independent groups
(one per person) that each independently confirmed vehicle-level violations
(RIDING_THROUGH_GATE, TOO_MANY_RIDERS, PLATE_NOT_REGISTERED) for the same
physical crossing — double DB rows, double alerts. `primary_rider=False`
(set for every non-driver group sharing a vehicle, see VideoPipeline._run_loop)
excludes those vehicle-level codes from that group's evidence, while leaving
NO_HELMET — a per-person fact — unaffected.
"""
from types import SimpleNamespace
from app.tests.test_vehicle_gate import pipeline, feed


def test_non_primary_rider_does_not_confirm_riding_through_gate(pipeline):
    feed(pipeline, helmet_dets=[SimpleNamespace(class_name='With Helmet')],
         crossed_gate=True, primary_rider=False, track_id=8)
    pipeline.db_insert.assert_not_called()


def test_primary_rider_still_confirms_riding_through_gate(pipeline):
    feed(pipeline, helmet_dets=[SimpleNamespace(class_name='With Helmet')],
         crossed_gate=True, primary_rider=True, track_id=7)
    assert pipeline.db_insert.call_args.kwargs['violation_type'] == 'RIDING_THROUGH_GATE'


def test_non_primary_rider_still_confirms_their_own_no_helmet(pipeline):
    """NO_HELMET is per-person, not per-vehicle — a passenger without a
    helmet must still be flagged even though they aren't the 'primary' rider."""
    feed(pipeline, helmet_dets=[SimpleNamespace(class_name='Without Helmet')],
         crossed_gate=True, primary_rider=False, track_id=8)
    assert pipeline.db_insert.call_args.kwargs['violation_type'] == 'NO_HELMET'
