"""Rules that turn raw detections into wireframe vocabulary (sketch_refine) and the OCR merge in sketch.py."""
import cv2
import numpy as np

from app.pipeline import codegen, fusion, ocr, sketch
from app.pipeline import sketch_refine as rr

SIZE = (1000, 600)


def comp(kind, x, y, w, h, label="", **extra):
    return {"type": kind, "label": label, "bbox": {"x": x, "y": y, "w": w, "h": h}, "confidence": 0.9,
            "source": "hybrid", **extra}


def types(components):
    return [c["type"] for c in components]


def test_checkbox_and_its_option_text_are_one_component():
    out = rr.attach_marker_labels([comp("checkbox", 0.30, 0.50, 0.03, 0.05, shape="rect"),
                                   comp("text", 0.35, 0.51, 0.20, 0.04, "Remember me", shape="text")], SIZE)
    assert len(out) == 1 and out[0]["type"] == "checkbox" and out[0]["label"] == "Remember me"
    assert out[0]["bbox"]["w"] > 0.24  # mark + text


def test_radio_mark_swallowed_by_an_ocr_line_is_recovered():
    out = rr.attach_marker_labels([comp("radio", 0.22, 0.46, 0.025, 0.04, shape="circle"),
                                   comp("heading", 0.218, 0.454, 0.077, 0.045, "OLow", shape="text", ocr=True)], SIZE)
    assert len(out) == 1 and out[0]["type"] == "radio" and out[0]["label"] == "Low"


def test_lone_circle_beside_a_title_stays_an_icon():
    out = rr.attach_marker_labels([comp("icon", 0.39, 0.18, 0.03, 0.05, shape="circle"),
                                   comp("heading", 0.43, 0.17, 0.2, 0.12, "Login", shape="text")], SIZE)
    assert sorted(types(out)) == ["heading", "icon"]


def test_chevron_inside_input_makes_it_a_select_and_disappears():
    field = comp("input", 0.2, 0.3, 0.5, 0.09, "Choose")
    chevron = comp("icon", 0.65, 0.33, 0.025, 0.02)
    out = rr.field_adornments([field, chevron], SIZE)
    assert types(out) == ["select"]


def test_top_bar_with_menu_is_a_navbar_and_plain_boxes_are_cards():
    bar = comp("container", 0.05, 0.05, 0.9, 0.12)
    items = [comp("text", 0.1 + 0.2 * i, 0.09, 0.1, 0.05, w, shape="text", ocr=True) for i, w in enumerate(["Brand", "Home", "About"])]
    box = comp("container", 0.1, 0.4, 0.3, 0.3)
    inner = comp("text", 0.12, 0.45, 0.1, 0.05, "Hi", shape="text", ocr=True)
    out = rr.refine_structure([bar, *items, box, inner], SIZE)
    kinds = {c["label"] or c["bbox"]["y"]: c["type"] for c in out}
    assert kinds[0.05] == "navbar" and kinds[0.4] == "card"
    assert [c["type"] for c in out if c["label"] in ("Home", "About")] == ["nav_item", "nav_item"]


def test_title_size_decides_between_heading_and_text():
    big = comp("text", 0.1, 0.1, 0.3, 0.09, "Welcome", shape="text", ocr=True)   # 54 px tall
    small = comp("heading", 0.1, 0.3, 0.2, 0.045, "caption", shape="text", ocr=True)  # 27 px
    rr.retype_text([big, small], SIZE)
    assert (big["type"], small["type"]) == ("heading", "text")


def test_caption_inside_the_column_of_sibling_fields_gets_its_missing_box():
    fields = [comp("input", 0.25, 0.20, 0.5, 0.09, "Name"), comp("input", 0.25, 0.50, 0.5, 0.09, "Password")]
    orphan = comp("text", 0.262, 0.355, 0.1, 0.04, "Email", shape="text", ocr=True)
    out = rr.complete_fields([*fields, orphan], SIZE)
    emails = [c for c in out if c["label"] == "Email"]
    assert len(emails) == 1 and emails[0]["type"] == "input" and abs(emails[0]["bbox"]["w"] - 0.5) < 1e-6


