"""Sketch understanding: OpenCV proposals + vision-model labelling, merged into a SketchAnalysis.

Modes
- cv:     OpenCV only. Shapes are classified by geometry; handwritten text is located but not read.
- vision: the vision model alone lists components with boxes (no OpenCV proposals).
- hybrid: OpenCV proposes boxes -> the image is annotated with numbered boxes -> the vision model labels
          each numbered box with a component type, reads its handwriting and adds missed components ->
          merge by IoU -> containment tree.
"""
from __future__ import annotations

import base64
import difflib
import re
import time

import cv2
import numpy as np

from .. import config
from . import ir as irm
from . import llm
from . import ocr as ocr_engine
from . import sketch_refine as refine_rules

VISION_TYPES = [t for t in irm.TYPES if t != "page"]
CONTAINERS = irm.CONTAINER_TYPES - {"page"}
WORK_WIDTH = 1000  # sketches are processed at this width
TYPE_COLORS = {  # BGR, for the overlay
    "button": (37, 99, 235), "input": (22, 163, 74), "textarea": (22, 163, 74), "select": (22, 163, 74),
    "heading": (147, 51, 234), "text": (120, 120, 120), "link": (234, 88, 12), "image": (219, 39, 119),
    "checkbox": (13, 148, 136), "radio": (13, 148, 136), "container": (100, 116, 139), "card": (100, 116, 139),
    "form": (100, 116, 139), "navbar": (202, 138, 4), "header": (202, 138, 4), "nav_item": (234, 88, 12),
    "divider": (71, 85, 105), "icon": (190, 18, 60), "list": (100, 116, 139),
}


# --------------------------------------------------------------------------- image utilities

def decode(image_bytes: bytes) -> np.ndarray:
    data = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Unsupported or corrupt image")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:  # transparent canvas exports: composite on white
        alpha = img[:, :, 3:4].astype(np.float32) / 255.0
        img = (img[:, :, :3].astype(np.float32) * alpha + 255.0 * (1 - alpha)).astype(np.uint8)
    return img


