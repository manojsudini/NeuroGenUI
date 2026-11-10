"""Relative resize semantics, intent post-processing and snapshot-based repair."""
import copy

import pytest

from app.pipeline import codegen, fusion, intent, refine, repair, validate
from app.pipeline import ir as irm


def _node(login_ir, nid):
    return irm.find(login_ir, nid)[0]


# --------------------------------------------------------------------------- resize phrases

@pytest.mark.parametrize("text,scale,axis,full", [
    ("Make the login button bigger.", 1.3, "both", False),
    ("the sign in button should be a bit bigger", 1.15, "both", False),
    ("make the heading a lot smaller", 0.6, "both", False),
    ("Make the search box wider", 1.3, "width", False),
    ("make the message box much taller", 1.6, "height", False),
    ("make it twice as wide", 2.0, "width", False),
    ("make the image half the size", 0.5, "both", False),
    ("make the photo 20% bigger", 1.2, "both", False),
    ("make the button narrower", 0.75, "width", False),
    ("Make the Create account button full-width.", None, "width", True),
    ("stretch the input edge to edge", None, "both", True),
])
def test_parse_resize_phrase(text, scale, axis, full):
    hint = refine.parse_resize_phrase(text)
    assert hint["scale"] == scale and hint["axis"] == axis and hint["full_width"] is full


def test_parse_resize_phrase_ignores_other_commands():
    assert refine.parse_resize_phrase("Make the page purple") is None
    assert refine.parse_resize_phrase("Add a forgot password link below the login button") is None


# --------------------------------------------------------------------------- intent post-processing

def test_style_width_full_becomes_resize():
    ops = [{"op": "style", "target": {"ref": "button"}, "changes": {"style": {"width": "full"}}}]
    intent._normalise_resize(ops, "Make the Create account button full width.")
    assert ops[0]["op"] == "resize" and ops[0]["changes"]["style"] == {"width": "full"}


def test_wider_uses_a_factor_on_the_width_axis():
    ops = [{"op": "style", "target": {"ref": "search box"}, "changes": {"style": {"width": "full"}}}]
    intent._normalise_resize(ops, "Make the search box wider.")
    assert ops[0] == {"op": "resize", "target": {"ref": "search box"}, "scale": 1.3, "axis": "width"}


def test_rows_guess_is_replaced_by_the_stated_factor():
    ops = [{"op": "resize", "target": {"ref": "message box"}, "changes": {"props": {"rows": 8}}}]
    intent._normalise_resize(ops, "Make the message box taller.")
    assert ops[0]["scale"] == 1.3 and ops[0]["axis"] == "height" and "changes" not in ops[0]


def test_two_resizes_keep_the_model_factors():
    ops = [{"op": "resize", "target": {"ref": "logo"}, "scale": 2.0},
           {"op": "resize", "target": {"ref": "subtitle"}, "scale": 0.87}]
    intent._normalise_resize(ops, "Make the logo twice as big and the subtitle a bit smaller")
    assert [o["scale"] for o in ops] == [2.0, 0.87]


def test_ir_summary_flags_shared_labels_and_order(login_ir):
    ir = copy.deepcopy(login_ir)
    form = _node(ir, "form_login")
    form["children"].insert(0, {**copy.deepcopy(_node(ir, "h_login")), "id": "txt_email", "type": "text", "label": "Email"})
    _node(ir, "btn_login")["style"] = {"width": 200}
    text = intent.ir_summary(ir)
    assert "btn_login | button | 'Login' [width=200]" in text
    assert "inputs in reading order: inp_email, inp_password" in text
    assert "label 'email' is shared by txt_email (text), inp_email (input)" in text


# --------------------------------------------------------------------------- apply_ops resize

def test_scale_width_of_a_drawn_input(login_ir):
    login_ir["meta"]["frame"] = {"page_width": 800, "scale": 1.0, "sketch_width": 1000, "sketch_height": 800,
                                 "content": {"x": 0, "y": 0, "w": 1.0, "h": 1.0}}
    _node(login_ir, "inp_email")["bbox"] = {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05}
    out = refine.apply_ops(login_ir, [{"op": "resize", "target": {"id": "inp_email"}, "scale": 1.3, "axis": "width"}])
    assert _node(out["ir"], "inp_email")["style"]["width"] == 390  # 0.3 * 1000 * 1.3
    out = refine.apply_ops(out["ir"], [{"op": "resize", "target": {"id": "inp_email"}, "scale": 0.5, "axis": "width"}])
    assert _node(out["ir"], "inp_email")["style"]["width"] == 195
    big = refine.apply_ops(login_ir, [{"op": "resize", "target": {"id": "inp_email"}, "scale": 3.0, "axis": "width"}])
    assert _node(big["ir"], "inp_email")["style"]["width"] == "full"  # would not fit the page


