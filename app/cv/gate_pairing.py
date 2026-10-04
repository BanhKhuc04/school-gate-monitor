"""Pair a front-camera vehicle event with the plate another camera confirmed
at (nearly) the same moment.

Only valid at a single-file gate: one vehicle passes at a time, so the plate a
rear camera confirms inside the window belongs to the vehicle the front camera
saw. Two different plates inside the window means two vehicles: never guess.
Misreads of one plate (89F123792 / 89F123192) count as the same plate.
"""
import difflib
import os
import threading
import time

WINDOW_SEC = max(1.0, float(os.environ.get('PAIRING_WINDOW_SEC', '8')))
SAME_PLATE_SIMILARITY = 0.8

_lock = threading.Lock()
_seen = {}     # (gate_id, plate) -> [first_ts, last_ts, observations, best_confidence]
_waiting = []  # [deadline_ts, event_ts, event_gate, callback]


def reset():
    with _lock:
        _seen.clear()
        _waiting.clear()


def _decide(event_ts, event_gate):
    """(plate, confidence, status) with status in paired / ambiguous / none."""
    near = {plate: span for (gate, plate), span in _seen.items()
            if gate != event_gate and span[0] - WINDOW_SEC <= event_ts <= span[1] + WINDOW_SEC}
    if not near:
        return None, 0.0, 'none'
    clusters = []
    for plate in sorted(near, key=lambda p: -near[p][2]):
        for cluster in clusters:
            if difflib.SequenceMatcher(None, plate, cluster[0]).ratio() >= SAME_PLATE_SIMILARITY:
                cluster.append(plate)
                break
        else:
            clusters.append([plate])
    if len(clusters) > 1:
        return None, 0.0, 'ambiguous'
    best = clusters[0][0]  # most observed spelling of the one plate
    return best, near[best][3], 'paired'


def pair(event_ts, event_gate):
    with _lock:
        return _decide(event_ts, event_gate)


def wait_for_plate(event_ts, event_gate, callback):
    """Call callback(plate, confidence, status) once a plate arrives in the
    window (or it turns ambiguous). Expires silently after the window."""
    with _lock:
        _waiting.append([event_ts + WINDOW_SEC, event_ts, event_gate, callback])


def record_plate(gate_id, plate, confidence=0.0, ts=None):
    ts = time.time() if ts is None else ts
    ready = []
    with _lock:
        span = _seen.get((gate_id, plate))
        if span is None:
            _seen[(gate_id, plate)] = [ts, ts, 1, confidence]
        else:
            span[0], span[1] = min(span[0], ts), max(span[1], ts)
            span[2] += 1
            span[3] = max(span[3], confidence)
        for key in [k for k, s in _seen.items() if ts - s[1] > 10 * WINDOW_SEC]:
            del _seen[key]
        for entry in list(_waiting):
            deadline, event_ts, event_gate, callback = entry
            if deadline < ts:
                _waiting.remove(entry)
                continue
            if event_gate == gate_id:
                continue
            text, conf, status = _decide(event_ts, event_gate)
            if status != 'none':
                _waiting.remove(entry)
                ready.append((callback, text, conf, status))
    for callback, text, conf, status in ready:
        callback(text, conf, status)


# A card's own camera never saw a plate in these states.
_NO_OWN_PLATE = {'missing', 'reading', 'selecting', 'unreadable', 'review', 'partial'}


def annotate_cards(cards, gate_id):
    """Show the plate another camera confirmed while this vehicle was in view.

    Vietnamese motorbikes carry no front plate, so a front camera's live card
    can only get one this way. Same single-file rule as events: two plates in
    the window means two vehicles, so nothing is shown.
    """
    for card in cards:
        plate = card.get('plate') or {}
        if (card.get('kind') == 'plate' or card.get('vehicle_track_id') is None
                or plate.get('state') not in _NO_OWN_PLATE):
            continue
        try:
            from datetime import datetime
            seen = datetime.fromisoformat(card['last_seen']).timestamp()
        except (KeyError, TypeError, ValueError):
            continue
        text, confidence, status = pair(seen, gate_id)
        if status == 'paired':
            plate.update(state='paired', text=text, association='paired_camera',
                         confidence=round(confidence, 3))
        elif status == 'ambiguous':
            card.setdefault('reasons', []).append('plate_pairing_ambiguous')
    return cards
