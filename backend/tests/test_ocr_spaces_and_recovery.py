"""OCR word spacing, notice-after-navigate, overlap-proof geometry, repair escalation and snapshot recovery in the orchestrator."""
import copy

import cv2
import numpy as np
import pytest

from app import db
from app.pipeline import codegen, ocr, orchestrator, refine, repair, validate
from app.pipeline import ir as irm
from tests.conftest import _node


# --------------------------------------------------------------------------- OCR spaces

def _line_image(words: list[str], gap: int = 14, glyph: int = 9, height: int = 20) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """White image with black bars standing in for letters: 1 px between letters, `gap` px between words."""
    img = np.full((height + 8, 600, 3), 255, np.uint8)
    x = 4
    for wi, word in enumerate(words):
        for _ in word:
            img[4:4 + height, x:x + glyph - 2] = 0
            x += glyph
        x += gap - 2 if wi < len(words) - 1 else 0
    return img, (0, 0, x + 4, height + 8)


def test_word_gaps_finds_only_the_wide_gap():
    img, px = _line_image(["Add", "to", "cart"])
    gaps, left, right = ocr.word_gaps(img, px)
    assert len(gaps) == 2 and all(ratio >= ocr.WORD_GAP for _, ratio in gaps)
    assert right > left


def test_insert_spaces_restores_multi_word_label():
    img, px = _line_image(["Add", "to", "cart"])
    gaps, left, right = ocr.word_gaps(img, px)
    assert ocr.insert_spaces("Addtocart", gaps, left, right) == "Add to cart"


def test_insert_spaces_leaves_single_words_and_numbers_alone():
    img, px = _line_image(["Send"], gap=14)
    assert ocr.insert_spaces("Send", [(18.0, 0.35)], 4, 40) == "Send"            # gap inside a known word, pieces are not words
    assert ocr.insert_spaces("$8,300", [(22.0, 0.35)], 2, 60) == "$8,300"         # gaps in a number
    assert ocr.insert_spaces("Hello", [], 4, 40) == "Hello"
    assert ocr.insert_spaces("Log out", [(20.0, 0.5)], 0, 40) == "Log out"        # already spaced


def test_wide_gap_wins_inside_a_known_compound():
    assert ocr.insert_spaces("Logout", [(14.0, 0.5)], 0, 40) == "Log out"


def test_one_letter_fragments_are_not_words():
    assert ocr.insert_spaces("Search", [(8.0, 0.33)], 0, 52) == "Search"


def test_tidy_spaces_joins_split_known_words():
    assert ocr.tidy_spaces("Sub scribe") == "Subscribe"
    assert ocr.tidy_spaces("Add to cart") == "Add to cart"


def test_description_vocabulary_places_the_cut():
    gaps = [(33.0, 0.4)]
    assert ocr.insert_spaces("Pickuppoint", gaps, 0, 66, vocab={"pickup", "point"}) == "Pickup point"


def test_hybrid_label_takes_the_ocr_spaces():
    from app.pipeline import sketch
    assert sketch.norm_label("Add to cart").replace(" ", "") == sketch.norm_label("Addtocart").replace(" ", "")


# --------------------------------------------------------------------------- message that survives navigation

def _two_page_ir(extra_events=None):
    button = _node("btn_buy", "button", "Buy", events=[{"on": "click", "actions": [
        {"type": "show_message", "text": "Added to cart", "tone": "success"}, {"type": "navigate", "page": "page_cart"}]}])
    home = _node("page_main", "page", "Main", children=[_node("h_home", "heading", "Shop", props={"level": 1}), button])
    cart = _node("page_cart", "page", "Cart", children=[_node("h_cart", "heading", "Your cart", props={"level": 1})])
    return {"schema": "neurogenui.ir/1", "meta": {"title": "Shop", "theme": {"primary": "#4f46e5", "radius": 10, "font": "Inter"}},
            "pages": [{"id": "page_main", "name": "Main", "route": "/", "root": home},
                      {"id": "page_cart", "name": "Cart", "route": "/cart", "root": cart}], "next_id": 5}


