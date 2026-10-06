"""Decode character boxes on ONE crop; runtime version of scripts/plate_char_tools.py.

Loaded at runtime by app.cv.char_plate_reader when CHAR_PLATE_READER_REVIEW_ONLY
is enabled. The scripts/ copy stays for offline training/eval workflows and
is kept identical in behaviour.
"""
import numpy as np

CHARACTERS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def confirmed_character_plate(result, min_confidence=.70):
    # Character classes are literal observations. Do not apply EasyOCR's
    # positional substitutions to invent a missing letter/number.
    from app.cv.ocr import validate_plate_format
    full = result.get('full', '')
    return full if (not result.get('error')
                    and result.get('confidence', 0) >= min_confidence
                    and validate_plate_format(full)) else ''


def decode_characters(boxes):
    """Input: class, normalized center x/y, width/height, confidence."""
    if not boxes:
        return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0}
    selected = []
    # Across-class NMS keeps both labels. A weak duplicate is not competing
    # evidence; close confidence scores still refuse recognition.
    for b in sorted(boxes, key=lambda b: b[5], reverse=True):
        duplicate = False
        for a in selected:
            ix = max(0, min(a[1]+a[3]/2, b[1]+b[3]/2) - max(a[1]-a[3]/2, b[1]-b[3]/2))
            iy = max(0, min(a[2]+a[4]/2, b[2]+b[4]/2) - max(a[2]-a[4]/2, b[2]-b[4]/2))
            inter = ix * iy
            union = a[3]*a[4] + b[3]*b[4] - inter
            if union and inter/union > .4:
                if a[0] != b[0] and a[5] - b[5] < .20:
                    return {'full': '', 'top_line': '', 'bottom_line': '',
                            'confidence': 0., 'error': 'ambiguous_characters'}
                duplicate = True
                break
        if not duplicate:
            selected.append(b)
    items = sorted(selected, key=lambda b: b[2])
    gaps = [items[i+1][2] - items[i][2] for i in range(len(items)-1)]
    if gaps and max(gaps) > .60 * np.median([b[4] for b in items]):
        split = int(np.argmax(gaps)) + 1
    else:
        split = len(items)
    top = sorted(items[:split], key=lambda b: b[1])
    bottom = sorted(items[split:], key=lambda b: b[1])

    def text(row):
        return ''.join(CHARACTERS[int(b[0])] for b in row)

    return {
        'full': text(top) + text(bottom),
        'top_line': text(top),
        'bottom_line': text(bottom),
        'confidence': float(min(b[5] for b in items)) if items else 0.0,
        'character_count': len(items),
    }


def read_char_crop(model, crop, device=0, imgsz=320, conf=.25):
    """Run the YOLO model on a single crop. Caller must ensure crop is BGR numpy."""
    result = model.predict(crop, imgsz=imgsz, device=device, conf=conf, iou=.45,
                           agnostic_nms=False, verbose=False)[0]
    xy = result.boxes.xywhn.cpu().tolist()
    classes = result.boxes.cls.cpu().tolist()
    scores = result.boxes.conf.cpu().tolist()
    return decode_characters([(int(c), *b, float(s)) for c, b, s in zip(classes, xy, scores)])
