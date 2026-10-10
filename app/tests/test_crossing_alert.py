from app.cv.crossing_alert import aggregate_crossing_event, build_alert_message


def issue(code):
    return {'code': code, 'status': 'confirmed'}


def test_all_three_faults_are_one_sealed_event():
    result = aggregate_crossing_event(7, 'crossing-1', [issue('NO_HELMET'), issue('RIDING_THROUGH_GATE')], None)
    assert result['vehicle_track_id'] == 7
    assert result['crossing_event_id'] == 'crossing-1'
    assert result['alert_finalized']
    assert {i['code'] for i in result['issues']} == {'NO_HELMET', 'RIDING_THROUGH_GATE', 'PLATE_UNREADABLE'}
    assert result['audio_message'] == 'Không đọc được biển số. Không đội mũ, vui lòng dắt xe.'


def test_full_plate_precedes_helmet_and_riding():
    from app.cv.plate_voter import PlateReadResult
    plate = PlateReadResult(text='89F123792', is_confident=True)
    result = aggregate_crossing_event(7, 'c1', [issue('NO_HELMET'), issue('RIDING_THROUGH_GATE')], plate)
    assert result['audio_message'] == '89 F1 237 92. Không đội mũ, vui lòng dắt xe.'


def test_no_faults_means_no_message_and_technical_failure_is_not_unreadable():
    from app.cv.plate_voter import PlateReadResult
    assert aggregate_crossing_event(7, 'c1', [], PlateReadResult(text='89F123792', is_confident=True))['audio_message'] == ''
    result = aggregate_crossing_event(7, 'c2', [], PlateReadResult(error='engine_failed'))
    assert result['audio_message'] == ''
    assert result['issues'][0]['status'] == 'needs_review'


def test_front_camera_unread_plate_is_review_only_and_silent():
    walked = aggregate_crossing_event(7, 'c1', [], None, plate_expected=False)
    assert walked['issues'] == [{'code': 'PLATE_UNREADABLE', 'status': 'needs_review',
                                 'reason': 'plate_not_visible_from_camera', 'sample_count': 0}]
    assert walked['audio_message'] == ''
    rode = aggregate_crossing_event(7, 'c2', [issue('RIDING_THROUGH_GATE')], None, plate_expected=False)
    assert rode['audio_message'] == 'Vui lòng dắt xe.'


def test_single_unreadable_is_short_and_unknown_issue_is_not_read():
    assert build_alert_message('', [issue('PLATE_UNREADABLE')]) == 'Không đọc được biển số.'
    assert build_alert_message('89F123792', [issue('RIDING_THROUGH_GATE')]) == '89 F1 237 92. Vui lòng dắt xe.'
    assert build_alert_message('89F123792', [issue('NO_HELMET')]) == '89 F1 237 92. Vui lòng đội mũ.'
    assert build_alert_message('', [{'code':'NO_HELMET','status':'conflict'}]) == ''