def _to_work(img: np.ndarray) -> tuple[np.ndarray, float]:
    h, w = img.shape[:2]
    scale = WORK_WIDTH / w
    if abs(scale - 1) > 0.01:
        img = cv2.resize(img, (WORK_WIDTH, max(1, round(h * scale))),
                         interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    return img, scale


def ink_mask(img: np.ndarray) -> np.ndarray:
    """Binary mask of pen strokes, robust to paper texture / uneven lighting."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Flatten the paper: divide by a heavily dilated+blurred estimate of the background so shadows, vignetting and
    # lighting gradients disappear (pen strokes are thinner than the 25 px window, so they do not enter it).
    background = cv2.GaussianBlur(cv2.dilate(gray, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))), (0, 0), 20)
    gray = np.clip(gray.astype(np.float32) / np.maximum(background.astype(np.float32), 1.0) * 255.0, 0, 255).astype(np.uint8)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Otsu keeps only real ink on clean scans; adaptive handles shading. Require both where Otsu is sane.
    mask = cv2.bitwise_and(adaptive, otsu) if otsu.mean() < 60 else adaptive
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return mask


def _norm(box: tuple[int, int, int, int], w: int, h: int) -> dict:
    x, y, bw, bh = box
    return {"x": round(x / w, 4), "y": round(y / h, 4), "w": round(bw / w, 4), "h": round(bh / h, 4)}


def _px(b: dict, w: int, h: int) -> tuple[int, int, int, int]:
    return int(b["x"] * w), int(b["y"] * h), int(b["w"] * w), int(b["h"] * h)


# --------------------------------------------------------------------------- OpenCV detection

def _shape_candidates(mask: np.ndarray) -> list[dict]:
    """Closed (or nearly closed) outlines from enclosed regions, at two closing strengths:
    a strong close joins gaps in big wobbly boxes, a light one keeps small checkboxes/radios open inside."""
    return _shapes_at(mask, 9) + _shapes_at(mask, 3)


def _shapes_at(mask: np.ndarray, close: int) -> list[dict]:
    h, w = mask.shape
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (close, close)))
    closed = cv2.dilate(closed, np.ones((3, 3), np.uint8), iterations=1)
    contours, hierarchy = cv2.findContours(closed, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    hierarchy = hierarchy[0]
    holes_by_outer: dict[int, list[int]] = {}
    for i, (_, _, _, parent) in enumerate(hierarchy):
        if parent >= 0:
            holes_by_outer.setdefault(parent, []).append(i)

    out = []
    for outer, holes in holes_by_outer.items():
        ox, oy, ow, oh = cv2.boundingRect(contours[outer])
        big_holes = [i for i in holes if cv2.contourArea(contours[i]) > 60]
        if not big_holes:
            continue
        union = sum(cv2.contourArea(contours[i]) for i in big_holes)
        # A rectangle with an X inside: the X splits the hole into ~4 triangles filling the box.
        if len(big_holes) >= 3 and union > 0.45 * ow * oh and ow > 40 and oh > 30:
            tri = [i for i in big_holes if 0.3 < cv2.contourArea(contours[i]) / max(1, np.prod(cv2.boundingRect(contours[i])[2:])) < 0.7]
            if len(tri) >= 3:
                out.append(_cand((ox, oy, ow, oh), "cross_box", 0.85, mask))
                continue
        for i in big_holes:
            area = cv2.contourArea(contours[i])
            x, y, bw, bh = cv2.boundingRect(contours[i])
            if bw < 10 or bh < 10 or area < 120:
                continue
            if max(bw, bh) < 60 and ow * oh > 4 * (bw + 12) * (bh + 12):
                continue  # small loop inside a bigger stroke blob: a letter (o, e, a), not a checkbox/radio
            if bh < 38 and bw > 1.5 * bh and bw >= 30:
                continue  # a wide, short loop is the gap between a word's letters (or under its underline), not a control
            if len(big_holes) > 1 and min(bw, bh) < 24:
                continue  # sliver between two outlines that touch after closing, not a component
            perimeter = cv2.arcLength(contours[i], True)
            circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter else 0
            rectangularity = area / (bw * bh)
            # Grow the hole back to the outline's outer edge (stroke thickness).
            pad = max(2, min(8, int(round(min(ow - bw, oh - bh) / 2)))) if len(big_holes) == 1 else 3
            box = (max(0, x - pad), max(0, y - pad), min(w, bw + 2 * pad), min(h, bh + 2 * pad))
            aspect = bw / bh
            if circularity > 0.78 and 0.75 < aspect < 1.33 and rectangularity < 0.86:
                out.append(_cand(box, "circle", min(0.95, circularity), mask))
            elif rectangularity > 0.72:
                out.append(_cand(box, "rect", round(min(0.95, rectangularity), 3), mask))
    return out


def _open_rects(mask: np.ndarray, known: list[dict]) -> list[dict]:
    """Outlines with a gap too wide to close: large, sparse connected strokes shaped like a box."""
    h, w = mask.shape
    joined = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)
    n, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if bw < 60 or bh < 28 or bw * bh > 0.9 * w * h:
            continue
        x, y, bw, bh = x + 4, y + 4, bw - 8, bh - 8  # undo the dilation growth
        if bh < 32:
            continue  # a word's bounding box, not a field (the smallest drawn fields and buttons are ~40 px tall)
        ink = cv2.countNonZero(mask[y:y + bh, x:x + bw]) / (bw * bh)
        box = {"x": x / w, "y": y / h, "w": bw / w, "h": bh / h}
        if any(irm.iou(box, k["bbox"]) > 0.5 for k in known):
            continue
        inside = sum(k["bbox"]["w"] * k["bbox"]["h"] for k in known if irm.contains(box, k["bbox"], 0.8))
        if inside > 0.25 * box["w"] * box["h"]:
            continue  # neighbouring outlines merged by dilation, not a separate box
        # Edge strokes present on at least 3 sides -> treat as an open rectangle.
        band_v = max(4, min(25, int(bh * 0.35)))  # wobbly strokes: look in a generous band per side
        band_h = max(4, min(25, int(bw * 0.35)))
        sides = [mask[y:y + band_v, x:x + bw], mask[y + bh - band_v:y + bh, x:x + bw],
                 mask[y:y + bh, x:x + band_h], mask[y:y + bh, x + bw - band_h:x + bw]]
        coverage = [(np.count_nonzero(s.max(axis=0 if j < 2 else 1)) / (bw if j < 2 else bh)) for j, s in enumerate(sides)]
        if ink < 0.25 and sum(c > 0.6 for c in coverage) >= 3:
            out.append(_cand((x, y, bw, bh), "rect", 0.55, mask))
    return out


def _cand(box: tuple[int, int, int, int], shape: str, conf: float, mask: np.ndarray) -> dict:
    h, w = mask.shape
    x, y, bw, bh = (int(v) for v in box)
    inner = mask[y + 3:y + bh - 3, x + 3:x + bw - 3]
    fill = float(cv2.countNonZero(inner)) / inner.size if inner.size else 0.0
    return {"bbox": _norm((x, y, bw, bh), w, h), "px": (x, y, bw, bh), "shape": shape, "area": int(bw * bh),
            "aspect": round(bw / max(1, bh), 3), "fill": round(fill, 3), "conf": round(float(conf), 3)}


def _strokes_outside(mask: np.ndarray, shapes: list[dict]) -> np.ndarray:
    """Mask with shape outlines removed, leaving text scribbles, lines and fills.

    Hand-drawn edges wobble and overshoot, so whole connected strokes that lie mostly on an outline band
    are removed (not just the pixels on the ideal rectangle).
    """
    band = np.zeros_like(mask)
    rest = mask.copy()
    for s in shapes:
        x, y, bw, bh = s["px"]
        cv2.rectangle(band, (x, y), (x + bw, y + bh), 255, thickness=22)
        if s["shape"] in ("cross_box", "circle") or (bw < 50 and bh < 50):
            rest[max(0, y - 4):y + bh + 4, max(0, x - 4):x + bw + 4] = 0
    n, labels, stats, _ = cv2.connectedComponentsWithStats(rest, connectivity=8)
    on_band = cv2.bitwise_and(rest, band)
    for i in range(1, n):
        area = stats[i][4]
        component = labels == i
        if np.count_nonzero(on_band[component]) > 0.6 * area:
            rest[component] = 0
    return rest


def _line_and_text_candidates(rest: np.ndarray) -> list[dict]:
    h, w = rest.shape
    out = []
    n, labels, stats, _ = cv2.connectedComponentsWithStats(rest, connectivity=8)
    small = np.zeros_like(rest)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 12:
            continue
        if bw > 80 and bh < 18 and bw / max(1, bh) > 6:
            shape = "line" if _straight(labels[y:y + bh, x:x + bw] == i) else "squiggle"
            out.append(_cand((x, y, bw, bh), shape, 0.8, rest))
            continue
        if bh > 120 and bw > 120:
            continue  # stray big stroke, not text
        if max(bw, bh) > 300 and area < 0.12 * bw * bh:
            continue  # a long sparse stroke (a box edge that survived outline removal) would glue neighbouring words together
        small[labels == i] = 255
    words = _text_lines(small)
    lines = [ln for ln in words if ln[2] >= 14 and ln[3] >= 8]
    specks = [ln for ln in words if ln[2] <= 16 and ln[3] <= 16]
    lists, lines = _bullet_lists(lines, small, specks)
    for box in lists:
        out.append(_cand(box, "list", 0.7, small))
    for x, y, bw, bh in lines:
        ink = cv2.countNonZero(small[y:y + bh, x:x + bw]) / (bw * bh)
        aspect = bw / bh
        if aspect > 6 and ink < 0.2 and bh < 30:
            shape = "squiggle"
        else:
            shape = "text"
        out.append(_cand((x, y, bw, bh), shape, 0.6, small))
    return out


def _leading_bullet(small: np.ndarray, line: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    """The tiny mark at the start of a text line (a list bullet), if there is one: a speck of ink no bigger than
    ~13 px that stands a few px clear of the first letter and sits in the lower-middle of the line."""
    x, y, bw, bh = line
    sub = small[y:y + bh, x:x + bw]
    n, _, stats, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
    comps = sorted((tuple(int(v) for v in stats[i][:5]) for i in range(1, n) if stats[i][4] >= 6), key=lambda c: c[0])
    if len(comps) < 3:
        return None
    cx, cy, cw, ch, _ = comps[0]
    nx = comps[1][0]
    if cw <= 13 and ch <= 13 and nx - (cx + cw) >= 5 and cy + ch / 2 >= 0.3 * bh and max(c[3] for c in comps[1:]) >= 12:
        return x + cx, y + cy, cw, ch
    return None


def _bullet_lists(lines: list, small: np.ndarray, specks: list) -> tuple[list, list]:
    """Two or more text lines stacked in one column, each led by a bullet mark, are one list."""
    led = []
    for ln in lines:
        x, y, bw, bh = ln
        mark = next((m for m in specks if 3 <= x - (m[0] + m[2]) <= 30 and y + 0.3 * bh <= m[1] + m[3] / 2 <= y + bh + 2), None) \
            or _leading_bullet(small, ln)
        if mark:
            led.append((ln, mark))
    led.sort(key=lambda t: t[0][1])
    groups, cur = [], []
    for item in led:
        if cur and (abs(item[1][0] - cur[-1][1][0]) <= 8 and 0 <= item[0][1] - (cur[-1][0][1] + cur[-1][0][3]) <= 1.6 * cur[-1][0][3]):
            cur.append(item)
        else:
            if cur:
                groups.append(cur)
            cur = [item]
    if cur:
        groups.append(cur)
    boxes, taken = [], []
    for g in groups:
        if len(g) < 2:
            continue
        x0 = min(min(m[0], ln[0]) for ln, m in g)
        y0 = min(ln[1] for ln, _ in g)
        x1 = max(ln[0] + ln[2] for ln, _ in g)
        y1 = max(ln[1] + ln[3] for ln, _ in g)
        boxes.append((x0, y0, x1 - x0, y1 - y0))
        taken += [ln for ln, _ in g]
    return boxes, [ln for ln in lines if ln not in taken]


def _text_lines(small: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Group ink into words (letters a few px apart) and words into lines.

    Two words belong to one line when they share a baseline band and the gap between them is smaller than ~0.55 of
    the text height (a space), so a sentence is one box while menu items spaced further apart stay separate."""
    joined = cv2.dilate(small, cv2.getStructuringElement(cv2.MORPH_RECT, (11, 7)))
    n, labels, _, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    ys, xs = np.nonzero(small)
    if not len(ys):
        return []
    at = labels[ys, xs]
    words = []
    for i in range(1, n):
        sel = at == i
        if sel.any():
            x0, x1, y0, y1 = int(xs[sel].min()), int(xs[sel].max()) + 1, int(ys[sel].min()), int(ys[sel].max()) + 1
            words.append([x0, y0, x1 - x0, y1 - y0])
    words.sort(key=lambda b: b[0])
    merged = True
    while merged:
        merged = False
        for i in range(len(words)):
            a = words[i]
            for j in range(i + 1, len(words)):
                b = words[j]
                v = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
                gap = max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2])
                if v > 0.55 * min(a[3], b[3]) and gap < 0.55 * max(a[3], b[3]):
                    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
                    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
                    words[i] = [x0, y0, x1 - x0, y1 - y0]
                    del words[j]
                    merged = True
                    break
            if merged:
                break
    return [tuple(w) for w in words]


