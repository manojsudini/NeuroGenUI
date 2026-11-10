"""Phase B/C: browser measurements, identical procedure for every system.

Per sketch and system (pipeline, pipeline_norepair, baseline, oracle):
  - DOM-level detection: validate.extract_dom(preview) (generic tag/role extraction, content-box normalised)
    matched to GT boxes re-normalised to the GT content box -> P/R/F1, type accuracy, mean IoU
  - layout IoU on the same boxes; edge-map SSIM between the sketch and a screenshot
  - functional correctness: every labels.interactions expectation simulated (dom.Renderer.simulate)
  - requirement satisfaction: every labels.requirements check
Per command and system (pipeline via apply_ops, pipeline from the Whisper transcript, baseline_modify):
  - post-condition check on the after-UI, preservation of non-target elements, render errors
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

import common  # noqa: F401
from checks import eval_check, eval_requirement, layout_iou, match, preservation, prf

log = logging.getLogger("eval.measure")


def _validate_mod():
    import importlib
    return importlib.import_module("app.pipeline.validate")


def content_norm(boxes: list[dict]) -> list[dict]:
    """Normalise boxes {x,y,w,h} to their union box (translation/scale invariant)."""
    if not boxes:
        return []
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["w"] for b in boxes)
    y1 = max(b["y"] + b["h"] for b in boxes)
    W, H = max(1e-9, x1 - x0), max(1e-9, y1 - y0)
    return [{"x": (b["x"] - x0) / W, "y": (b["y"] - y0) / H, "w": b["w"] / W, "h": b["h"] / H} for b in boxes]


def gt_content(lab):
    boxes = content_norm([c["bbox"] for c in lab["components"]])
    return [{"type": c["type"], "label": c["label"], "bbox": b} for c, b in zip(lab["components"], boxes)]


def edge_ssim(sketch_path: str, shot_path: Path, width: int = 500) -> float:
    """SSIM between dilated+blurred Canny edge maps of the sketch and of the screenshot, after cropping
    the screenshot to the sketch's aspect ratio (top-aligned, white-padded) and resizing both to 500 px wide."""
    sk = cv2.imread(sketch_path, cv2.IMREAD_GRAYSCALE)
    sh = cv2.imread(str(shot_path), cv2.IMREAD_GRAYSCALE)
    h = int(round(width * sk.shape[0] / sk.shape[1]))
    want_h = int(round(sh.shape[1] * sk.shape[0] / sk.shape[1]))
    if sh.shape[0] >= want_h:
        sh = sh[:want_h]
    else:
        sh = np.vstack([sh, np.full((want_h - sh.shape[0], sh.shape[1]), 255, np.uint8)])
    sk = cv2.resize(sk, (width, h), interpolation=cv2.INTER_AREA)
    sh = cv2.resize(sh, (width, h), interpolation=cv2.INTER_AREA)

    def edges(g):
        e = cv2.Canny(cv2.GaussianBlur(g, (3, 3), 0), 40, 120)
        e = cv2.dilate(e, np.ones((3, 3), np.uint8))
        return cv2.GaussianBlur(e, (9, 9), 0)
    return float(structural_similarity(edges(sk), edges(sh), data_range=255))


def detection_from_dom(lab, extract) -> dict:
    gt = gt_content(lab)
    comps = extract.get("components") or []
    pred = [{"type": c["type"], "label": c.get("label", ""), "bbox": c["bbox"]} for c in comps]
    m = match(gt, pred)
    m["layout_iou"] = layout_iou(gt, pred)
    return m


def measure_sketch(lab, systems: dict[str, str], renderer, shots_dir: Path) -> dict:
    validate = _validate_mod()
    out = {}
    h = lab["height"]
    for name, code in systems.items():
        if not code:
            out[name] = {"available": False}
            continue
        r = {"available": True}
        shot = shots_dir / name / f"{lab['id']}.png"
        snap = renderer.render(code, screenshot=shot, height=h)
        r["render_ok"] = snap["ok"]
        r["runtime_errors"] = (snap["run"].get("errors") or [])[:5] + snap["console_errors"][:5]
        r["n_elements"] = len(snap["elements"])
        ex = validate.extract_dom(code)
        r["extract_errors"] = ex.get("errors", [])[:5]
        det = detection_from_dom(lab, ex)
        r["det"] = {k: det[k] for k in ("n_gt", "n_pred", "matched", "tp_strict", "tp_lenient", "iou_sum")}
        r["det_pairs"] = det["pairs"]
        r["layout_iou"] = det["layout_iou"]
        r["ssim_edges"] = edge_ssim(lab["image_path"], shot) if shot.exists() else None
        sim = lambda exp, label: renderer.simulate(code, exp, label, height=h)  # noqa: E731
        r["interactions"] = [dict(sim(i["expect"], i["target_label"]), expect=i["expect"])
                             for i in lab["interactions"]]
        r["requirements"] = []
        for q in lab["requirements"]:
            if q["kind"] == "interaction":
                res = sim(q["expect"], q["target_label"])
                res = {"passed": res["passed"], "detail": res["detail"]}
            else:
                res = eval_requirement(q, snap, sim)
            r["requirements"].append({"req": q, **res})
        r["snap"] = snap
        out[name] = r
    return out


def measure_command(cmd, before_code, after_code, renderer, height, cache_snaps: dict) -> dict:
    """before_code: base UI; after_code: UI after the command (None = system failed to produce one)."""
    if not after_code:
        return {"available": False, "passed": False, "detail": "no output", "preservation": None}
    key = hash(before_code) if before_code else None
    before = None
    if before_code:
        if key not in cache_snaps:
            cache_snaps[key] = renderer.render(before_code, height=height)
        before = cache_snaps[key]
    after = renderer.render(after_code, height=height)
    sim = lambda exp, label: renderer.simulate(after_code, exp, label, height=height)  # noqa: E731
    try:
        res = eval_check(cmd["check"], before, after, sim)
    except Exception as e:  # noqa: BLE001
        log.exception("check failed for %s", cmd["id"])
        res = {"passed": False, "detail": f"check error {e}"}
    pre = None
    if before is not None and cmd["base"] != "empty" and cmd["check"]["kind"] not in ("event", "navigates", "size_change"):
        try:
            pre = bool(eval_check(cmd["check"], None, before, None)["passed"])
        except Exception:  # noqa: BLE001
            pre = None
    pres = preservation(before, after, cmd) if before is not None and cmd["base"] != "empty" else None
    return {"available": True, "passed": bool(res["passed"]) and after["ok"], "check_passed": res["passed"],
            "detail": res["detail"], "render_ok": after["ok"],
            "runtime_errors": (after["run"].get("errors") or [])[:3] + after["console_errors"][:3],
            "preservation": pres, "pre_satisfied": pre}


def png_bytes(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()
