"""Regression cases from the Codex review; no cameras or model loading."""
import pytest
from app.cv.crossing import CrossingDetector


@pytest.mark.parametrize("first_side", [0.3, 0.7])
def test_crossing_requires_three_origin_samples_through_boundary(first_side):
    detector = CrossingDetector([0.2, 0.5, 0.8, 0.5])
    other = 1 - first_side
    points = [first_side, 0.5, other, other, other]
    assert not any(detector.update(1, 0.5, y, 100 + i * 0.2)[1]
                   for i, y in enumerate(points))


def test_crossing_fires_on_first_clear_sample_of_the_new_side():
    """Was 'expires_origin_evidence': the old algorithm reset origin evidence
    after max_crossing_sec and required the NEW side to also stabilize for
    min_frames_per_side before confirming. The current design has no such
    expiry/second-stability-wait — once a side is stable, ONE clear sample on
    the other side crosses immediately (see crossing.py module docstring).

    Phase 4 (Task 1): default constructor uses `min_frames_exit_side=3`
    (3+3 mode). This test now uses the legacy 3+1 mode by passing
    `min_frames_exit_side=1` explicitly to verify the legacy instant-cross
    path remains available. The default 3+3 behavior is covered by
    test_task01_phase4_crossing_finalize.TestCrossing3Plus3Rule."""
    detector = CrossingDetector([0.2, 0.5, 0.8, 0.5], min_frames_exit_side=1)
    points = [(0.3, t) for t in [100, 100.2, 100.4, 101, 102, 103, 104, 105]]
    points += [(0.7, t) for t in [106, 106.2, 106.4]]
    results = [detector.update(1, 0.5, y, t)[1] for y, t in points]
    assert results.count(True) == 1
    assert results[-3] is True  # fires on the very first 0.7 sample (t=106)


def test_encounter_fetch_keeps_class_scope(monkeypatch):
    import sqlite3
    import app.db as db
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE violation_events(id INTEGER PRIMARY KEY, encounter_id TEXT,
            timestamp TEXT, plate_matched TEXT, gate_id TEXT, issues_json TEXT);
        CREATE TABLE registered_vehicles(plate_number TEXT, student_name TEXT,
            student_class TEXT);
        INSERT INTO registered_vehicles VALUES ('A','fixture A','10A1'),('B','fixture B','10B1');
        INSERT INTO violation_events VALUES
            (1,'shared','2026-10-01T08:00:00','A','main','[]'),
            (2,'shared','2026-10-01T08:00:01','B','main','[]');
    ''')
    monkeypatch.setattr(db, 'get_connection', lambda: conn)
    result = db.list_violation_encounters(student_class='10A1')
    assert result['items'][0]['violation_ids'] == [1]


def test_crossing_duplicate_frame_never_counts_as_three():
    detector = CrossingDetector([0.2, 0.5, 0.8, 0.5])
    points = [(0.3,1),(0.3,1),(0.3,1),(0.7,2),(0.7,3),(0.7,4)]
    assert not any(detector.update(1, .5, y, 100+i*.2, frame_seq=seq)[1]
                   for i,(y,seq) in enumerate(points))


def test_crossing_margin_uses_pixel_diagonal_on_wide_frame():
    from app.cv.crossing import Side
    detector=CrossingDetector([0.2,0.5,0.8,0.5])
    # 20 px from a horizontal line, inside 2% of a 1920x1080 diagonal (~44 px).
    side, crossed=detector.update(1,.5,.5+20/1080,100,frame_seq=1,frame_size=(1920,1080))
    assert side == Side.ON
    assert not crossed


@pytest.mark.parametrize('offset,expected_size',[(0,20),(20,20),(200,1)])
def test_encounter_total_and_full_issues_before_pagination(monkeypatch, offset, expected_size):
    import sqlite3, json
    import app.db as db
    conn=sqlite3.connect(':memory:')
    conn.row_factory=sqlite3.Row
    conn.executescript('''
        CREATE TABLE violation_events(id INTEGER PRIMARY KEY, encounter_id TEXT,
          timestamp TEXT, plate_matched TEXT, gate_id TEXT, issues_json TEXT);
        CREATE TABLE registered_vehicles(plate_number TEXT,student_name TEXT,student_class TEXT);
    ''')
    for n in range(201):
        conn.execute('INSERT INTO violation_events VALUES (?,?,?,?,?,?)',
                     (n+1,f'enc-{n:03}', '2026-10-01T08:00:00',None,'main',
                      json.dumps([{'code':'NO_HELMET','status':'confirmed'}])))
    conn.execute('INSERT INTO violation_events VALUES (202,?,?,?,?,?)',
                 ('enc-200','2026-10-01T08:00:00',None,'main',
                  json.dumps([{'code':'PLATE_LOW_CONFIDENCE','status':'deferred'}])))
    conn.commit()
    monkeypatch.setattr(db,'get_connection',lambda:conn)
    result=db.list_violation_encounters(limit=20,offset=offset)
    assert result['total']==201
    assert len(result['items'])==expected_size
    if offset == 0:
        assert result['items'][0]['encounter_id']=='enc-200'
        assert {issue['code'] for issue in result['items'][0]['issues']} == {'NO_HELMET','PLATE_LOW_CONFIDENCE'}
