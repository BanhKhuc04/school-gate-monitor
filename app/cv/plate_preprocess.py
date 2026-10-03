"""Bounded OpenCV transforms for an already detected plate crop."""
import cv2
import numpy as np


def rectify_plate(crop: np.ndarray) -> np.ndarray:
    """Find a plausible plate perimeter among the five largest edge contours.

    Missing/ambiguous borders leave the source intact. A character box or a
    small background rectangle must never define the perspective transform.
    """
    if crop is None or crop.size == 0 or crop.dtype != np.uint8:
        return crop
    h, w = crop.shape[:2]
    if min(h, w) < 20:
        return crop
    scale = min(1., 640 / max(h, w))
    small = cv2.resize(crop, (round(w * scale), round(h * scale)))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
    smooth = cv2.bilateralFilter(gray, 9, 60, 60)
    if int(smooth.max()) - int(smooth.min()) < 15:
        return crop
    edges = cv2.Canny(smooth, 30, 150)
    # A crop can cut the rim, leaving Canny contours open. A light plate panel
    # supplies a second closed contour without inventing corners from text.
    _, panel = cv2.threshold(smooth, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    masks = (edges, panel)
    for mask in masks:
        points = _plate_quad(mask)
        if points is not None:
            break
    else:
        return crop
    center = points.mean(axis=0)
    lengths = np.linalg.norm(points - np.roll(points, -1, axis=0), axis=1)
    width, height = max(lengths[0], lengths[2]), max(lengths[1], lengths[3])
    # A tiny margin protects the rim and characters close to the boundary.
    points = (center + (points-center)*1.025) / scale
    width, height = width * 1.025 / scale, height * 1.025 / scale
    output_scale = min(1., 960 / max(width, height))
    width, height = round(width*output_scale), round(height*output_scale)
    target = np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
    transform = cv2.getPerspectiveTransform(points.astype(np.float32), target)
    return cv2.warpPerspective(crop, transform, (width, height),
                               flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


def _plate_quad(gray):
    contours, _ = cv2.findContours(gray, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    area = gray.size
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if not .18 * area <= cv2.contourArea(contour) <= .98 * area:
            continue
        quad = cv2.approxPolyDP(contour, .035 * cv2.arcLength(contour, True), True)
        if len(quad) != 4 or not cv2.isContourConvex(quad):
            continue
        points = quad[:, 0].astype(np.float32)
        if np.any(np.ptp(points, axis=0) < np.array([gray.shape[1], gray.shape[0]]) * [.5, .4]):
            continue
        center = points.mean(axis=0)
        if np.any(np.abs(center - [gray.shape[1]/2, gray.shape[0]/2]) >
                  np.array([gray.shape[1], gray.shape[0]]) * .2):
            continue
        # Order clockwise from top-left, avoiding duplicate corners on ties.
        angles = np.arctan2(points[:, 1]-center[1], points[:, 0]-center[0])
        points = points[np.argsort(angles)]
        points = np.roll(points, -np.argmin(points.sum(axis=1)), axis=0)
        lengths = np.linalg.norm(points - np.roll(points, -1, axis=0), axis=1)
        if lengths.min() < 12 or min(lengths[0], lengths[2])/max(lengths[0], lengths[2]) < .5 or min(lengths[1], lengths[3])/max(lengths[1], lengths[3]) < .5:
            continue
        width, height = max(lengths[0], lengths[2]), max(lengths[1], lengths[3])
        if not .8 <= width / height <= 6.5:
            continue
        return points
    return None


def enhance_plate(crop: np.ndarray, mode: str = 'contrast') -> np.ndarray:
    """Enlarge, denoise gently, then optionally improve local contrast/binarize.

    These operations preserve observed strokes; they do not reconstruct lost
    characters. Limit both enlargement and maximum output size for the worker.
    """
    h, w = crop.shape[:2]
    scale = min(3., max(1., 240 / max(1, w)), 960 / max(h, w))
    image = cv2.resize(crop, (max(1, round(w*scale)), max(1, round(h*scale))),
                       interpolation=cv2.INTER_CUBIC if scale >= 1 else cv2.INTER_AREA)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    if gray.dtype != np.uint8:
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    gray = cv2.bilateralFilter(gray, 5, 25, 25)
    if mode != 'gray':
        gray = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(gray)
    if mode == 'binary':
        gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 21, 7)
    elif mode == 'contrast':
        gray = cv2.addWeighted(gray, 1.15, cv2.GaussianBlur(gray, (3, 3), 0), -.15, 0)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
