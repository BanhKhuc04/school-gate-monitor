"""Freeze a vehicle crossing into one event and one short audio message."""
import re
from copy import deepcopy


def spoken_plate(plate):
    match = re.fullmatch(r'(\d{2})([A-Z]\d?|[A-Z]{2})(\d{4,5})', plate or '')
    if not match:
        return ''
    province, series, number = match.groups()
    return f'{province} {series} {number[:-2]} {number[-2:]}'


def build_alert_message(plate, issues):
    codes = {i['code'] for i in issues if i.get('status') == 'confirmed'}
    reminders = []
    helmet, riding = 'NO_HELMET' in codes, 'RIDING_THROUGH_GATE' in codes
    if helmet and riding:
        reminders.append('Không đội mũ, vui lòng dắt xe.')
    elif helmet:
        reminders.append('Vui lòng đội mũ.')
    elif riding:
        reminders.append('Vui lòng dắt xe.')
    for code, text in [('MISSING_MIRROR', 'Mời kiểm tra gương trái.'),
                       ('TOO_MANY_RIDERS', 'Mời kiểm tra số người trên xe.'),
                       ('PLATE_NOT_REGISTERED', 'Mời kiểm tra đăng ký xe.')]:
        if code in codes:
            reminders.append(text)
    unreadable = 'PLATE_UNREADABLE' in codes
    if not reminders and not unreadable:
        return ''
    prefix = spoken_plate(plate)
    if prefix:
        prefix += '.'
    elif unreadable:
        prefix = 'Không đọc được biển số.'
    return ' '.join(([prefix] if prefix else []) + reminders)


def aggregate_crossing_event(vehicle_track_id, crossing_event_id, issues, plate_result,
                             plate_expected=True):
    """plate_expected=False: this camera cannot see the plate (a front camera;
    Vietnamese motorbikes carry rear plates only), so an unread plate is a
    review note, never a violation or a spoken alert on its own."""
    issues = deepcopy(issues)
    plate = plate_result.text if plate_result and plate_result.is_confident else ''
    if not plate:
        technical_error = getattr(plate_result, 'error', None)
        issues.append({'code': 'PLATE_UNREADABLE',
            'status': 'needs_review' if technical_error or not plate_expected else 'confirmed',
            'reason': technical_error or ('plate_not_visible_from_camera' if not plate_expected else
                      'ocr_deadline' if getattr(plate_result, 'pending', False) else 'full_plate_not_read'),
            'sample_count': getattr(plate_result, 'sample_count', 0)})
    issues = list({i['code']: i for i in issues}.values())
    return {'vehicle_track_id': vehicle_track_id, 'crossing_event_id': crossing_event_id,
            'alert_finalized': True, 'plate_status': 'CONFIRMED' if plate else 'ERROR' if getattr(plate_result, 'error', None) else 'UNREADABLE',
            'plate_read': plate, 'issues': issues, 'audio_message': build_alert_message(plate, issues)}
