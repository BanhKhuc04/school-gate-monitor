"""Geometry checks use real pixels; OCR selection tests stub only the engine."""
import cv2
import numpy as np
import pytest

from app.cv import ocr


def plate_scene(angle=20):
    plate = np.full((90, 210, 3), 235, np.uint8)
    cv2.rectangle(plate, (3, 3), (206, 86), (15, 15, 15), 2)
    cv2.putText(plate, '59H12345', (15, 58), cv2.FONT_HERSHEY_SIMPLEX,
                .8, (20, 20, 20), 2, cv2.LINE_AA)
    center = (150, 100)
    quad = cv2.boxPoints((center, (210, 90), angle)).astype(np.float32)
    source = np.float32([[0, 0], [209, 0], [209, 89], [0, 89]])
    # boxPoints has its own order; use a known clockwise perimeter here.
    start = np.argmin(quad.sum(axis=1))
    quad = np.roll(quad, -start, axis=0)
    matrix = cv2.getPerspectiveTransform(source, quad)
    scene = cv2.warpPerspective(plate, matrix, (300, 200),
                                borderValue=(35, 35, 35))
    return scene


@pytest.mark.parametrize('angle', [-20, 20, 30])
def test_rectification_flattens_twenty_degree_plate_without_mutating_source(angle):
    from app.cv.plate_preprocess import rectify_plate
    scene = plate_scene(angle)
    saved = scene.copy()
    rectified = rectify_plate(scene)
    assert np.array_equal(scene, saved)
    assert 2.0 < rectified.shape[1] / rectified.shape[0] < 2.8
    # The horizontal plate border is now near horizontal, rather than 20 deg.
    edges = cv2.Canny(cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY), 30, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 35,
                           minLineLength=rectified.shape[1] * .65,
                           maxLineGap=10)
    assert lines is not None
    assert any(abs(y2 - y1) <= 3 for [[x1, y1, x2, y2]] in lines)


@pytest.mark.parametrize('shape', [(70, 120), (70, 120, 3)])
def test_no_plate_boundary_keeps_original_geometry(shape):
    from app.cv.plate_preprocess import rectify_plate
    image = np.full(shape, 100, np.uint8)
    assert np.array_equal(rectify_plate(image), image)


def test_small_character_rectangle_is_not_used_as_plate_boundary():
    from app.cv.plate_preprocess import rectify_plate
    image = np.full((100, 180, 3), 220, np.uint8)
    cv2.rectangle(image, (60, 35), (80, 65), (0, 0, 0), 2)
    assert np.array_equal(rectify_plate(image), image)


def test_perspective_plate_becomes_rectangle():
    from app.cv.plate_preprocess import rectify_plate
    image = np.full((170, 280, 3), 30, np.uint8)
    quad = np.int32([[25, 25], [255, 55], [220, 145], [45, 130]])
    cv2.fillConvexPoly(image, quad, (240, 240, 240))
    cv2.polylines(image, [quad], True, (0, 0, 0), 2)
    result = rectify_plate(image)
    assert result.shape[0] < image.shape[0]
    assert result.shape[1] / result.shape[0] > 1.8
    assert result[result.shape[0] // 2, result.shape[1] // 2].mean() > 200


def test_preprocessing_is_bounded_and_handles_gray_input():
    from app.cv.plate_preprocess import enhance_plate
    gray = np.tile(np.arange(100, 150, dtype=np.uint8), (30, 1))
    saved = gray.copy()
    enhanced = enhance_plate(gray)
    assert enhanced.dtype == np.uint8 and enhanced.ndim == 3
    assert max(enhanced.shape[:2]) <= 960
    assert np.array_equal(gray, saved)


def test_conflicting_valid_variants_are_not_accepted(monkeypatch):
    crop = np.full((50, 240, 3), 120, np.uint8)
    results = iter([
        {'full': '59H12345', 'top_line': '59H12345', 'bottom_line': '', 'confidence': .5},
        {'full': '59H12346', 'top_line': '59H12346', 'bottom_line': '', 'confidence': .95},
    ])
    monkeypatch.setattr(ocr, '_get_reader', lambda: object())
    monkeypatch.setattr(ocr, '_read_prepared_plate', lambda *_: next(results))
    monkeypatch.setattr(ocr, 'plate_variants', lambda _: iter([
        ('original', crop), ('contrast', crop),
    ]))
    result = ocr.read_plate_detailed(crop)
    assert result['confidence'] == 0
    assert result['needs_review'] is True


def test_confident_first_read_does_not_run_extra_ocr(monkeypatch):
    crop = np.full((50, 240, 3), 120, np.uint8)
    calls = []
    def read(*_):
        calls.append(1)
        return {'full': '59H12345', 'top_line': '59H12345',
                'bottom_line': '', 'confidence': .95}
    monkeypatch.setattr(ocr, '_get_reader', lambda: object())
    monkeypatch.setattr(ocr, '_read_prepared_plate', read)
    result = ocr.read_plate_detailed(crop)
    assert result['full'] == '59H12345' and len(calls) == 1


def test_a_single_confident_enhancement_requires_review(monkeypatch):
    crop = np.full((50, 240, 3), 120, np.uint8)
    results = iter([
        {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0},
        {'full': '59H12345', 'top_line': '59H12345', 'bottom_line': '', 'confidence': .99},
        {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0},
        {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0},
    ])
    monkeypatch.setattr(ocr, '_get_reader', lambda: object())
    monkeypatch.setattr(ocr, '_read_prepared_plate', lambda *_: next(results))
    result = ocr.read_plate_detailed(crop)
    assert result['full'] == '59H12345'
    assert result['confidence'] == 0 and result['needs_review']
    assert result['preprocessing_attempts'] == 2


def test_variants_do_not_raise_the_engine_confidence(monkeypatch):
    crop = np.full((50, 240, 3), 120, np.uint8)
    monkeypatch.setattr(ocr, '_get_reader', lambda: object())
    monkeypatch.setattr(ocr, '_read_prepared_plate', lambda *_: {
        'full': '59H12345', 'top_line': '59H12345', 'bottom_line': '', 'confidence': .6,
    })
    result = ocr.read_plate_detailed(crop)
    assert result['confidence'] == .6
    assert result['preprocessing_attempts'] == 2