def test_scale_height_and_both(login_ir):
    st = _node(refine.apply_ops(login_ir, [{"op": "resize", "target": {"id": "btn_login"}, "scale": 2.0, "axis": "height"}])["ir"],
               "btn_login")["style"]
    assert st["height"] == 80 and "fontSize" not in st  # default button height 40
    st = _node(refine.apply_ops(login_ir, [{"op": "resize", "target": {"id": "btn_login"}, "scale": 1.15}])["ir"],
               "btn_login")["style"]
    assert st["height"] == 46 and st["fontSize"] == 17 and "size" not in st  # small step: no size word jump


def test_full_width_and_textarea_rows(login_ir):
    out = refine.apply_ops(login_ir, [{"op": "resize", "target": {"id": "btn_login"}, "changes": {"style": {"width": "full"}}}])
    assert _node(out["ir"], "btn_login")["style"]["width"] == "full"
    ta = copy.deepcopy(login_ir)
    _node(ta, "form_login")["children"].append({**copy.deepcopy(_node(ta, "inp_email")), "id": "ta_msg", "type": "textarea",
                                               "label": "Message", "props": {"rows": 4}})
    out = refine.apply_ops(ta, [{"op": "resize", "target": {"ref": "message box"}, "scale": 1.5, "axis": "height"}])
    assert _node(out["ir"], "ta_msg")["props"]["rows"] == 6


def test_size_word_on_an_image_changes_its_height(login_ir):
    _node(login_ir, "img_logo")["style"] = {"height": 160}
    out = refine.apply_ops(login_ir, [{"op": "resize", "target": {"id": "img_logo"}, "changes": {"style": {"size": "sm"}}}])
    assert _node(out["ir"], "img_logo")["style"]["height"] == 112


# --------------------------------------------------------------------------- target repair

def test_text_caption_becomes_the_field_when_no_input_exists(login_ir):
    form = _node(login_ir, "form_login")
    form["children"] = [{**_node(login_ir, "h_login"), "id": "txt_phone", "type": "text", "label": "Phone number", "props": {}}]
    out = refine.apply_ops(login_ir, [{"op": "modify", "target": {"ref": "phone field", "id": "txt_phone"},
                                       "changes": {"props": {"placeholder": "555 0100"}}}])
    node = _node(out["ir"], "txt_phone")
    assert out["changes"][0]["ok"] and node["type"] == "input"
    assert node["props"]["placeholder"] == "555 0100" and node["props"]["inputType"] == "tel"


def test_plural_anchor_means_the_whole_option_group(login_ir):
    form = _node(login_ir, "form_login")
    opts = [{**_node(login_ir, "inp_email"), "id": f"rad_{i}", "type": "radio", "label": f"Slot {i}", "props": {}} for i in range(3)]
    form["children"][2:2] = opts  # email, password, radios..., login
    out = refine.apply_ops(login_ir, [{"op": "move", "target": {"id": "inp_email"},
                                       "position": {"relation": "below", "anchor": {"ref": "slots", "id": "rad_0"}}}])
    order = [c["id"] for c in _node(out["ir"], "form_login")["children"]]
    assert order.index("inp_email") == order.index("rad_2") + 1


def test_remove_records_ids_for_the_validator(login_ir):
    out = refine.apply_ops(login_ir, [{"op": "remove", "target": {"id": "form_login"}}])
    assert {"form_login", "inp_email", "btn_login"} <= set(out["ir"]["meta"]["removed_ids"])


# --------------------------------------------------------------------------- snapshot repair (browser)

def _analysis(fixture_truth):
    return {"width": fixture_truth["width"], "height": fixture_truth["height"], "components": fixture_truth["components"]}