def _straight(component: np.ndarray) -> bool:
    """A ruled line stays on a straight path; a wavy text placeholder oscillates around it."""
    cols = np.where(component.any(axis=0))[0]
    if len(cols) < 20:
        return True
    centers = np.array([np.nonzero(component[:, c])[0].mean() for c in cols])
    slope, intercept = np.polyfit(cols, centers, 1)
    return float(np.std(centers - (slope * cols + intercept))) < 1.15


def _merge_ocr(cands: list[dict], lines: list[dict], w: int, h: int) -> list[dict]:
    """Give OCR-read text lines to the stroke-based text candidates (splitting a line that holds several separated
    items, e.g. a row of menu words), and add lines the stroke analysis did not find."""
    textual = [c for c in cands if c["shape"] == "text"]
    taken: set[int] = set()
    added = []
    for ln in lines:
        lx, ly, lw, lh = ln["px"]
        inside = [c for c in textual if id(c) not in taken
                  and lx - 8 <= c["px"][0] + c["px"][2] / 2 <= lx + lw + 8
                  and ly - 0.3 * lh <= c["px"][1] + c["px"][3] / 2 <= ly + lh * 1.3]
        # OCR separates widely spaced items (a row of menu words) with a run of spaces
        segments = [t for t in re.split(r"\s{2,}", ln["text"]) if t]
        if len(inside) >= 2 and len(segments) >= 2:
            inside.sort(key=lambda c: c["px"][0])
            total = sum(len(t) for t in segments)
            groups: list[list[str]] = [[] for _ in inside]
            done = 0
            for t in segments:
                centre = lx + lw * (done + len(t) / 2) / total
                done += len(t)
                j = min(range(len(inside)), key=lambda k: abs(inside[k]["px"][0] + inside[k]["px"][2] / 2 - centre))
                groups[j].append(t)
            for c, g in zip(inside, groups):
                c["text"], c["ocr_score"] = " ".join(g), ln["score"]
                taken.add(id(c))
        elif inside:
            best = max(inside, key=lambda c: c["px"][2] * c["px"][3])
            for c in inside:
                taken.add(id(c))
            best["text"], best["ocr_score"] = ln["text"], ln["score"]
            # the line box is the better extent: it also covers words the strokes split apart
            best["px"] = (lx, ly, lw, lh)
            best["bbox"] = _norm(best["px"], w, h)
            best["ocr_box"] = True
            for c in inside:
                if c is not best:
                    cands.remove(c)
        else:
            added.append({"bbox": _norm((lx, ly, lw, lh), w, h), "px": (lx, ly, lw, lh), "shape": "text", "area": lw * lh,
                          "aspect": round(lw / max(1, lh), 3), "fill": 0.3, "conf": 0.6, "text": ln["text"],
                          "ocr_score": ln["score"], "ocr_box": True})
    # a "box" that is just a word's outline (the OCR line sits on it) is the text, not a control
    cands = [c for c in cands if not (c["shape"] == "rect" and c["px"][3] < 48 and any(
        irm.iou(c["bbox"], _norm(ln["px"], w, h)) > 0.45 for ln in lines))]
    return cands + added


def detect_cv(image_bytes: bytes, use_ocr: bool | None = None) -> list[dict]:
    """OpenCV candidates: [{bbox (normalised), shape: rect|circle|line|text|squiggle|cross_box|list, area, aspect, fill,
    conf, guess, text?}]. With OCR available, text candidates carry the text read from them (`text`)."""
    img, _ = _to_work(decode(image_bytes))
    mask = ink_mask(img)
    shapes = _shape_candidates(mask)
    shapes = _dedupe(shapes)
    shapes += _open_rects(mask, shapes)
    rest = _strokes_outside(mask, shapes)
    others = _line_and_text_candidates(rest)
    cands = _dedupe(shapes + others)
    h, w = mask.shape
    if use_ocr is None or use_ocr:
        lines = ocr_engine.read_lines(img)
        if lines is not None:
            cands = _merge_ocr(cands, lines, w, h)
    for c in cands:
        c["guess"] = _guess_type(c, cands, w, h)
    cands.sort(key=lambda c: (c["bbox"]["y"], c["bbox"]["x"]))
    for c in cands:
        c.pop("px", None)
    return cands


SHAPE_PRIORITY = {"cross_box": 0, "rect": 1, "circle": 1, "line": 2, "list": 2, "text": 3, "squiggle": 3}


def _dedupe(cands: list[dict]) -> list[dict]:
    """Drop near-duplicates; outlines win over text clusters made from the same strokes."""
    out: list[dict] = []
    for c in sorted(cands, key=lambda c: (SHAPE_PRIORITY.get(c["shape"], 4), -c["conf"])):
        if any(irm.iou(c["bbox"], o["bbox"]) > 0.7 for o in out):
            continue
        out.append(c)
    return out


def _guess_type(c: dict, cands: list[dict], w: int, h: int) -> str:
    """Geometry-only guess of the UI component type (used by cv mode and as a hint in hybrid)."""
    b, shape = c["bbox"], c["shape"]
    pw, ph = b["w"] * w, b["h"] * h
    inside = [o for o in cands if o is not c and irm.contains(b, o["bbox"], 0.9)]
    if shape == "cross_box":
        return "image"
    if shape == "circle":
        if c["fill"] > 0.06:
            return "icon" if pw < 90 else "image"  # something drawn inside: a symbol, not an option
        return "radio" if pw < 45 else ("icon" if pw < 90 else "image")
    if shape == "line":
        return "divider"
    if shape == "list":
        return "list"
    if shape == "squiggle":
        return "text"
    if shape == "text":
        return "heading" if ph > 34 else "text"
    # rectangles
    if pw < 60 and ph < 60 and 0.6 < pw / max(1, ph) < 1.6:
        return "checkbox"
    if b["y"] < 0.12 and b["w"] > 0.75 and ph < 110:
        return "navbar"
    shapes_inside = [o for o in inside if o["shape"] in ("rect", "circle", "cross_box")]
    if shapes_inside:
        return "card"
    if pw > 120 and ph > 110 and not inside:
        return "image"  # a big empty frame in a wireframe is a picture placeholder
    if pw > 260 and ph > 160:
        return "container"
    if ph <= 110 and pw / max(1, ph) > 2.0:
        texts = [o for o in inside if o["shape"] in ("text", "squiggle")]
        if c["fill"] > 0.35:
            return "button"
        if texts:
            t = texts[0]["bbox"]
            centered = abs((t["x"] + t["w"] / 2) - (b["x"] + b["w"] / 2)) < b["w"] * 0.15
            return "button" if centered or pw < 0.3 * w else "input"
        return "input"
    if ph > 110 and pw / max(1, ph) > 1.8 and not inside:
        return "textarea"
    return "container" if pw > 200 and ph > 120 else "button"


