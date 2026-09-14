"""Find nested visual containers in the captured pixels, independent of toolkit."""
import cv2
import numpy as np


def detect_regions(png):
    image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return []
    height, width = image.shape[:2]
    ratio = min(1, 1600 / max(width, height))
    small = cv2.resize(image, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 30, 90)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    # Flat panels can lack a complete border; thresholded surfaces supplement
    # edge contours. Keep enclosing rectangles at several contrast levels.
    masks = [edges]
    for level in (32, 64, 96, 128, 160, 192, 224, 245):
        masks.append(cv2.threshold(gray, level, 255, cv2.THRESH_BINARY)[1])
    candidates = []
    for mask in masks:
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < max(32, 36 * ratio) or h < max(20, 24 * ratio):
                continue
            if w * h > small.shape[0] * small.shape[1] * .98:
                continue
            if abs(cv2.contourArea(contour)) / (w * h) < .72:
                continue
            rect = (round(x / ratio), round(y / ratio), round(w / ratio), round(h / ratio))
            if any(max(abs(a - b) for a, b in zip(rect, old)) <= 5 / ratio for old in candidates):
                continue
            candidates.append(rect)
    candidates.sort(key=lambda r: r[2] * r[3], reverse=True)
    return [{'x': x / width, 'y': y / height, 'width': min(w, width - x) / width,
             'height': min(h, height - y) / height} for x, y, w, h in candidates[:500]]
