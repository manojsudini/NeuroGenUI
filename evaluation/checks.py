"""Matching, post-condition checks, requirement checks and preservation, all on generic DOM snapshots
(see dom.py), so the same code scores the pipeline and the baseline."""
from __future__ import annotations

import colorsys
import re

import numpy as np
from scipy.optimize import linear_sum_assignment

from dom import find_element, norm, type_ok

# ------------------------------------------------------------------ geometry / matching


def iou(a: dict, b: dict) -> float:
    ix = max(0.0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0.0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    inter = ix * iy
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


LENIENT = [{"nav_item", "link"}, {"container", "card", "form"}, {"input", "textarea"}]


def same_type(a: str, b: str, lenient: bool) -> bool:
    if a == b:
        return True
    return lenient and any(a in g and b in g for g in LENIENT)


def match(gt: list[dict], pred: list[dict], thr: float = 0.3) -> dict:
    """Hungarian assignment maximising IoU among pairs with IoU >= thr (type-agnostic), then type check.

    gt/pred items: {"type", "bbox": {x,y,w,h} normalised}. Returns per-pair info and counts:
      matched            pairs with IoU >= thr (localisation)
      tp_strict/lenient  matched pairs whose type also agrees (strict / lenient equivalence)
    Precision/recall/F1 are computed on type-correct matches, as in object detection.
    """
    n, m = len(gt), len(pred)
    pairs = []
    if n and m:
        M = np.zeros((n, m))
        for i, g in enumerate(gt):
            for j, p in enumerate(pred):
                M[i, j] = iou(g["bbox"], p["bbox"])
        cost = np.where(M >= thr, -M, 1.0)
        # prefer same-type pairs on near ties: tiny bonus
        for i, g in enumerate(gt):
            for j, p in enumerate(pred):
                if M[i, j] >= thr and same_type(g["type"], p["type"], True):
                    cost[i, j] -= 0.05
        r, c = linear_sum_assignment(cost)
        for i, j in zip(r, c):
            if M[i, j] >= thr:
                pairs.append({"gt": i, "pred": j, "iou": float(M[i, j]), "gt_type": gt[i]["type"],
                              "pred_type": pred[j]["type"],
                              "type_strict": gt[i]["type"] == pred[j]["type"],
                              "type_lenient": same_type(gt[i]["type"], pred[j]["type"], True)})
    out = {"n_gt": n, "n_pred": m, "matched": len(pairs), "pairs": pairs,
           "tp_strict": sum(p["type_strict"] for p in pairs),
           "tp_lenient": sum(p["type_lenient"] for p in pairs),
           "iou_sum": sum(p["iou"] for p in pairs)}
    return out


def prf(tp: int, n_pred: int, n_gt: int) -> tuple[float, float, float]:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gt if n_gt else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def layout_iou(gt: list[dict], pred: list[dict]) -> float:
    """Mean over GT components of the IoU with the Hungarian-assigned rendered element
    (type-agnostic, any IoU > 0); unassigned GT components count 0."""
    if not gt:
        return 0.0
    if not pred:
        return 0.0
    M = np.array([[iou(g["bbox"], p["bbox"]) for p in pred] for g in gt])
    r, c = linear_sum_assignment(-M)
    return float(sum(M[i, j] for i, j in zip(r, c)) / len(gt))


# ------------------------------------------------------------------ colour


def parse_rgb(s: str):
    m = re.match(r"rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)", s or "")
    if not m:
        return None
    r, g, b = (float(m.group(i)) for i in (1, 2, 3))
    a = float(m.group(4)) if m.group(4) is not None else 1.0
    return r, g, b, a


def hue_name(s: str) -> str | None:
    """Coarse colour name of a CSS rgb() string: red, orange, yellow, green, teal, blue, purple, pink,
    black, white, gray; None for transparent."""
    c = parse_rgb(s)
    if not c or c[3] < 0.2:
        return None
    r, g, b = (x / 255 for x in c[:3])
    h, l, sat = colorsys.rgb_to_hls(r, g, b)
    if l < 0.13 or (sat < 0.25 and l < 0.3):
        return "black"
    if l > 0.93:
        return "white"
    if sat < 0.18:
        return "gray"
    deg = h * 360
    if deg < 12 or deg >= 340:
        return "red" if not (l > 0.7) else "pink"
    if deg < 40:
        return "orange"
    if deg < 68:
        return "yellow"
    if deg < 160:
        return "green"
    if deg < 195:
        return "teal"
    if deg < 255:
        return "blue"
    if deg < 290:
        return "purple"
    return "pink"


HUE_ALIASES = {"teal": {"teal", "cyan"}, "purple": {"purple", "violet"}, "black": {"black"}}


def hue_matches(el: dict, want: str, key: str) -> bool:
    names = []
    if key in ("color", "bg"):
        names += [hue_name(el.get("bg")), hue_name(el.get("border"))]
    if key in ("textColor", "color"):
        names.append(hue_name(el.get("color")))
    if key == "color" and el["type"] not in ("button",):
        names.append(hue_name(el.get("color")))
    return want in {n for n in names if n}


# ------------------------------------------------------------------ post-conditions


def _el(snap, label, type=None):
    return find_element(snap["elements"], label or "", type)


def eval_check(check: dict, before: dict | None, after: dict, simulate=None) -> dict:
    """Evaluate a commands.jsonl post-condition. `before`/`after` are DOM snapshots; `simulate(expect, label)`
    runs an interaction on the after-code. Returns {"passed", "detail"}."""
    k = check["kind"]
    if k == "all":
        subs = [eval_check(c, before, after, simulate) for c in check["checks"]]
        return {"passed": all(s["passed"] for s in subs), "detail": "; ".join(s["detail"] for s in subs)}
    if k == "node_exists":
        e = _el(after, check["label_contains"], check["type"])
        return {"passed": e is not None, "detail": f"{check['type']} '{check['label_contains']}' "
                + ("found" if e else "missing")}
    if k == "removed":
        lab = check.get("label_contains", "")
        if lab:
            still = _el(after, lab, check["type"])
        else:
            still = next((e for e in after["elements"] if type_ok(check["type"], e["type"])), None)
        return {"passed": still is None and after.get("ok", True),
                "detail": "gone" if still is None else f"still present: {still['label'][:40]!r}"}
    if k == "label_changed":
        new = _el(after, check["new"], check["type"])
        old_exact = [e for e in after["elements"] if type_ok(check["type"], e["type"]) and norm(e["label"]) == norm(check["old"])]
        ok = new is not None and not old_exact
        return {"passed": ok, "detail": f"new={'yes' if new else 'no'} old_remaining={len(old_exact)}"}
    if k == "attr_contains":
        hit = [e for e in after["elements"] if type_ok(check["type"], e["type"])
               and norm(check["value"]) in norm(e.get(check["attr"], ""))]
        return {"passed": bool(hit), "detail": f"{len(hit)} element(s) with {check['attr']} containing value"}
    if k == "order":
        a = _el(after, check["first"]["label"], check["first"].get("type"))
        b = _el(after, check["then"]["label"], check["then"].get("type"))
        if not a or not b:
            return {"passed": False, "detail": f"element missing (first={bool(a)}, then={bool(b)})"}
        ra, rb = a["rect"], b["rect"]
        acy, bcy = ra["y"] + ra["h"] / 2, rb["y"] + rb["h"] / 2
        acx, bcx = ra["x"] + ra["w"] / 2, rb["x"] + rb["w"] / 2
        rel = check.get("relation", "below")
        ok = {"below": bcy > acy + 4, "above": bcy < acy - 4, "left_of": bcx < acx - 4,
              "right_of": bcx > acx + 4}[rel]
        return {"passed": ok, "detail": f"{rel}: first cy={acy:.0f} cx={acx:.0f}, then cy={bcy:.0f} cx={bcx:.0f}"}
    if k == "size_change":
        if before is None:
            return {"passed": False, "detail": "no before snapshot"}
        a, b = _el(before, check["target_label"], check["type"]), _el(after, check["target_label"], check["type"])
        if not a or not b:
            return {"passed": False, "detail": f"element missing (before={bool(a)}, after={bool(b)})"}
        dim = check.get("dim", "area")
        val = {"area": lambda e: e["rect"]["w"] * e["rect"]["h"], "width": lambda e: e["rect"]["w"],
               "height": lambda e: e["rect"]["h"], "font": lambda e: e["fontSize"]}[dim]
        ratio = val(b) / max(1e-6, val(a))
        if dim == "area" and abs(ratio - 1) < 0.05:     # also accept a font-size change as "bigger/smaller"
            ratio = b["fontSize"] / max(1e-6, a["fontSize"]) if abs(b["fontSize"] - a["fontSize"]) > 0.5 else ratio
        ok = ratio > 1.05 if check["direction"] == "increase" else ratio < 0.95
        return {"passed": ok, "detail": f"{dim} ratio {ratio:.2f}"}
    if k == "style_eq":
        e = _el(after, check["target_label"], check["type"])
        if not e:
            return {"passed": False, "detail": "element missing"}
        ok = hue_matches(e, check["hue"], check.get("key", "color"))
        if ok and before is not None:   # must be a change, not a colour the element already had
            b = _el(before, check["target_label"], check["type"])
            if b is not None and hue_matches(b, check["hue"], check.get("key", "color")) and \
                    (b["bg"], b["color"], b["border"]) == (e["bg"], e["color"], e["border"]):
                ok = False
        return {"passed": ok, "detail": f"bg={hue_name(e['bg'])} text={hue_name(e['color'])} border={hue_name(e['border'])}"}
    if k == "event":
        if simulate is None:
            return {"passed": False, "detail": "no simulator"}
        exp = {"type": check["action"], **{x: check[x] for x in ("text_contains", "field_label", "format") if x in check}}
        r = simulate(exp, check["target_label"])
        return {"passed": r["passed"], "detail": r["detail"]}
    if k == "navigates":
        if simulate is None:
            return {"passed": False, "detail": "no simulator"}
        r = simulate({"type": "navigate", "page": check["page"]}, check["target_label"])
        return {"passed": r["passed"], "detail": r["detail"]}
    raise ValueError(f"unknown check kind {k}")


# ------------------------------------------------------------------ requirements


def eval_requirement(req: dict, snap: dict, simulate) -> dict:
    k = req["kind"]
    if k == "node_exists":
        e = _el(snap, req["label_contains"], req["type"])
        return {"passed": e is not None, "detail": "found" if e else "missing"}
    if k == "input_type":
        e = _el(snap, req["label_contains"], "input")
        ok = e is not None and e.get("inputType") == req["input_type"]
        return {"passed": ok, "detail": f"type={e.get('inputType') if e else None}"}
    if k == "count_at_least":
        n = sum(1 for e in snap["elements"] if e["type"] == req["type"])
        return {"passed": n >= req["n"], "detail": f"{n} found"}
    if k == "interaction":
        r = simulate(req["expect"], req["target_label"])
        return {"passed": r["passed"], "detail": r["detail"]}
    raise ValueError(k)


# ------------------------------------------------------------------ preservation


def _sig(e):
    return (e["type"], norm(e["label"]))


def preservation(before: dict, after: dict, cmd: dict) -> dict:
    """Fraction of NON-target elements of the before-UI that are unchanged after the command:
    same type + label present, with the same text colour, background and font size, and size within 15%.
    The command's target (and its anchor for move/add) is excluded; reflow-induced position shifts are allowed."""
    exp = cmd["expected"]
    exclude = set()
    tl = exp.get("target_label")
    if tl is not None:
        t = find_element(before["elements"], tl, exp.get("target_type"))
        if t is not None:
            exclude.add(t["idx"])
    if cmd["category"] == "modify" and "label" in exp["params"]:
        pass
    # elements drawn inside the target (e.g. the icon inside an image placeholder) belong to the target
    for t_idx in list(exclude):
        tr = next(e["rect"] for e in before["elements"] if e["idx"] == t_idx)
        for e in before["elements"]:
            r = e["rect"]
            ix = max(0.0, min(r["x"] + r["w"], tr["x"] + tr["w"]) - max(r["x"], tr["x"]))
            iy = max(0.0, min(r["y"] + r["h"], tr["y"] + tr["h"]) - max(r["y"], tr["y"]))
            if r["w"] * r["h"] > 0 and ix * iy / (r["w"] * r["h"]) >= 0.9:
                exclude.add(e["idx"])
    considered = [e for e in before["elements"] if e["idx"] not in exclude
                  and e["type"] not in ("card", "container", "form", "header", "navbar", "list")]
    by_sig = {}
    for e in after["elements"]:
        by_sig.setdefault(_sig(e), []).append(e)
    kept = 0
    changed = []
    for e in considered:
        ok = False
        for a in by_sig.get(_sig(e), []):
            same_style = (a["color"] == e["color"] and a["bg"] == e["bg"] and abs(a["fontSize"] - e["fontSize"]) < 0.6)
            w_ok = abs(a["rect"]["w"] - e["rect"]["w"]) <= 0.15 * max(e["rect"]["w"], 1) + 1
            h_ok = abs(a["rect"]["h"] - e["rect"]["h"]) <= 0.15 * max(e["rect"]["h"], 1) + 1
            if same_style and w_ok and h_ok:
                ok = True
                break
        kept += ok
        if not ok:
            changed.append(f"{e['type']}:{e['label'][:24]}")
    n = len(considered)
    return {"rate": kept / n if n else None, "n": n, "kept": kept, "changed": changed[:12]}