# --------------------------------------------------------------------------- vision

def _png(img: np.ndarray, max_side: int = 1280) -> bytes:
    h, w = img.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.imencode(".png", img)[1].tobytes()


def plausible(kind: str, bbox: dict, width: int, height: int, shape: str = "") -> bool:
    """Can a component of this kind have this drawn shape/size? (Used to overrule implausible vision labels.)"""
    w, h = bbox["w"] * width, bbox["h"] * height
    if shape in ("circle", "cross_box") and kind in ("heading", "text", "link", "nav_item", "divider"):
        return False  # words are not drawn as a closed circle or a crossed box
    if kind in ("icon", "radio", "checkbox"):
        return w < 90 and h < 90 and 0.4 < w / max(1, h) < 2.5
    if kind in ("input", "select", "button", "textarea"):
        return h >= 20 and w >= 30
    if kind == "divider":
        return h < 30 and w > 3 * h
    return True


def numbered_image(img: np.ndarray, cands: list[dict]) -> np.ndarray:
    """Copy of the sketch with each OpenCV proposal drawn as a red numbered box."""
    out = img.copy()
    h, w = out.shape[:2]
    for i, c in enumerate(cands, start=1):
        x, y, bw, bh = _px(c["bbox"], w, h)
        cv2.rectangle(out, (x, y), (x + bw, y + bh), (0, 0, 230), 2)
        tag = str(i)
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        if bw >= 70 and bh >= 30:            # inside the top-right corner: handwriting starts on the left
            tx, ty = x + bw - tw - 9, y + th + 6
        else:                                # small box: just above its right end
            tx, ty = max(0, x + bw - tw - 6), max(th + 4, y - 3)
        cv2.rectangle(out, (tx, ty - th - 4), (tx + tw + 6, ty + 2), (0, 0, 230), -1)
        cv2.putText(out, tag, (tx + 3, ty - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    return out


TYPE_GUIDE = (
    "Component types: button, input (single-line text field), textarea, checkbox, radio, select (dropdown), "
    "heading (large title text), text (normal handwritten text or text placeholder squiggles), link (underlined "
    "or link-like text), image (box with an X or diagonal lines, or a picture), icon (tiny symbol), navbar (top "
    "bar with menu items), nav_item (an item inside a navbar), header, card (a box grouping other components), "
    "container, form, list, divider (a horizontal line). "
)

BOX_SCHEMA = llm.obj({
    "boxes": {"type": "array", "items": llm.obj({
        "n": {"type": "integer"},
        "type": {"type": "string", "enum": [*VISION_TYPES, "none"]},
        "label": {"type": "string"},
        "confidence": {"type": "number"},
    })},
    "missed": {"type": "array", "items": llm.obj({
        "type": {"type": "string", "enum": VISION_TYPES},
        "label": {"type": "string"},
        "x": {"type": "number"}, "y": {"type": "number"}, "w": {"type": "number"}, "h": {"type": "number"},
    })},
    "title": {"type": "string"},
    "category": {"type": "string"},
})

FULL_SCHEMA = llm.obj({
    "components": {"type": "array", "items": llm.obj({
        "type": {"type": "string", "enum": VISION_TYPES},
        "label": {"type": "string"},
        "x": {"type": "number"}, "y": {"type": "number"}, "w": {"type": "number"}, "h": {"type": "number"},
        "confidence": {"type": "number"},
    })},
    "title": {"type": "string"},
    "category": {"type": "string"},
})

CATEGORIES = "login, registration, dashboard, profile, ecommerce, banking, booking, contact, settings, landing, other"


def _hint_line(i: int, c: dict, w: int, h: int) -> str:
    x, y, bw, bh = _px(c["bbox"], w, h)
    return (f"{i}: {c['shape']} {bw}x{bh}px at ({x},{y}); geometry suggests {c['guess']}"
            + (f"; text height {bh}px" if c["shape"] in ("text", "squiggle") else "")
            + (f"; OCR reads \"{c['text']}\"" if c.get("text") else ""))


LABEL_RULES = (
    "Rules of the wireframe vocabulary. "
    "(1) A checkbox (square) or radio (circle) is ONE component with the option text drawn beside it as its label; "
    "do not report that text as its own component. A circle with a symbol inside and no option text is an icon. "
    "(2) A dropdown (select) is a field with a small v-shaped arrow at its right end; a plain field is an input; "
    "a tall multi-line field is a textarea. A small glyph inside a field (arrow, calendar, magnifier) is not a component. "
    "(3) In a top navbar the first word at the left is the brand (heading) and the other words are nav_item; a bordered "
    "word in a bar is a button. A bar with only a title (and maybe an icon or a field) is a header. "
    "(4) A box with an X, a picture or a chart/graph drawn in it is an image, never a card. A box that groups "
    "other components is a card; a vertical strip of menu items on the side is a navbar. "
    "(5) Short lines with bullet marks form one list (its lines are not separate components). "
    "(6) A long thin line between sections is a divider; wavy placeholder lines are text. "
    "(7) Large titles and big numbers are heading; ordinary words, captions and field captions are text; "
    "underlined or link-like words are link. Use `none` for a box that is noise or a fragment of another component. "
)


def _vision_label(img: np.ndarray, cands: list[dict]) -> tuple[dict, dict]:
    numbered = numbered_image(img, cands)
    h, w = img.shape[:2]
    hints = "\n".join(_hint_line(i, c, w, h) for i, c in enumerate(cands, start=1))
    messages = [
        {"role": "system", "content": (
            "You read rough hand-drawn UI wireframe sketches. " + TYPE_GUIDE +
            "The second image is the same sketch with numbered red boxes proposed by an OpenCV detector (pixel sizes "
            "are given in the list). For every numbered box return its component type (or 'none' if the box is noise or "
            "just part of another component, e.g. a stroke of a letter), and transcribe any handwritten text inside or "
            "forming it as `label` (empty string if none; when the proposal list gives an OCR reading, use it unless it is clearly wrong). A handwritten word written right above or left of an input "
            "box is a separate 'text' component (its label). Text written inside a button/input box is that box's label. "
            "If a box covers only part of a word or phrase, give the whole word/phrase it belongs to. Containers (navbar, "
            "header, card, container, form, list) get an empty label: every word or control drawn inside them (a brand "
            "name, each menu item, a button) is its own component; if no numbered box covers it, add it to `missed` with "
            "its own tight box. " + LABEL_RULES +
            "Then list in `missed` every visible component that no numbered box covers, with a bounding box "
            "normalised to 0..1 of the image (x,y = top-left). Also give a short page title and a category "
            f"({CATEGORIES}). Confidence is 0..1.")},
        {"role": "user", "content": [
            {"type": "text", "text": f"Original sketch ({w}x{h}px), then the numbered proposals. Proposals:\n{hints}"},
            llm.image_part(_png(img)),
            llm.image_part(_png(numbered)),
        ]},
    ]
    return llm.chat_json(messages, BOX_SCHEMA, "sketch_labels", config.get("OPENAI_VISION_MODEL"))


def grid_image(img: np.ndarray) -> np.ndarray:
    """Copy of the sketch with a light, labelled 10% coordinate grid (helps the model report positions)."""
    out = img.copy()
    h, w = out.shape[:2]
    for i in range(1, 10):
        x, y = int(w * i / 10), int(h * i / 10)
        cv2.line(out, (x, 0), (x, h), (235, 190, 120), 1)
        cv2.line(out, (0, y), (w, y), (235, 190, 120), 1)
        cv2.putText(out, f"{i / 10:.1f}", (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 120, 40), 1, cv2.LINE_AA)
        cv2.putText(out, f"{i / 10:.1f}", (2, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 120, 40), 1, cv2.LINE_AA)
    return out


def _vision_full(img: np.ndarray) -> tuple[dict, dict]:
    messages = [
        {"role": "system", "content": (
            "You read rough hand-drawn UI wireframe sketches and list every UI component. " + TYPE_GUIDE +
            "For each component give its type, the handwritten text it contains or that forms it (`label`, empty if "
            "none) and its bounding box normalised to 0..1 of the image (x,y = top-left corner, w,h = size). "
            "Include containers (cards/boxes that group other components) as separate components with an empty label; "
            "every word or control inside a navbar/header/card is its own component. A handwritten "
            "word right above or left of an input box is a separate 'text' component. List components in reading "
            f"order. Also give a short page title and a category ({CATEGORIES}). Confidence is 0..1. "
            "The second image has a labelled grid every 0.1 of the width/height: use it to measure boxes "
            "tightly around each drawn component.")},
        {"role": "user", "content": [{"type": "text", "text": "The sketch, then the same sketch with a coordinate grid:"},
                                     llm.image_part(_png(img)), llm.image_part(_png(grid_image(img)))]},
    ]
    return llm.chat_json(messages, FULL_SCHEMA, "sketch_components", config.get("OPENAI_VISION_MODEL"))


VERIFY_SCHEMA = llm.obj({
    "fixes": {"type": "array", "items": llm.obj({
        "n": {"type": "integer"},
        "action": {"type": "string", "enum": ["retype", "remove"]},
        "type": {"type": "string", "enum": VISION_TYPES},
        "label": {"type": "string"},
    })},
    "missing": {"type": "array", "items": llm.obj({
        "type": {"type": "string", "enum": VISION_TYPES},
        "label": {"type": "string"},
        "x": {"type": "number"}, "y": {"type": "number"}, "w": {"type": "number"}, "h": {"type": "number"},
    })},
})


def verification_overlay(img: np.ndarray, components: list[dict]) -> np.ndarray:
    """The sketch with every detected component boxed and tagged "n:type" (colour by type)."""
    out = img.copy()
    h, w = out.shape[:2]
    for i, comp in enumerate(components, start=1):
        color = TYPE_COLORS.get(comp["type"], (80, 80, 80))
        x, y, bw, bh = _px(comp["bbox"], w, h)
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2)
        tag = f"{i}:{comp['type']}"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        ty = y - 3 if y > th + 6 else y + bh + th + 3
        cv2.rectangle(out, (x, ty - th - 3), (x + tw + 4, ty + 3), color, -1)
        cv2.putText(out, tag, (x + 2, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return out


def _vision_verify(img: np.ndarray, components: list[dict]) -> tuple[dict, dict]:
    listing = "\n".join(f"{i}: {c['type']}" + (f' "{c["label"]}"' if c.get("label") else "") for i, c in enumerate(components, start=1))
    messages = [
        {"role": "system", "content": (
            "You check the output of a wireframe component detector. The first image is the hand-drawn sketch, the "
            "second the same sketch with every detected component boxed and tagged `n:type`. " + TYPE_GUIDE + LABEL_RULES +
            "List ONLY the corrections: `fixes` (retype a box whose type is wrong, or remove a box that is noise, a "
            "duplicate or a fragment of another component) and `missing` (drawn components with no box, with a tight box "
            "normalised to 0..1, x,y = top-left). Do not list correct boxes. Do not rename good labels.")},
        {"role": "user", "content": [{"type": "text", "text": f"Detected components:\n{listing}"},
                                     llm.image_part(_png(img)), llm.image_part(_png(verification_overlay(img, components)))]},
    ]
    return llm.chat_json(messages, VERIFY_SCHEMA, "sketch_verify", config.get("OPENAI_VISION_MODEL"))


def apply_verification(components: list[dict], result: dict) -> list[dict]:
    drop: set[int] = set()
    for fix in result.get("fixes", []):
        n = fix.get("n", 0) - 1
        if not 0 <= n < len(components):
            continue
        if fix["action"] == "remove":
            drop.add(n)
        else:
            components[n]["type"] = fix["type"]
            if fix.get("label", "").strip() and components[n]["type"] not in CONTAINERS:
                components[n]["label"] = fix["label"].strip()
    out = [c for i, c in enumerate(components) if i not in drop]
    for item in result.get("missing", []):
        box = _clamp_box(item)
        if box and not any(irm.iou(box, c["bbox"]) > 0.3 for c in out):
            out.append({"type": item["type"], "label": item["label"].strip(), "bbox": box, "confidence": 0.6, "source": "vision"})
    return out


def _clamp_box(item: dict) -> dict | None:
    x, y = max(0.0, min(1.0, float(item["x"]))), max(0.0, min(1.0, float(item["y"])))
    w, h = max(0.0, min(1.0 - x, float(item["w"]))), max(0.0, min(1.0 - y, float(item["h"])))
    if w < 0.005 or h < 0.004:
        return None
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


# --------------------------------------------------------------------------- assembly

def containment_tree(components: list[dict]) -> None:
    """Set each component's parent to the smallest container component whose box holds it.
    Boxes estimated by the vision model alone are imprecise: mostly-inside is enough, and they are clamped in."""
    for i, comp in enumerate(components):
        best, best_area = None, None
        need = 0.4 if comp.get("source") == "vision" else 0.85
        for j, other in enumerate(components):
            if i == j or other["type"] not in CONTAINERS:
                continue
            if irm.contains(other["bbox"], comp["bbox"], need) or (need < 0.85 and _center_inside(comp["bbox"], other["bbox"])
                                                                  and comp["bbox"]["w"] * comp["bbox"]["h"] < other["bbox"]["w"] * other["bbox"]["h"]):
                area = other["bbox"]["w"] * other["bbox"]["h"]
                if best_area is None or area < best_area:
                    best, best_area = j, area
        if best is None and need < 0.85:  # imprecise box just outside a bar: it belongs to the bar
            for j, bar in enumerate(components):
                b, c = bar["bbox"], comp["bbox"]
                if bar["type"] in ("navbar", "header") and b["x"] <= c["x"] + c["w"] / 2 <= b["x"] + b["w"] \
                        and b["y"] - 0.03 <= c["y"] + c["h"] / 2 <= b["y"] + b["h"] + 0.03 and comp["type"] not in CONTAINERS:
                    best = j
                    break
        comp["parent"] = best
        if best is not None and need < 0.85:
            comp["bbox"] = _clamp_into(comp["bbox"], components[best]["bbox"])


def _center_inside(inner: dict, outer: dict) -> bool:
    cx, cy = inner["x"] + inner["w"] / 2, inner["y"] + inner["h"] / 2
    return outer["x"] < cx < outer["x"] + outer["w"] and outer["y"] < cy < outer["y"] + outer["h"]


def _clamp_into(inner: dict, outer: dict) -> dict:
    inset_x, inset_y = 0.04 * outer["w"], 0.04 * outer["h"]
    outer = {"x": outer["x"] + inset_x, "y": outer["y"] + inset_y,
             "w": outer["w"] - 2 * inset_x, "h": outer["h"] - 2 * inset_y}
    x = max(inner["x"], outer["x"])
    y = max(inner["y"], outer["y"])
    w = min(inner["x"] + inner["w"], outer["x"] + outer["w"]) - x
    h = min(inner["y"] + inner["h"], outer["y"] + outer["h"]) - y
    return {"x": round(x, 4), "y": round(y, 4), "w": round(max(w, 0.005), 4), "h": round(max(h, 0.005), 4)}


def draw_overlay(img: np.ndarray, components: list[dict]) -> bytes:
    out = cv2.addWeighted(img, 0.55, np.full_like(img, 255), 0.45, 0)
    h, w = out.shape[:2]
    for i, comp in enumerate(components):
        color = TYPE_COLORS.get(comp["type"], (80, 80, 80))
        x, y, bw, bh = _px(comp["bbox"], w, h)
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2)
        tag = f"{i + 1} {comp['type']}" + (f": {comp['label'][:18]}" if comp.get("label") else "")
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        ty = y - 4 if y > th + 8 else y + bh + th + 4
        cv2.rectangle(out, (x, ty - th - 4), (x + tw + 6, ty + 3), color, -1)
        cv2.putText(out, tag, (x + 3, ty - 1), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return cv2.imencode(".png", out)[1].tobytes()


def analyze_sketch(image_bytes: bytes, mode: str = "hybrid", overlay: bool = True, use_ocr: bool | None = None,
                   verify: bool | None = None) -> dict:
    """Image -> SketchAnalysis {components:[{type,label,bbox,confidence,source,parent}], width, height, mode, timings}."""
    mode = mode if mode in ("cv", "vision", "hybrid") else "hybrid"
    started = time.perf_counter()
    original = decode(image_bytes)
    height, width = original.shape[:2]
    img, _ = _to_work(original)
    if mode != "cv" and not config.openai_configured():
        raise config.OpenAIUnavailable()

    timings = {"cv_ms": 0, "vision_ms": 0}
    title, category, model_info = "", "", None
    components: list[dict] = []

    if mode in ("cv", "hybrid"):
        t = time.perf_counter()
        cands = detect_cv(image_bytes, use_ocr=use_ocr)
        timings["cv_ms"] = int((time.perf_counter() - t) * 1000)
    else:
        cands = []

    if mode == "cv":
        components = [{"type": c["guess"], "label": c.get("text", ""), "bbox": c["bbox"], "confidence": c["conf"],
                       "source": "cv", "shape": c["shape"], "ocr": bool(c.get("ocr_box"))} for c in cands]
    elif mode == "vision":
        t = time.perf_counter()
        result, model_info = _vision_full(img)
        timings["vision_ms"] = int((time.perf_counter() - t) * 1000)
        for item in result.get("components", []):
            box = _clamp_box(item)
            if box:
                components.append({"type": item["type"], "label": item["label"].strip(), "bbox": box,
                                   "confidence": round(float(item.get("confidence", 0.8)), 3), "source": "vision"})
        title, category = result.get("title", ""), result.get("category", "")
    else:
        t = time.perf_counter()
        result, model_info = _vision_label(img, cands)
        timings["vision_ms"] = int((time.perf_counter() - t) * 1000)
        labels = {b["n"]: b for b in result.get("boxes", [])}
        for i, cand in enumerate(cands, start=1):
            lab = labels.get(i)
            if lab is None:
                components.append({"type": cand["guess"], "label": cand.get("text", ""), "bbox": cand["bbox"],
                                   "shape": cand["shape"], "ocr": bool(cand.get("ocr_box")),
                                   "confidence": round(cand["conf"] * 0.6, 3), "source": "cv"})
            elif lab["type"] == "none" and cand.get("text") and cand.get("ocr_score", 0) >= 0.8 and cand["shape"] == "text":
                # the model took it for noise, but OCR reads real words there
                components.append({"type": "text", "label": cand["text"], "bbox": cand["bbox"], "shape": cand["shape"],
                                   "ocr": bool(cand.get("ocr_box")), "confidence": round(cand["conf"], 3), "source": "hybrid"})
            elif lab["type"] != "none":
                kind = "text" if lab["type"] == "divider" and cand["shape"] == "squiggle" else lab["type"]
                if cand["shape"] == "list":
                    kind = "list"  # bulleted lines were recognised from the strokes themselves
                if not plausible(kind, cand["bbox"], img.shape[1], img.shape[0], cand["shape"]):
                    kind = cand["guess"]  # the drawn geometry contradicts the label (e.g. a wide box called an icon)
                label = lab["label"].strip()
                if cand.get("text") and kind not in CONTAINERS and cand.get("ocr_score", 0) >= 0.8 and (
                        not label or difflib.SequenceMatcher(None, norm_label(label), norm_label(cand["text"])).ratio() < 0.6):
                    label = cand["text"]  # the vision reading is used unless it is empty or unrelated to what OCR read
                elif " " in (cand.get("text") or "") and " " not in label and \
                        norm_label(label).replace(" ", "") == norm_label(cand["text"]).replace(" ", ""):
                    label = cand["text"]  # same words, but only OCR kept the spaces
                components.append({"type": kind, "label": label, "bbox": cand["bbox"], "shape": cand["shape"],
                                   "ocr": bool(cand.get("ocr_box")),
                                   "confidence": round((cand["conf"] + float(lab.get("confidence", 0.8))) / 2, 3),
                                   "source": "hybrid"})
        for item in result.get("missed", []):
            box = _clamp_box(item)
            if box and not any(irm.iou(box, c["bbox"]) > 0.5 for c in components):
                components.append({"type": item["type"], "label": item["label"].strip(), "bbox": box,
                                   "confidence": 0.7, "source": "vision"})
        title, category = result.get("title", ""), result.get("category", "")

    components = clean_components(components, size=(img.shape[1], img.shape[0]), mask=ink_mask(img))
    if verify is None:
        verify = config.get("NGUI_SKETCH_VERIFY").strip().lower() in ("1", "true", "yes", "on")
    if verify and mode != "cv":
        t = time.perf_counter()
        components.sort(key=lambda c: (round(c["bbox"]["y"], 2), c["bbox"]["x"]))
        fixes, _ = _vision_verify(img, components)
        components = apply_verification(components, fixes)
        timings["verify_ms"] = int((time.perf_counter() - t) * 1000)
    components.sort(key=lambda c: (round(c["bbox"]["y"], 2), c["bbox"]["x"]))
    containment_tree(components)
    timings["total_ms"] = int((time.perf_counter() - started) * 1000)
    analysis = {
        "components": components,
        "width": width,
        "height": height,
        "mode": mode,
        "title": title,
        "category": (category or "").lower(),
        "timings": timings,
        "cv_candidates": len(cands),
    }
    if model_info:
        analysis["model"] = model_info["model"]
    if overlay:
        analysis["overlay_png_b64"] = base64.b64encode(draw_overlay(img, components)).decode()
    return analysis


TEXT_LIKE = {"heading", "text"}
TEXTUAL = {"heading", "text", "button", "link", "nav_item"}


def norm_label(label: str) -> str:
    """Case/punctuation-insensitive form of a label for comparisons."""
    return " ".join(re.findall(r"[a-z0-9]+", (label or "").lower()))


def _center_distance(a: dict, b: dict) -> float:
    return ((a["x"] + a["w"] / 2 - b["x"] - b["w"] / 2) ** 2 + (a["y"] + a["h"] / 2 - b["y"] - b["h"] / 2) ** 2) ** 0.5


def clean_components(components: list[dict], size: tuple[int, int] | None = None, mask: np.ndarray | None = None) -> list[dict]:
    """Analysis post-processing shared by every mode (all rules are geometric/label based).

    `size` is the working image size (w, h) and `mask` its ink mask; when given, boxes are calibrated against
    the strokes and the pixel-based structure rules run."""
    if mask is not None:
        refine_rules.calibrate_boxes(components, mask)
    for comp in components:
        if comp.get("label") and not norm_label(comp["label"]):
            comp["label"] = ""  # "~~~~" transcribed from a scribble: placeholder, not text
    components = components + recover_bar_brands(components)
    for comp in components:
        if comp["type"] in CONTAINERS:
            comp["label"] = ""  # a box's text belongs to the components drawn inside it
    components = drop_vision_echoes(components)
    components = drop_conflicting_overlaps(components)
    components = _merge_text_into_boxes(components)
    components = merge_duplicates(components)
    components = merge_prefix_fragments(components)
    components = merge_text_fragments(components)
    components = refine_rules.attach_marker_labels(components, size or (1000, 700))
    radios_without_labels_are_icons(components)
    unlabeled_glyphs_are_icons(components)
    components = pictures_are_images(components)
    unify_sibling_cards(components)
    if size is not None:
        components = refine_rules.refine_structure(components, size)
    for comp in components:
        comp.pop("_calibrated", None)
    return components


def pictures_are_images(components: list[dict]) -> list[dict]:
    """A box holding only drawing strokes (a sun circle, mountain lines) and no text or controls is a picture."""
    out = list(components)
    for box in components:
        if box["type"] not in ("card", "container") or box not in out:
            continue
        inside = [c for c in out if c is not box and irm.contains(box["bbox"], c["bbox"], 0.85)]
        if inside and all(c["type"] in ("icon", "divider") and not c.get("label") for c in inside) and len(inside) <= 3:
            box["type"] = "image"
            out = [c for c in out if c not in inside]
    return out


def recover_bar_brands(components: list[dict]) -> list[dict]:
    """When the reader put a whole bar's text on the bar ("Nimbus Features Pricing ..."), the words before the
    first item that has its own box are the brand drawn at the bar's left: give them a component."""
    added = []
    for bar in components:
        label = norm_label(bar.get("label", ""))
        if bar["type"] not in ("navbar", "header") or not label:
            continue
        items = sorted((c for c in components if c is not bar and norm_label(c.get("label", ""))
                        and irm.contains(bar["bbox"], c["bbox"], 0.8)), key=lambda c: c["bbox"]["x"])
        if not items:
            continue
        first = items[0]
        cut = label.find(norm_label(first["label"]))
        leading = label[:cut].strip() if cut > 0 else ""
        if not leading:
            continue
        b, f = bar["bbox"], first["bbox"]
        x = b["x"] + 0.02 * b["w"]
        width = min(0.012 * len(leading) + 0.02, f["x"] - x - 0.01)
        if width <= 0.01:
            continue
        words = bar["label"].split()
        brand = " ".join(words[:len(leading.split())])
        added.append({"type": "text", "label": brand, "bbox": {"x": round(x, 4), "y": f["y"], "w": round(width, 4),
                      "h": f["h"]}, "confidence": 0.5, "source": "inferred"})
    return added


FIELD_KINDS = {"input", "textarea", "select"}


def drop_conflicting_overlaps(components: list[dict]) -> list[dict]:
    """Two leaf components on (almost) the same box cannot both be right: keep the one whose label is not
    repeated elsewhere on the page (a label copied onto the wrong box), else the more precise source."""
    leaves = [c for c in components if c["type"] not in CONTAINERS]
    drop = set()
    for i, a in enumerate(leaves):
        for b in leaves[i + 1:]:
            if id(a) in drop or id(b) in drop or irm.iou(a["bbox"], b["bbox"]) < 0.6:
                continue
            def repeated(c):
                label = norm_label(c.get("label", ""))
                return bool(label) and sum(norm_label(o.get("label", "")) == label for o in components) > 1
            if repeated(a) != repeated(b):
                drop.add(id(a) if repeated(a) else id(b))
            elif (a.get("source") == "vision") != (b.get("source") == "vision"):
                drop.add(id(a) if a.get("source") == "vision" else id(b))
    return [c for c in components if id(c) not in drop]


def drop_vision_echoes(components: list[dict]) -> list[dict]:
    """A vision "missed" box whose text is already read from an OpenCV box nearby is the same component
    (vision boxes are imprecise, so overlap alone does not catch it)."""
    precise = [c for c in components if c.get("source") != "vision"]
    out = []
    for comp in components:
        label = norm_label(comp.get("label", ""))
        if comp.get("source") == "vision" and label:
            field = next((o for o in precise if o["type"] in FIELD_KINDS and norm_label(o.get("label", "")) == label
                          and irm.contains(comp["bbox"], o["bbox"], 0.8)), None)
            if field is not None:  # the field was found by its text only; vision saw the whole box
                field["bbox"] = irm.union_bbox([field["bbox"], comp["bbox"]])
                continue
        if comp.get("source") == "vision" and label and any(
                norm_label(o.get("label", "")) == label and (o["type"] == comp["type"] or
                                                            {o["type"], comp["type"]} <= TEXTUAL)
                and _center_distance(o["bbox"], comp["bbox"]) < 0.5 for o in precise):
            continue
        out.append(comp)
    return out


def merge_prefix_fragments(components: list[dict]) -> list[dict]:
    """OpenCV can split a handwritten title ("Cl" + "oud storage made simple" read as "Cloud storage made
    simple"): a short text right before a longer one on the same line that starts with it is the same text."""
    out = list(components)
    for frag in list(out):
        label = norm_label(frag.get("label", ""))
        if frag["type"] in CONTAINERS or not label:
            continue
        for whole in out:
            if whole is frag or not (whole["type"] == frag["type"] or {whole["type"], frag["type"]} <= TEXT_LIKE):
                continue
            a, b = frag["bbox"], whole["bbox"]
            same_line = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]) > 0.4 * min(a["h"], b["h"])
            if same_line and -0.5 * a["w"] <= b["x"] - (a["x"] + a["w"]) < 0.03 and \
                    norm_label(whole["label"]).startswith(label) and len(norm_label(whole["label"])) > len(label):
                whole["bbox"] = irm.union_bbox([a, b])
                out.remove(frag)
                break
    return out


def unlabeled_glyphs_are_icons(components: list[dict]) -> None:
    """A small, square, unreadable mark called text/heading is a drawn symbol, not words."""
    for comp in components:
        b = comp["bbox"]
        if comp["type"] in TEXT_LIKE and not comp.get("label") and b["w"] < 0.06 and b["h"] < 0.09 \
                and comp.get("shape") in ("rect", "circle", "cross_box"):
            comp["type"] = "icon"


def radios_without_labels_are_icons(components: list[dict]) -> None:
    """A radio is a small circle with option text beside it; without such text it is an icon."""
    texts = [c for c in components if c["type"] in TEXT_LIKE]
    for comp in components:
        if comp["type"] != "radio" or comp.get("label"):
            continue
        b = comp["bbox"]
        beside = any(abs((t["bbox"]["y"] + t["bbox"]["h"] / 2) - (b["y"] + b["h"] / 2)) < b["h"]
                     and 0 <= t["bbox"]["x"] - (b["x"] + b["w"]) < 0.06 for t in texts)
        if not beside:
            comp["type"] = "icon"


def unify_sibling_cards(components: list[dict]) -> None:
    """Boxes of the same size side by side are the same kind: a plain container among cards is a card."""
    boxes = [c for c in components if c["type"] in ("card", "container")]
    for comp in boxes:
        if comp["type"] != "container":
            continue
        b = comp["bbox"]
        twins = [o for o in boxes if o is not comp and o["type"] == "card"
                 and abs(o["bbox"]["w"] - b["w"]) < 0.15 * b["w"] and abs(o["bbox"]["h"] - b["h"]) < 0.15 * b["h"]
                 and abs(o["bbox"]["y"] - b["y"]) < 0.5 * b["h"]]
        if twins:
            comp["type"] = "card"


def merge_duplicates(components: list[dict]) -> list[dict]:
    """One drawn word can come back twice (two OpenCV fragments both read as "Dashboard", or a proposal
    plus a "missed" box). Same label + same kind + touching boxes -> one component with the union box."""
    def kind(c):
        return "text" if c["type"] in TEXT_LIKE else c["type"]

    def adjacent(a, b):
        if irm.iou(a, b) > 0.2:
            return True
        v_overlap = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
        h_gap = max(a["x"], b["x"]) - min(a["x"] + a["w"], b["x"] + b["w"])
        return v_overlap > 0.5 * min(a["h"], b["h"]) and h_gap < 0.03

    out: list[dict] = []
    for comp in components:
        label = (comp.get("label") or "").strip().lower()
        twin = next((o for o in out if label and kind(o) == kind(comp)
                     and (o.get("label") or "").strip().lower() == label and adjacent(o["bbox"], comp["bbox"])), None)
        if twin is None:
            out.append(comp)
            continue
        if comp.get("source") == "vision" and twin.get("source") != "vision":
            pass  # keep the precise OpenCV box
        elif twin.get("source") == "vision" and comp.get("source") != "vision":
            twin["bbox"], twin["source"] = comp["bbox"], comp["source"]
        else:
            twin["bbox"] = irm.union_bbox([twin["bbox"], comp["bbox"]])
        if comp["type"] == "heading":
            twin["type"] = "heading"
        twin["confidence"] = max(twin.get("confidence", 0), comp.get("confidence", 0))
    return out


def merge_text_fragments(components: list[dict]) -> list[dict]:
    """Unlabelled text pieces (scribbled placeholder lines) that continue each other on a line, or stack into
    a paragraph, become one text component, the way a person reads the drawing."""
    def joinable(a, b, limit):
        v_overlap = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
        h_gap = max(a["x"], b["x"]) - min(a["x"] + a["w"], b["x"] + b["w"])
        if v_overlap > 0.4 * min(a["h"], b["h"]) and h_gap < limit:
            return True
        x_overlap = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
        v_gap = max(a["y"], b["y"]) - min(a["y"] + a["h"], b["y"] + b["h"])
        return x_overlap > 0.3 * min(a["w"], b["w"]) and v_gap < 0.025

    bars = [c for c in components if c["type"] in ("navbar", "header")]
    texts = [c for c in components if c["type"] == "text" and not (c.get("label") or "").strip()]
    others = [c for c in components if c not in texts]
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(texts):
            for b in texts[i + 1:]:
                # menu items in the same bar are separate components even when they sit close
                limit = 0.0 if any(irm.contains(bar["bbox"], a["bbox"], 0.8) and irm.contains(bar["bbox"], b["bbox"], 0.8)
                                   for bar in bars) else 0.04
                if joinable(a["bbox"], b["bbox"], limit):
                    a["bbox"] = irm.union_bbox([a["bbox"], b["bbox"]])
                    a["confidence"] = max(a.get("confidence", 0), b.get("confidence", 0))
                    texts.remove(b)
                    merged = True
                    break
            if merged:
                break
    return others + texts


def _merge_text_into_boxes(components: list[dict]) -> list[dict]:
    """Text read inside a button/input/link box becomes that box's label instead of a separate component."""
    holders = [c for c in components if c["type"] in ("button", "input", "textarea", "select", "nav_item", "link")]
    fields = [c for c in holders if c["type"] in ("button", "input", "textarea", "select")]
    out = []
    for comp in components:
        # a "heading" read inside a button/field is that control's caption, not a title
        if comp["type"] == "heading" and comp.get("label") and comp not in holders:
            holder = next((h for h in fields if irm.contains(h["bbox"], comp["bbox"], 0.8)
                           and comp["bbox"]["h"] < 0.8 * h["bbox"]["h"]), None)
            if holder is not None:
                if not holder.get("label"):
                    holder["label"] = comp["label"]
                continue
        if comp["type"] == "text" or comp in holders:  # text, or the text cluster typed like its box (button in button)
            holder = next((h for h in holders if h is not comp and irm.contains(h["bbox"], comp["bbox"], 0.8)
                           and (comp["type"] == "text" or h["type"] == comp["type"])), None)
            if holder is not None:
                if comp.get("label") and not holder.get("label"):
                    holder["label"] = comp["label"]
                continue
        out.append(comp)
    return out


def overlay_png(analysis: dict) -> bytes | None:
    data = analysis.get("overlay_png_b64")
    return base64.b64decode(data) if data else None
