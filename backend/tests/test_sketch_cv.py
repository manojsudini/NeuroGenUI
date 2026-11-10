from app.pipeline import ir as irm
from app.pipeline import sketch


def test_cv_detects_rough_login_sketch(fixture_png, fixture_truth):
    analysis = sketch.analyze_sketch(fixture_png, mode="cv")
    comps = analysis["components"]
    assert analysis["mode"] == "cv" and analysis["width"] == 1000
    assert analysis["timings"]["vision_ms"] == 0 and analysis["overlay_png_b64"]
    for truth in fixture_truth["components"]:
        if truth["type"] in ("text", "heading"):
            continue
        if truth["type"] in ("checkbox", "radio"):  # the mark and its option text are one component
            assert any(c["type"] == truth["type"] and irm.iou(c["bbox"], truth["bbox"]) > 0.1 for c in comps), truth
            continue
        best = max(comps, key=lambda c: irm.iou(c["bbox"], truth["bbox"]))
        assert irm.iou(best["bbox"], truth["bbox"]) > 0.5, truth
        assert best["type"] == truth["type"], (truth, best)
    # the gapped (non-closed) email rectangle is still found as an input
    card = next(c for c in comps if c["type"] == "card")
    inner = [c for c in comps if c.get("parent") == comps.index(card)]
    assert len(inner) >= 6


def test_detect_cv_shapes(fixture_png):
    cands = sketch.detect_cv(fixture_png)
    shapes = {c["shape"] for c in cands}
    assert {"rect", "cross_box", "text"} <= shapes
    assert all(0 <= c["bbox"]["x"] <= 1 and 0 < c["bbox"]["w"] <= 1 for c in cands)
