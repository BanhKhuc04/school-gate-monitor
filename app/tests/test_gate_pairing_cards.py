"""Front-camera live cards show the plate the rear camera confirmed at the
same moment (Vietnamese motorbikes have no front plate)."""
from datetime import datetime, timezone

import pytest

from app.cv import gate_pairing


@pytest.fixture(autouse=True)
def clean():
    gate_pairing.reset()
    yield
    gate_pairing.reset()


def card(ts, state='missing', vehicle=8, kind=None):
    c = {'vehicle_track_id': vehicle, 'last_seen': datetime.fromtimestamp(ts, timezone.utc).isoformat(),
         'plate': {'state': state, 'text': '', 'association': 'unverified'}, 'reasons': []}
    if kind:
        c['kind'] = kind
    return c


def test_front_card_gets_rear_plate_seen_at_the_same_time():
    gate_pairing.record_plate('secondary', '89F123792', .9, ts=1000)
    cards = gate_pairing.annotate_cards([card(1003)], 'main')
    assert cards[0]['plate']['state'] == 'paired'
    assert cards[0]['plate']['text'] == '89F123792'
    assert cards[0]['plate']['association'] == 'paired_camera'


def test_two_rear_plates_in_window_is_never_guessed():
    gate_pairing.record_plate('secondary', '89F123792', .9, ts=1000)
    gate_pairing.record_plate('secondary', '30A12345', .9, ts=1001)
    cards = gate_pairing.annotate_cards([card(1002)], 'main')
    assert cards[0]['plate']['state'] == 'missing'
    assert 'plate_pairing_ambiguous' in cards[0]['reasons']


def test_no_pairing_outside_window_without_vehicle_or_own_plate():
    gate_pairing.record_plate('secondary', '89F123792', .9, ts=1000)
    far = card(1000 + gate_pairing.WINDOW_SEC + 5)
    no_bike = card(1001, vehicle=None)
    own = card(1001, state='confirmed')
    plate_only = card(1001, kind='plate')
    gate_pairing.annotate_cards([far, no_bike, own, plate_only], 'main')
    assert [c['plate']['state'] for c in (far, no_bike, own, plate_only)] == ['missing', 'missing', 'confirmed', 'missing']


def test_own_gate_plates_are_not_paired_with_itself():
    gate_pairing.record_plate('main', '89F123792', .9, ts=1000)
    assert gate_pairing.annotate_cards([card(1001)], 'main')[0]['plate']['state'] == 'missing'