def test_validator_flags_what_vanished_since_the_snapshot(fixture_truth):
    ir = fusion.fuse(_analysis(fixture_truth), [])
    broken = copy.deepcopy(ir)
    button = next(n for n, _, _ in irm.walk(broken) if n["type"] == "button")
    irm.find(broken, button["id"])[1]["children"].remove(button)
    report = validate.validate(broken, codegen.generate_code(broken)["preview"], None, reference=ir)
    assert f"missing:{button['id']}" in [c["id"] for c in report["checks"] if not c["ok"]]
    # a user removal is not a defect
    removed = refine.apply_ops(ir, [{"op": "remove", "target": {"id": button["id"]}}])["ir"]
    report = validate.validate(removed, codegen.generate_code(removed)["preview"], None, reference=ir)
    assert not [c for c in report["checks"] if c["id"].startswith("missing:")]


def test_repair_restores_a_node_from_the_snapshot_without_a_sketch(fixture_truth):
    ir = fusion.fuse(_analysis(fixture_truth), [])
    broken = copy.deepcopy(ir)
    target = next(n for n, _, _ in irm.walk(broken) if n["type"] == "input")
    parent = irm.find(broken, target["id"])[1]
    slot = [c["id"] for c in parent["children"]].index(target["id"])
    parent["children"].remove(target)
    result = repair.repair_loop(broken, None, reference=ir)
    assert any(r["action"] == "restore_from_snapshot" and r["result"] == "fixed" for r in result["repairs"])
    new_parent = irm.find(result["ir"], target["id"])[1]
    assert new_parent["id"] == parent["id"] and [c["id"] for c in new_parent["children"]].index(target["id"]) == slot
    assert result["report"]["passed"]


def test_repair_unhides_without_duplicating(fixture_truth):
    analysis = _analysis(fixture_truth)
    ir = fusion.fuse(analysis, [])
    broken = copy.deepcopy(ir)
    target = next(n for n, _, _ in irm.walk(broken) if n["type"] == "button")
    target["style"] = {**target.get("style", {}), "hidden": True}
    before = len([n for n, _, _ in irm.walk(ir)])
    result = repair.repair_loop(broken, analysis)
    assert len([n for n, _, _ in irm.walk(result["ir"])]) == before  # no duplicate re-inserted next to the hidden node
    assert not irm.is_hidden(result["ir"], target["id"])


def test_repair_resets_a_collapsed_size(fixture_truth):
    analysis = _analysis(fixture_truth)
    ir = fusion.fuse(analysis, [])
    broken = copy.deepcopy(ir)
    target = next(n for n, _, _ in irm.walk(broken) if n["type"] == "button")
    target["style"] = {**target.get("style", {}), "width": 0, "height": 0}
    report = validate.validate(broken, codegen.generate_code(broken)["preview"], analysis)
    assert f"size:{target['id']}" in [c["id"] for c in report["checks"] if not c["ok"]]
    result = repair.repair_loop(broken, analysis)
    assert result["report"]["passed"]
    assert result["ir"] and irm.find(result["ir"], target["id"])[0]["style"].get("width") != 0


# --------------------------------------------------------------------------- misc

def test_navigate_only_interaction_is_a_navigation_op():
    op = {"op": "interaction", "target": {"ref": "Cancel", "id": None}, "confidence": 0.9,
          "event": {"on": "click", "actions": [{"type": "navigate", "page": "Home"}]}}
    out = intent._clean_op(op, None)
    assert out["op"] == "navigation" and out["page"] == {"name": "Home"} and "event" not in out
    mixed = {"op": "interaction", "target": {"ref": "Login"}, "event": {"on": "click", "actions": [
        {"type": "show_message", "text": "Hi"}, {"type": "navigate", "page": "Home"}]}}
    assert intent._clean_op(mixed, None)["op"] == "interaction"


def test_coverage_repair_labels_a_checkbox_with_its_caption():
    analysis = {"width": 1000, "height": 800, "components": [
        {"type": "checkbox", "label": "", "bbox": {"x": 0.1, "y": 0.5, "w": 0.03, "h": 0.04}, "confidence": 1, "source": "gt", "parent": None},
        {"type": "text", "label": "Remember me", "bbox": {"x": 0.15, "y": 0.5, "w": 0.2, "h": 0.04}, "confidence": 1, "source": "gt", "parent": None}]}
    assert repair._caption(analysis, analysis["components"][0]) == "Remember me"
    ir = irm.new_ir("t")
    assert not repair._covered(ir, analysis["components"][0])
