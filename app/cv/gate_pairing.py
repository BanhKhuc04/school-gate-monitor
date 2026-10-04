"""Pair a front-camera vehicle event with the plate another camera confirmed
at (nearly) the same moment.

Only valid at a single-file gate: one vehicle passes at a time, so the plate a
rear camera confirms inside the window belongs to the vehicle the front camera
saw. Two different plates inside the window means two vehicles: never guess.
Misreads of one plate (89F123792 / 89F123192) count as the same plate.

Two ways to pair, strongest first:
  1. Shared gate line. Each camera draws the same physical line on its own
     image; the rear camera reports when a PLATE crosses it. The front event
     takes the plate whose crossing is within LINE_WINDOW_SEC of its own
     vehicle crossing, after removing the learned camera offset (stream
     latency + where each line was drawn), median of recent unique pairs.
     Once the rear camera reports crossings, only this rule is used, so a
     plate seen seconds earlier or later can no longer be attached.
  2. Fallback (rear line not drawn / never fires): any plate the rear camera
     confirmed within WINDOW_SEC.
"""
import difflib
import os
import statistics
import threading
import time
from collections import deque

WINDOW_SEC = max(1.0, float(os.environ.get('PAIRING_WINDOW_SEC', '8')))
LINE_WINDOW_SEC = max(.5, float(os.environ.get('PAIRING_LINE_WINDOW_SEC', '2.5')))
PAIRING_WAIT_SEC = max(0., float(os.environ.get('PAIRING_WAIT_SEC', '2.0')))
SAME_PLATE_SIMILARITY = 0.8
MIN_OFFSET_SAMPLES = 5

_lock = threading.Lock()
_seen = {}       # (gate_id, plate) -> [first_ts, last_ts, observations, best_confidence]
_crossings = {}  # (gate_id, plate) -> {crossing_ts: confidence}
_waiting = []    # [deadline_ts, event_ts, event_gate, callback]
_deltas = deque(maxlen=21)  # rear crossing - front crossing, unique pairs only
_events = deque(maxlen=64)  # (gate_id, event_ts) of vehicle crossings needing a plate


def reset():
    with _lock:
        _seen.clear()
        _crossings.clear()
        _waiting.clear()
        _deltas.clear()
        _events.clear()


def record_event(gate_id, event_ts):
    """A vehicle crossing on a camera that cannot see plates (learning input)."""
    with _lock:
        _events.append((gate_id, event_ts))


def wait_budget():
    """How long a front event should wait for the rear plate crossing."""
    return min(WINDOW_SEC, max(PAIRING_WAIT_SEC, offset() + LINE_WINDOW_SEC))


def _learn(gate_id, plate, crossing_ts):
    """One vehicle event and one plate crossing near each other -> a delay sample."""
    events = [ts for g, ts in _events if g != gate_id and abs(crossing_ts - ts) <= WINDOW_SEC]
    if len(events) != 1:
        return
    others = {p for (g, p), times in _crossings.items() if g == gate_id
              and any(abs(t - events[0]) <= WINDOW_SEC for t in times)}
    if len(_clusters(others, len)) == 1:
        _deltas.append(crossing_ts - events[0])


def offset():
    """Learned rear-minus-front crossing delay (0 until enough unique pairs)."""
    return statistics.median(_deltas) if len(_deltas) >= MIN_OFFSET_SAMPLES else 0.0


def _clusters(plates, weight):
    groups = []
    for plate in sorted(plates, key=weight, reverse=True):
        for group in groups:
            if difflib.SequenceMatcher(None, plate, group[0]).ratio() >= SAME_PLATE_SIMILARITY:
                group.append(plate)
                break
        else:
            groups.append([plate])
    return groups


def _decide(event_ts, event_gate):
    """(plate, confidence, status, method); status paired / ambiguous / none."""
    other = {(g, p): c for (g, p), c in _crossings.items() if g != event_gate}
    wide = {}
    for (gate, plate), times in other.items():
        for ts, conf in times.items():
            if abs(ts - event_ts) <= WINDOW_SEC:
                wide.setdefault(plate, []).append((ts, conf))
    if wide:  # the rear camera reports line crossings: use only those
        target = event_ts + offset()
        close = {p: [(t, c) for t, c in v if abs(t - target) <= LINE_WINDOW_SEC] for p, v in wide.items()}
        close = {p: v for p, v in close.items() if v}
        if not close:
            return None, 0.0, 'none', 'line'
        groups = _clusters(close, lambda p: (len(close[p]), max(c for _, c in close[p])))
        if len(groups) > 1:
            return None, 0.0, 'ambiguous', 'line'
        best = groups[0][0]
        return best, max(c for _, c in close[best]), 'paired', 'line'
    near = {plate: span for (gate, plate), span in _seen.items()
            if gate != event_gate and span[0] - WINDOW_SEC <= event_ts <= span[1] + WINDOW_SEC}
    if not near:
        return None, 0.0, 'none', 'window'
    groups = _clusters(near, lambda p: near[p][2])
    if len(groups) > 1:
        return None, 0.0, 'ambiguous', 'window'
    best = groups[0][0]  # most observed spelling of the one plate
    return best, near[best][3], 'paired', 'window'


def pair(event_ts, event_gate):
    with _lock:
        return _decide(event_ts, event_gate)[:3]


def pair_detail(event_ts, event_gate):
    """Like pair() plus how it was paired ('line' or 'window')."""
    with _lock:
        return _decide(event_ts, event_gate)


def wait_for_plate(event_ts, event_gate, callback):
    """Call callback(plate, confidence, status) once a plate arrives in the
    window (or it turns ambiguous). Expires silently after the window."""
    with _lock:
        _waiting.append([event_ts + WINDOW_SEC, event_ts, event_gate, callback])


def record_plate(gate_id, plate, confidence=0.0, ts=None, crossing_ts=None):
    """crossing_ts: wall time this plate's track crossed the camera's gate line."""
    ts = time.time() if ts is None else ts
    ready = []
    with _lock:
        if crossing_ts is not None:
            times = _crossings.setdefault((gate_id, plate), {})
            new = crossing_ts not in times
            times[crossing_ts] = max(confidence, times.get(crossing_ts, 0.0))
            if new:
                _learn(gate_id, plate, crossing_ts)
            for key in [k for k, v in _crossings.items() if ts - max(v) > 10 * WINDOW_SEC]:
                del _crossings[key]
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
            text, conf, status, _ = _decide(event_ts, event_gate)
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