def test_show_message_then_navigate_is_still_visible():
    ir = _two_page_ir()
    code = codegen.generate_code(ir)
    assert "carry" in code["files"]["src/runtime/actions.js"] and "ui.notice" in code["files"]["src/App.jsx"]
    report = validate.validate(ir, code["preview"])
    event = next(c for c in report["checks"] if c["id"] == "event:btn_buy:click")
    assert event["ok"], event["detail"]
    assert report["passed"]


# --------------------------------------------------------------------------- geometry: no overflow into neighbours

FRAME = {"kind": "desktop", "sketch_width": 1000, "sketch_height": 600, "content": {"x": 0, "y": 0, "w": 1, "h": 1},
         "page_width": 1000, "scale": 1.0}


def _geo():
    return codegen.Geometry({"meta": {"frame": FRAME}}, set())


def test_natural_width_child_near_right_edge_keeps_room_for_its_label():
    child = _node("chk_x", "checkbox", "Check-out", bbox={"x": 0.62, "y": 0.2, "w": 0.023, "h": 0.04})
    frame = {"x": 0.5, "y": 0.1, "w": 0.15, "h": 0.2}  # 150 px wide
    style, _ = _geo().child_style(child, frame, "column", 0.1)
    offset = float(style["marginLeft"].rstrip("%")) / 100
    assert offset * 150 + 28 + 8 * len("Check-out") <= 150 + 1


def test_overlapping_row_children_may_shrink_but_not_collapse():
    a = _node("inp_a", "input", "A", bbox={"x": 0.0, "y": 0.1, "w": 0.6, "h": 0.1})
    style, _ = _geo().child_style(a, {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.5}, "row", 0.0)
    assert style["flex"] == "0 1 auto" and style["minWidth"] == 40


# --------------------------------------------------------------------------- repair: covered controls and escalation

def test_covered_typing_check_triggers_relayout():
    ir = _two_page_ir()
    ir["pages"][0]["root"]["children"].append(_node("chk_a", "checkbox", "A"))
    check = {"id": "typing:chk_a", "target": "chk_a", "detail": "covered: <select> intercepts pointer events", "hard": True, "ok": False}
    action, detail = repair._fix(ir, check, None, set(), {})
    assert action == "relayout" and "chk_a" in ir["meta"]["free_layout"]


def test_pw_detail_reports_covering_element():
    class Err(Exception):
        pass
    msg = "Locator.check: Timeout\nCall log:\n  - <select id='g'> from <section> subtree intercepts pointer events\n"
    assert validate._pw_detail(Err(msg)).startswith("covered: ")
    assert validate._pw_detail(Err("plain failure\nmore")) == "plain failure"


def test_escalation_widens_repair_when_targeted_fix_does_not_help(monkeypatch):
    ir = _two_page_ir()
    failing = {"id": "typing:btn_buy", "kind": "functional", "name": "x", "ok": False, "detail": "weird", "hard": True, "target": "btn_buy"}

    def fake_validate(ir_, preview, analysis=None, reference=None):
        free = set(ir_["meta"].get("free_layout", []))
        ok = free >= irm.all_ids(ir_)  # only the page-wide relayout clears it
        return {"passed": ok, "checks": [] if ok else [failing], "score": 1.0}

    monkeypatch.setattr(validate, "validate", fake_validate)
    monkeypatch.setattr(repair.validator, "validate", fake_validate)
    ir["meta"]["free_layout"] = []
    out = repair.repair_loop(ir, None, 4)
    actions = [r["action"] for r in out["repairs"]]
    assert actions[:3] == ["recompile_safe", "relayout", "relayout_page"] and out["report"]["passed"]
    assert [r["result"] for r in out["repairs"]][-1] == "fixed"


# --------------------------------------------------------------------------- snapshot recovery wired into the orchestrator

@pytest.fixture(autouse=True)
def _db():
    db.init()


