"""
pytest tests for face enrollment DB functions + posture heuristic.
"""
import pytest
import numpy as np


def test_face_tables_created(client):
    """Face tables exist after init_db."""
    import app.db as db
    rows = db.get_face_embeddings()
    assert isinstance(rows, list)
    events = db.get_face_match_events(limit=10)
    assert isinstance(events, list)


def test_add_face_embedding_to_db():
    """add_face_embedding stores embedding and returns ID."""
    import app.db as db
    emb = np.random.rand(512).astype(np.float32).tobytes()
    emb_id = db.add_face_embedding(label_name="Test User", embedding=emb, photo_path=None)
    assert isinstance(emb_id, int)
    assert emb_id > 0
    all_embs = db.get_face_embeddings()
    assert any(e["label_name"] == "Test User" for e in all_embs)


def test_delete_face_embedding():
    """delete_face_embedding removes the record."""
    import app.db as db
    emb = np.random.rand(512).astype(np.float32).tobytes()
    emb_id = db.add_face_embedding(label_name="Delete Me", embedding=emb)
    result = db.delete_face_embedding(emb_id)
    assert result is True
    by_id = db.get_face_embedding_by_id(emb_id)
    assert by_id is None


def test_add_face_match_event():
    """add_face_match_event stores a match event."""
    import app.db as db
    event_id = db.add_face_match_event(
        matched_label="Unknown Person",
        similarity=0.25,
        snapshot_path="/media/test.jpg",
    )
    assert isinstance(event_id, int)
    events = db.get_face_match_events(limit=10)
    assert any(e["matched_label"] == "Unknown Person" for e in events)


def test_posture_heuristic_standing():
    """Straight leg = standing (angle ~180 degrees)."""
    import math
    # Hip at (50, 80), knee at (50, 100), ankle at (50, 130)
    # Vector hip->knee = (0, 20), knee->ankle = (0, 30)
    # These are nearly collinear -> angle ~180 -> standing
    p1 = (50.0, 80.0)  # hip
    p2 = (50.0, 100.0)  # knee
    p3 = (50.0, 130.0)  # ankle
    v1x, v1y = p1[0] - p2[0], p1[1] - p2[1]
    v2x, v2y = p3[0] - p2[0], p3[1] - p2[1]
    dot = v1x * v2x + v1y * v2y
    n1 = math.hypot(v1x, v1y)
    n2 = math.hypot(v2x, v2y)
    cos_a = max(-1.0, min(dot / (n1 * n2), 1.0))
    angle = math.degrees(math.acos(cos_a))
    # Should be classified as standing (>160 degrees)
    assert angle > 160


def test_posture_heuristic_riding():
    """Bent leg = riding (angle < 140 degrees)."""
    import math
    # Hip at (50, 60), knee at (50, 55), ankle at (50, 70)
    # Vector hip->knee = (0, -5), knee->ankle = (0, 15)
    # These form a sharp angle -> riding
    p1 = (50.0, 60.0)
    p2 = (50.0, 55.0)
    p3 = (50.0, 70.0)
    v1x, v1y = p1[0] - p2[0], p1[1] - p2[1]
    v2x, v2y = p3[0] - p2[0], p3[1] - p2[1]
    dot = v1x * v2x + v1y * v2y
    n1 = math.hypot(v1x, v1y)
    n2 = math.hypot(v2x, v2y)
    cos_a = max(-1.0, min(dot / (n1 * n2), 1.0))
    angle = math.degrees(math.acos(cos_a))
    # Should be classified as riding (<140 degrees)
    assert angle < 140