def test_caption_above_a_field_is_not_turned_into_a_field():
    fields = [comp("input", 0.25, 0.30, 0.5, 0.09, "Name")]
    caption = comp("text", 0.25, 0.24, 0.1, 0.04, "Name", shape="text", ocr=True)  # flush with the box edge, right above
    out = rr.complete_fields([*fields, caption], SIZE)
    assert sorted(types(out)) == ["input", "text"]


def test_underline_under_text_is_a_link_not_a_divider():
    text = comp("text", 0.3, 0.5, 0.2, 0.05, "Forgot password?", shape="text")
    line = comp("divider", 0.3, 0.555, 0.2, 0.01, shape="line")
    out = rr.underlines_are_decoration([text, line])
    assert types(out) == ["link"]


def test_list_items_fold_into_the_list():
    lst = comp("list", 0.1, 0.4, 0.3, 0.2, shape="list")
    a, b = comp("text", 0.12, 0.42, 0.2, 0.05, "One"), comp("text", 0.12, 0.5, 0.2, 0.05, "Two")
    out = rr.absorb_list_items([lst, a, b])
    assert types(out) == ["list"] and out[0]["items"] == ["One", "Two"]
    ir = fusion.fuse({"components": out, "width": 1000, "height": 600, "mode": "cv", "timings": {}}, [], title="t")
    node = next(n for n, _, _ in __import__("app.pipeline.ir", fromlist=["walk"]).walk(ir) if n["type"] == "list")
    assert node["props"]["items"] == ["One", "Two"]


def test_ocr_lines_split_on_wide_spaces_and_fill_gaps():
    def cand(x, y, w, h):
        return {"bbox": sketch._norm((x, y, w, h), 1000, 600), "px": (x, y, w, h), "shape": "text", "area": w * h,
                "aspect": w / h, "fill": 0.3, "conf": 0.6}
    cands = [cand(100, 100, 60, 25), cand(300, 100, 80, 25)]
    lines = [{"text": "Home   Reports", "score": 0.9, "px": (98, 96, 290, 32)},
             {"text": "Footer note", "score": 0.95, "px": (100, 500, 200, 30)}]
    out = sketch._merge_ocr(cands, lines, 1000, 600)
    assert sorted(c["text"] for c in out) == ["Footer note", "Home", "Reports"]


def test_text_lines_keep_widely_spaced_items_apart():
    mask = np.zeros((100, 700), np.uint8)
    for x in (20, 45, 70, 95):            # one word: letters 5 px apart
        mask[30:55, x:x + 20] = 255
    for x in (400, 425):                  # a second item far to the right
        mask[30:55, x:x + 20] = 255
    lines = sketch._text_lines(mask)
    assert len(lines) == 2


def test_bullets_make_a_list():
    lines = [(40, 100, 120, 24), (40, 140, 120, 24)]
    specks = [(20, 108, 9, 9), (20, 148, 9, 9)]
    boxes, rest = sketch._bullet_lists(lines, np.zeros((300, 300), np.uint8), specks)
    assert len(boxes) == 1 and rest == [] and boxes[0][0] <= 20


def test_ocr_is_optional(monkeypatch):
    monkeypatch.setenv("NGUI_OCR", "0")
    assert ocr.read_lines(np.zeros((50, 50, 3), np.uint8)) is None
    # and the analysis still works without it
    img = np.full((300, 600, 3), 255, np.uint8)
    cv2.rectangle(img, (100, 100), (400, 180), (30, 30, 30), 3)
    out = sketch.analyze_sketch(cv2.imencode(".png", img)[1].tobytes(), mode="cv", overlay=False)
    assert out["components"]


def test_geometry_keeps_divider_and_small_control_rows(login_ir):
    ir = {"schema": "neurogenui.ir/1"}
    an = {"components": [comp("heading", 0.1, 0.05, 0.3, 0.08, "Privacy"), comp("radio", 0.1, 0.2, 0.2, 0.09, "Public"),
                         comp("divider", 0.1, 0.4, 0.8, 0.04), comp("icon", 0.1, 0.5, 0.05, 0.08)],
          "width": 1000, "height": 600, "mode": "gt", "timings": {}}
    ir = fusion.fuse(an, [], title="t")
    code = codegen.generate_code(ir)["preview"]
    assert "paddingTop" in code and "minHeight" in code