def test_modify_restores_a_node_a_refinement_dropped(monkeypatch, login_ir):
    project = db.create_project("snap")
    pid = project["id"]
    code = codegen.generate_code(login_ir)
    db.save_version({"project_id": pid, "number": 1, "parent": None, "kind": "generate", "text": "", "source": "text", "ops": [],
                     "changes": [], "ir": login_ir, "ir_synced": True, "files": code["files"], "preview": code["preview"],
                     "code_stats": code["stats"], "sketch_id": None, "analysis": None, "validation": None, "repairs": [], "timings": {}})
    real_apply = refine.apply_ops

    def lossy_apply(base_ir, ops):  # a buggy refinement that silently loses the password field
        res = real_apply(base_ir, ops)
        form = irm.find(res["ir"], "form_login")[0]
        form["children"] = [c for c in form["children"] if c["id"] != "inp_password"]
        return res

    monkeypatch.setattr(refine, "apply_ops", lossy_apply)
    ops = [{"op": "style", "target": {"ref": "button", "id": "btn_login"}, "changes": {"style": {"color": "blue"}}}]
    version = orchestrator.run_modify(pid, "make the login button blue", ops=ops)
    assert irm.find(version["ir"], "inp_password")[0] is not None
    assert any(r["action"] == "restore_from_snapshot" for r in version["repairs"])
    assert version["validation"]["passed"]


def test_user_removal_is_not_restored(login_ir):
    project = db.create_project("snap2")
    pid = project["id"]
    code = codegen.generate_code(login_ir)
    db.save_version({"project_id": pid, "number": 1, "parent": None, "kind": "generate", "text": "", "source": "text", "ops": [],
                     "changes": [], "ir": login_ir, "ir_synced": True, "files": code["files"], "preview": code["preview"],
                     "code_stats": code["stats"], "sketch_id": None, "analysis": None, "validation": None, "repairs": [], "timings": {}})
    ops = [{"op": "remove", "target": {"ref": "password field", "id": "inp_password"}}]
    version = orchestrator.run_modify(pid, "remove the password field", ops=ops)
    assert irm.find(version["ir"], "inp_password")[0] is None
    assert not any(r["action"] == "restore_from_snapshot" for r in version["repairs"])


def test_reference_ir_only_for_modify_versions(login_ir):
    project = db.create_project("snap3")
    pid = project["id"]
    base = {"project_id": pid, "number": 1, "parent": None, "kind": "generate", "text": "", "source": "text", "ops": [], "changes": [],
            "ir": login_ir, "ir_synced": True, "files": {}, "preview": "", "code_stats": {}, "sketch_id": None, "analysis": None,
            "validation": None, "repairs": [], "timings": {}}
    db.save_version(base)
    assert orchestrator._reference_ir(pid, {"kind": "generate", "parent": 1}) is None
    assert orchestrator._reference_ir(pid, {"kind": "modify", "parent": 1})["meta"]["title"] == login_ir["meta"]["title"]
    assert orchestrator._reference_ir(pid, {"kind": "modify", "parent": None}) is None


# --------------------------------------------------------------------------- required dropdown without options

def _form_with_empty_select():
    form = _node("form_c", "form", children=[
        _node("sel_topic", "select", "Topic"),
        _node("btn_send", "button", "Send", events=[{"on": "click", "actions": [
            {"type": "validate_required", "targets": ["sel_topic"], "message": "Pick a topic."}]}])])
    root = _node("page_main", "page", "Main", children=[form])
    return {"schema": "neurogenui.ir/1", "meta": {"title": "T", "theme": {"primary": "#4f46e5", "radius": 10, "font": "Inter"}},
            "pages": [{"id": "page_main", "name": "Main", "route": "/", "root": root}], "next_id": 5}


def test_finalize_gives_empty_selects_options():
    from app.pipeline import fusion
    ir = _form_with_empty_select()
    notes = fusion.finalize_content(ir)
    assert irm.find(ir, "sel_topic")[0]["props"]["options"] == ["Option 1", "Option 2", "Option 3"] and notes


def test_repair_fixes_unfillable_required_select_and_ui_passes():
    ir = _form_with_empty_select()
    code = codegen.generate_code(ir)
    report = validate.validate(ir, code["preview"])
    assert not report["passed"]  # the validator cannot select anything in an empty dropdown
    fixed = repair.repair_loop(ir, None, 3, code, report)
    assert fixed["report"]["passed"] and any(r["action"] == "default_options" for r in fixed["repairs"])
