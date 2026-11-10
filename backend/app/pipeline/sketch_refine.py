"""Geometry- and context-based post-processing of sketch components (shared by every analysis mode).

Detectors and vision readers are good at *finding* and *reading* things but weak at the conventions of a UI
wireframe: how big a text box really is, that a checkbox and the words beside it are one control, that the
first word of a top bar is the brand, that a drawing of a chart is a picture. Those conventions live here as
explicit rules over boxes (all in normalised coordinates, pixel thresholds use the working image size).
"""
from __future__ import annotations

import re

import cv2
import numpy as np

from . import ir as irm

LARGE_PX, SMALL_PX = 40, 30  # OCR line-box heights (px at 1000 px width) of titles vs ordinary text
TEXT_KINDS = {"text", "heading", "link", "nav_item"}
BOX_KINDS = {"card", "container", "navbar", "header", "form", "list"}


def _cx(b): return b["x"] + b["w"] / 2
def _cy(b): return b["y"] + b["h"] / 2


def _px_box(b: dict, w: int, h: int) -> tuple[int, int, int, int]:
    return int(round(b["x"] * w)), int(round(b["y"] * h)), int(round(b["w"] * w)), int(round(b["h"] * h))


# --------------------------------------------------------------------------- box calibration

def stroke_center_rect(mask: np.ndarray, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Re-estimate a drawn rectangle from the *centre line* of each of its four strokes.

    A wobbly pen outline overshoots the nominal rectangle in both directions, so the bounding box of the
    contour is bigger than the box the person meant (and a UI element would have). The median stroke position
    along each side is a robust estimate of the intended edge."""
    x, y, bw, bh = box
    H, W = mask.shape
    if bw < 24 or bh < 16:
        return box

    def side(vertical: bool, far: bool) -> float | None:
        if vertical:  # left / right edge: look in a band at the edge, collect per-row stroke centres
            band = max(4, min(20, int(bw * 0.3)))
            x0 = x + bw - band if far else x
            sub = mask[y + int(0.12 * bh): y + int(0.88 * bh), max(0, x0): min(W, x0 + band)]
            axis_len, idx_axis = sub.shape[0], 1
            off = max(0, x0)
        else:
            band = max(4, min(20, int(bh * 0.3)))
            y0 = y + bh - band if far else y
            sub = mask[max(0, y0): min(H, y0 + band), x + int(0.12 * bw): x + int(0.88 * bw)]
            axis_len, idx_axis = sub.shape[1], 0
            off = max(0, y0)
        if sub.size == 0 or axis_len == 0:
            return None
        centres = []
        lines = sub if vertical else sub.T  # iterate per row (vertical edge) or per column (horizontal edge)
        for line in lines:
            nz = np.flatnonzero(line)
            if nz.size:
                centres.append(float(nz.mean()))
        if len(centres) < 0.4 * axis_len:
            return None
        return off + float(np.median(centres))

    left, right, top, bottom = side(True, False), side(True, True), side(False, False), side(False, True)
    if None in (left, right, top, bottom):
        return box
    nx0, nx1, ny0, ny1 = int(round(left)), int(round(right)), int(round(top)), int(round(bottom))
    if nx1 - nx0 < 0.6 * bw or ny1 - ny0 < 0.6 * bh:
        return box
    return nx0, ny0, nx1 - nx0, ny1 - ny0


def calibrate_boxes(components: list[dict], mask: np.ndarray) -> None:
    """Pad ink-tight text boxes to a line box and pull wobbly outlines onto their stroke centres."""
    H, W = mask.shape
    for comp in components:
        shape, b = comp.get("shape"), comp["bbox"]
        if comp.get("source") == "vision" or comp.get("_calibrated"):
            continue
        if comp.get("ocr"):
            comp["_calibrated"] = True  # OCR line boxes already are line boxes
            continue
        if shape in ("text", "squiggle"):
            px, py, pw, ph = _px_box(b, W, H)
            # A line box reaches above the ascenders and a little below the baseline.
            top, bottom, left, right = 0.30 * ph, 0.12 * ph, 3.0, 0.5
            x0, y0 = max(0, px - left), max(0, py - top)
            x1, y1 = min(W, px + pw + right), min(H, py + ph + bottom)
            comp["bbox"] = {"x": round(x0 / W, 4), "y": round(y0 / H, 4),
                            "w": round((x1 - x0) / W, 4), "h": round((y1 - y0) / H, 4)}
        elif shape in ("rect", "cross_box"):
            x, y, bw, bh = stroke_center_rect(mask, _px_box(b, W, H))
            comp["bbox"] = {"x": round(x / W, 4), "y": round(y / H, 4), "w": round(bw / W, 4), "h": round(bh / H, 4)}
        comp["_calibrated"] = True


# --------------------------------------------------------------------------- controls with their words

def _is_mark(comp: dict, size: tuple[int, int]) -> bool:
    """A small, roughly square circle/box with no text of its own can be a checkbox or radio mark."""
    if comp["type"] in ("checkbox", "radio"):
        return True
    W, H = size
    b = comp["bbox"]
    pw, ph = b["w"] * W, b["h"] * H
    return (comp["type"] in ("icon", "text", "heading", "button", "input") and not comp.get("label")
            and comp.get("shape") in ("circle", "rect") and 16 <= pw <= 40 and 16 <= ph <= 40
            and 0.6 <= pw / ph <= 1.7)


def attach_marker_labels(components: list[dict], size: tuple[int, int] = (1000, 700)) -> list[dict]:
    """A checkbox / radio is the mark *and* the option text beside it: one component covering both."""
    marks = [c for c in components if _is_mark(c, size)]
    texts = [c for c in components if c["type"] in ("text", "heading", "link") and c.get("label")
             and c.get("source") != "inferred" and c not in marks]
    used: set[int] = set()
    for mark in sorted(marks, key=lambda c: (c["bbox"]["y"], c["bbox"]["x"])):
        mb = mark["bbox"]
        # an OCR line that already spans the mark ("OLow": the circle was read as a letter)
        spanning = next((t for t in texts if id(t) not in used and t["bbox"]["x"] <= mb["x"] + 0.4 * mb["w"]
                         and t["bbox"]["x"] + t["bbox"]["w"] > mb["x"] + mb["w"]
                         and irm.contains(t["bbox"], mb, 0.6) and t["bbox"]["w"] < 0.6), None)
        if spanning is not None:
            label = re.sub(r"^[Oo0Q](?:\s+|(?=[A-Z0-9]))", "", spanning["label"].strip()) or spanning["label"]
            mark["bbox"] = irm.union_bbox([mb, spanning["bbox"]])
            mark["label"] = label
            if mark["type"] not in ("checkbox", "radio"):
                mark["type"] = "radio" if mark.get("shape") == "circle" else "checkbox"
            used.add(id(spanning))
            continue
        best, best_gap = None, None
        for t in texts:
            if id(t) in used:
                continue
            tb = t["bbox"]
            gap = tb["x"] - (mb["x"] + mb["w"])
            if abs(_cy(tb) - _cy(mb)) < 0.7 * max(mb["h"], tb["h"]) and -0.3 * mb["w"] <= gap < 0.045 \
                    and tb["w"] > 0.5 * mb["w"] and not (tb["h"] > 1.8 * mb["h"]):
                if best is None or gap < best_gap:
                    best, best_gap = t, gap
        if best is not None:
            mark["bbox"] = irm.union_bbox([mb, best["bbox"]])
            mark["label"] = best["label"] if not mark.get("label") or len(best["label"]) >= len(mark["label"]) else mark["label"]
            if mark["type"] not in ("checkbox", "radio"):
                mark["type"] = "radio" if mark.get("shape") == "circle" else "checkbox"
            used.add(id(best))
    return [c for c in components if id(c) not in used]


def field_adornments(components: list[dict], size: tuple[int, int]) -> list[dict]:
    """A small mark at the right end of a field (a drop-down chevron, a calendar or search glyph, a textarea resize
    handle) belongs to the field. A wide chevron makes a plain input a select."""
    W, H = size
    drop = set()
    for field in components:
        if field["type"] not in ("input", "select", "textarea"):
            continue
        fb = field["bbox"]
        for c in components:
            if c is field or id(c) in drop or c["type"] in BOX_KINDS or c["type"] in ("button", "image", "checkbox", "radio"):
                continue
            b = c["bbox"]
            pw, ph = b["w"] * W, b["h"] * H
            if c.get("label") or pw > 48 or ph > 48:
                continue
            if irm.contains(fb, b, 0.8) and b["x"] > fb["x"] + 0.78 * fb["w"] and abs(_cy(b) - _cy(fb)) < 0.45 * fb["h"] + 0.01 \
                    or (field["type"] == "textarea" and irm.contains(fb, b, 0.8) and b["x"] > fb["x"] + 0.85 * fb["w"]):
                drop.add(id(c))
                if field["type"] == "input" and pw / max(ph, 1) >= 1.1 and ph <= 30:
                    field["type"] = "select"
    return [c for c in components if id(c) not in drop]


def underlines_are_decoration(components: list[dict]) -> list[dict]:
    """A thin stroke right under a text line and about as wide is that text's underline (a link), not a divider."""
    drop = set()
    for ln in components:
        b = ln["bbox"]
        if ln.get("shape") not in ("line", "squiggle") or ln.get("label") or b["h"] > 0.03:
            continue
        for t in components:
            if t is ln or t["type"] not in ("text", "heading", "link", "nav_item") or not t.get("label"):
                continue
            tb = t["bbox"]
            overlap = min(b["x"] + b["w"], tb["x"] + tb["w"]) - max(b["x"], tb["x"])
            gap = b["y"] - (tb["y"] + tb["h"])
            if overlap > 0.6 * b["w"] and b["w"] < 1.4 * tb["w"] and -0.5 * tb["h"] <= gap < 0.03:
                drop.add(id(ln))
                if t["type"] == "text":
                    t["type"] = "link"
                break
    return [c for c in components if id(c) not in drop]


def complete_fields(components: list[dict], size: tuple[int, int]) -> list[dict]:
    """Hand-drawn field outlines are often broken (a missing edge). A caption that sits inside the footprint of its
    siblings' column, or a caption with a lone chevron/glyph at the far end of its row, still tells where the field is."""
    W, H = size
    fields = [c for c in components if c["type"] in ("input", "select")]
    holders = [c for c in components if c["type"] in ("input", "select", "textarea", "button", "card", "navbar", "header",
                                                      "image", "list", "container", "form")]
    heights = sorted(f["bbox"]["h"] for f in fields)
    fh = heights[len(heights) // 2] if heights else 52 / H
    gone: set[int] = set()
    new: list[dict] = []
    orphans = [c for c in components if c["type"] in ("text", "heading") and c.get("label") and c.get("ocr", True)
               and c.get("shape") in ("text", None)
               and not any(h["type"] not in ("card", "navbar", "header", "container", "form", "image")
                           and irm.contains(h["bbox"], c["bbox"], 0.6) for h in holders)]

    def free(box: dict, ignore: set[int]) -> bool:
        for o in components:
            if id(o) in ignore or o["type"] in ("card", "container", "form", "navbar", "header") or id(o) in gone:
                continue
            ix = max(0.0, min(box["x"] + box["w"], o["bbox"]["x"] + o["bbox"]["w"]) - max(box["x"], o["bbox"]["x"]))
            iy = max(0.0, min(box["y"] + box["h"], o["bbox"]["y"] + o["bbox"]["h"]) - max(box["y"], o["bbox"]["y"]))
            if ix * iy > 0.1 * o["bbox"]["w"] * o["bbox"]["h"]:
                return False
        return True

    for t in orphans:
        tb = t["bbox"]
        if tb["w"] > 0.5 or tb["h"] > 0.75 * fh:
            continue
        # (a) a glyph at the far end of the row: [caption ........ v]
        marks = [m for m in components if m is not t and id(m) not in gone and not m.get("label")
                 and m["type"] not in ("card", "container", "form", "navbar", "header", "image", "button", "list", "divider")
                 and m["bbox"]["w"] * W <= 48 and m["bbox"]["h"] * H <= 48
                 and m["bbox"]["x"] > tb["x"] + tb["w"] + 0.1 and abs(_cy(m["bbox"]) - _cy(tb)) < 0.4 * fh]
        box = None
        if marks:
            m = min(marks, key=lambda c: c["bbox"]["x"])
            cand = {"x": round(tb["x"] - 0.012, 4), "y": round(_cy(tb) - fh / 2, 4),
                    "w": round(m["bbox"]["x"] + m["bbox"]["w"] + 0.012 - tb["x"] + 0.012, 4), "h": round(fh, 4)}
            if free(cand, {id(t), id(m)}):
                kind = "select" if m["bbox"]["w"] / max(m["bbox"]["h"] * H / W, 1e-6) >= 1.1 else "input"
                box, gone = (cand, kind), gone | {id(m)}
        # (b) the caption sits inset in the column of the sibling fields
        if box is None:
            sibs = [f for f in fields if f["bbox"]["w"] >= 0.25 and 0.007 <= tb["x"] - f["bbox"]["x"] <= 0.04
                    and f["bbox"]["x"] + f["bbox"]["w"] > tb["x"] + tb["w"]]
            if sibs:
                f = min(sibs, key=lambda c: abs(_cy(c["bbox"]) - _cy(tb)))
                fb = f["bbox"]
                cand = {"x": fb["x"], "y": round(_cy(tb) - fb["h"] / 2, 4), "w": fb["w"], "h": fb["h"]}
                if free(cand, {id(t)}):
                    box = (cand, "input" if f["type"] == "input" else f["type"])
        if box is not None:
            gone.add(id(t))
            new.append({"type": box[1], "label": t["label"], "bbox": box[0], "confidence": 0.5, "source": "inferred"})
    return [c for c in components if id(c) not in gone] + new


def absorb_list_items(components: list[dict]) -> list[dict]:
    """The lines of a detected list are its items, not separate components: fold them into the list."""
    lists = [c for c in components if c["type"] == "list"]
    gone: set[int] = set()
    for lst in lists:
        items = sorted((c for c in components if c is not lst and c["type"] not in BOX_KINDS
                        and irm.contains(lst["bbox"], c["bbox"], 0.8)), key=lambda c: c["bbox"]["y"])
        for it in items:
            gone.add(id(it))
        labels = [it["label"] for it in items if it.get("label")]
        if labels and not lst.get("items"):
            lst["items"] = labels
    return [c for c in components if id(c) not in gone]


# --------------------------------------------------------------------------- types from structure

def _inside(box: dict, comp: dict, frac: float = 0.8) -> bool:
    return irm.contains(box, comp["bbox"], frac)


def _leaf_children(box_comp: dict, components: list[dict]) -> list[dict]:
    return [c for c in components if c is not box_comp and _inside(box_comp["bbox"], c)]


def pictures_from_strokes(components: list[dict]) -> None:
    """A box whose only content is unlabelled drawing strokes (axes, a curve, a sun, mountains) is a picture."""
    if not any(c.get("label") for c in components):
        return  # nothing has been read: scribbles cannot be told from placeholder text
    for box in components:
        if box["type"] not in ("card", "container"):
            continue
        inside = [c for c in components if c is not box and irm.contains(box["bbox"], c["bbox"], 0.8)]
        if inside and all(c["type"] in ("text", "heading", "icon", "divider") and not c.get("label")
                          and c.get("shape") in ("text", "squiggle", "line", "circle", "rect", None) for c in inside) and len(inside) <= 4:
            box["type"] = "image"
            box["_picture"] = [id(c) for c in inside]


def retype_boxes(components: list[dict], size: tuple[int, int]) -> None:
    """Container vocabulary from geometry + content: top bars are navbars/headers, a tall bar of menu items is a
    sidebar nav, an empty frame (chart, photo) is an image, other grouping boxes are cards."""
    W, H = size
    for box in components:
        if box["type"] not in ("card", "container", "navbar", "header", "form"):
            continue
        b = box["bbox"]
        kids = _leaf_children(box, components)
        leaves = [k for k in kids if k["type"] not in BOX_KINDS]
        wordy = [k for k in leaves if k["type"] in TEXT_KINDS and k.get("label")]
        bar_like = b["w"] > 0.6 and b["h"] < 0.2 and b["y"] < 0.25
        sidebar = b["x"] < 0.15 and b["w"] < 0.3 and b["h"] > 0.3 and len(wordy) >= 3
        if box["type"] in ("card", "container"):
            if not kids:
                if b["w"] * W > 100 and b["h"] * H > 80:
                    box["type"] = "image"  # an empty frame is a picture / chart placeholder
                continue
            if bar_like and leaves:
                box["type"] = "navbar" if len(wordy) >= 2 else "header"
            elif sidebar:
                box["type"] = "navbar"
            else:
                box["type"] = "card"


def retype_text(components: list[dict], size: tuple[int, int]) -> None:
    """Role of text lines: brand/menu items in bars, titles by size."""
    W, H = size
    bars = [c for c in components if c["type"] in ("navbar", "header")]
    in_bar: set[int] = set()
    for bar in bars:
        bb = bar["bbox"]
        horizontal = bb["w"] >= bb["h"]
        items = sorted((c for c in components if c is not bar and _inside(bb, c) and c["type"] in TEXT_KINDS
                        and (c.get("label") or c.get("shape") == "text")), key=lambda c: c["bbox"]["x" if horizontal else "y"])
        if not items:
            continue
        for it in items:
            in_bar.add(id(it))
        if bar["type"] == "header":
            for it in items:
                if it["type"] in ("text", "link", "nav_item"):
                    it["type"] = "heading"
            continue
        first = items[0]
        rest = items[1:]
        brand = False
        if len(items) >= 3 and horizontal:
            gaps = [rest[i + 1]["bbox"]["x"] - (rest[i]["bbox"]["x"] + rest[i]["bbox"]["w"]) for i in range(len(rest) - 1)]
            gap0 = rest[0]["bbox"]["x"] - (first["bbox"]["x"] + first["bbox"]["w"])
            med = sorted(gaps)[len(gaps) // 2] if gaps else 0.0
            brand = first["type"] == "heading" or gap0 > 1.5 * med + 0.02
        elif len(items) >= 2:
            brand = first["type"] == "heading"
        for it in items:
            it["type"] = "heading" if (it is first and brand) else "nav_item"
    for comp in components:
        if id(comp) in in_bar or comp["type"] not in ("text", "heading") or not comp.get("label"):
            continue
        if comp.get("shape") not in ("text", None) or comp.get("source") == "vision":
            continue
        # OCR line boxes are ~1.1x the ink, calibrated stroke boxes 1.42x; titles are the bigger writing
        box_h = comp["bbox"]["h"] * H
        if comp.get("ocr"):  # clearly large or clearly small writing decides; in between the reader's opinion stands
            comp["type"] = "heading" if box_h >= LARGE_PX else "text" if box_h < SMALL_PX else comp["type"]
        else:
            comp["type"] = "heading" if box_h / 1.42 >= 26 else "text"


def lonely_wide_squiggles_are_dividers(components: list[dict], size: tuple[int, int]) -> None:
    """A single thin, long, unlabelled stroke between things is a rule/divider, not a text placeholder."""
    W, H = size
    for comp in components:
        if comp["type"] not in ("text", "divider") or comp.get("label"):
            continue
        b = comp["bbox"]
        if comp.get("shape") in ("line", "squiggle") and b["h"] * H <= 24 and b["w"] >= 0.25 and b["w"] * W > 8 * b["h"] * H:
            near = [o for o in components if o is not comp and o["type"] in ("text", "heading")
                    and not o.get("label") and abs(_cx(o["bbox"]) - _cx(b)) < 0.5 * b["w"]
                    and 0 < abs(_cy(o["bbox"]) - _cy(b)) < 0.05]
            comp["type"] = "text" if near else "divider"


def refine_structure(components: list[dict], size: tuple[int, int]) -> list[dict]:
    pictures_from_strokes(components)
    gone = {i for c in components for i in c.pop("_picture", [])}
    components = [c for c in components if id(c) not in gone]
    components = absorb_list_items(components)
    components = field_adornments(components, size)
    components = underlines_are_decoration(components)
    components = complete_fields(components, size)
    retype_boxes(components, size)
    retype_text(components, size)
    lonely_wide_squiggles_are_dividers(components, size)
    return components
