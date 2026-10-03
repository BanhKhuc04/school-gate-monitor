"""Exercise real pipeline behavior, not a copied legacy decision function."""
from app.tests.test_vehicle_gate import pipeline, feed


def test_riding_with_helmet_requires_crossing(pipeline):
    from types import SimpleNamespace
    feed(pipeline,helmet_dets=[SimpleNamespace(class_name='With Helmet')],crossed_gate=True)
    assert pipeline.db_insert.call_args.kwargs['violation_type']=='RIDING_THROUGH_GATE'


def test_standing_with_helmet_is_not_riding_violation(pipeline):
    from types import SimpleNamespace
    feed(pipeline,helmet_dets=[SimpleNamespace(class_name='With Helmet')],posture_status='standing',crossed_gate=True)
    pipeline.db_insert.assert_not_called()


def test_riding_evidence_accumulates_before_crossing_and_fires_on_the_crossing_frame(pipeline):
    """Riding evidence builds up continuously WHILE still approaching the gate
    (crossed_gate=False) — it must already be ready the instant the bike
    actually crosses, firing on that SAME frame instead of needing another
    full batch of post-crossing frames to re-confirm."""
    from types import SimpleNamespace
    feed(pipeline, helmet_dets=[SimpleNamespace(class_name='With Helmet')],
         crossed_gate=False, count=4)
    pipeline.db_insert.assert_not_called()
    feed(pipeline, helmet_dets=[SimpleNamespace(class_name='With Helmet')],
         crossed_gate=True, count=1)
    assert pipeline.db_insert.call_args.kwargs['violation_type'] == 'RIDING_THROUGH_GATE'
