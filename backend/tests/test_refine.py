"""The 7 brief commands (§4.4) as Ops applied to a hand-built login IR, with exact assertions."""
import copy
import json

from app.pipeline import refine
from app.pipeline import ir as irm


def ids(ir):
    return [n["id"] for n, _, _ in irm.walk(ir)]


def children(ir, node_id):
    return [c["id"] for c in irm.find(ir, node_id)[0]["children"]]


def dump(node):
    return json.dumps(node, sort_keys=True)


def test_create_login_page():
    empty = irm.new_ir("Untitled")
    op = {"op": "create", "meta": {"title": "Login", "category": "login"}, "components": [
        {"type": "heading", "label": "Login", "props": {"level": 1}},
        {"type": "input", "label": "Email", "props": {"inputType": "email", "required": True}},
        {"type": "input", "label": "Password", "props": {"inputType": "password", "required": True}},
        {"type": "button", "label": "Login"}]}
    out = refine.apply_ops(empty, [op])
    ir = out["ir"]
    assert out["changes"][0]["ok"]
    assert ir["meta"]["title"] == "Login"
    assert ids(ir) == ["page_main", "h_login", "form_5", "inp_email", "inp_password", "btn_login"]
    assert irm.find(ir, "inp_password")[0]["props"]["inputType"] == "password"
    assert irm.find(ir, "btn_login")[1]["type"] == "form"


def test_add_forgot_password_link_below_login_button(login_ir):
    op = {"op": "add", "component": {"type": "link", "label": "Forgot password?"},
          "position": {"relation": "below", "anchor": {"ref": "login button", "id": None}}}
    out = refine.apply_ops(login_ir, [op])
    assert out["changes"] == [{"op": "add", "target": "lnk_forgot_password",
                               "detail": "added link 'Forgot password?' below btn_login", "ok": True}]
    assert children(out["ir"], "form_login") == ["inp_email", "inp_password", "btn_login", "lnk_forgot_password"]
    link = irm.find(out["ir"], "lnk_forgot_password")[0]
    assert link["relations"] == [{"type": "below", "target": "btn_login"}]


def test_make_login_button_blue(login_ir):
    out = refine.apply_ops(login_ir, [{"op": "style", "target": {"ref": "login button"}, "changes": {"style": {"color": "blue"}}}])
    assert irm.find(out["ir"], "btn_login")[0]["style"] == {"color": "#2563eb"}
    assert out["changes"][0]["ok"] and out["changes"][0]["target"] == "btn_login"
    # every other node is byte-identical
    for nid in ("h_login", "img_logo", "inp_email", "inp_password"):
        assert dump(irm.find(out["ir"], nid)[0]) == dump(irm.find(login_ir, nid)[0])
    assert irm.find(login_ir, "btn_login")[0]["style"] == {}, "input IR must not be mutated"


def test_move_button_below_password(login_ir):
    # put the button first so the move is visible
    ir = copy.deepcopy(login_ir)
    form = irm.find(ir, "form_login")[0]
    form["children"] = [form["children"][2], form["children"][0], form["children"][1]]
    out = refine.apply_ops(ir, [{"op": "move", "target": {"ref": "the button"},
                                 "position": {"relation": "below", "anchor": {"ref": "password"}}}])
    assert out["changes"][0]["ok"]
    assert children(out["ir"], "form_login") == ["inp_email", "inp_password", "btn_login"]


def test_add_phone_field_below_email(login_ir):
    op = {"op": "add", "component": {"type": "input", "label": "Phone"},
          "position": {"relation": "below", "anchor": {"ref": "email field"}}}
    out = refine.apply_ops(login_ir, [op])
    assert children(out["ir"], "form_login") == ["inp_email", "inp_phone", "inp_password", "btn_login"]
    assert irm.find(out["ir"], "inp_phone")[0]["props"] == {"inputType": "tel"}


def test_remove_the_image(login_ir):
    out = refine.apply_ops(login_ir, [{"op": "remove", "target": {"ref": "the image"}}])
    assert out["changes"][0] == {"op": "remove", "target": "img_logo", "detail": "removed image ''", "ok": True}
    assert "img_logo" not in ids(out["ir"])
    assert children(out["ir"], "page_main") == ["h_login", "form_login"]


def test_error_on_login_click_with_empty_fields(login_ir):
    op = {"op": "interaction", "target": {"ref": "login button"},
          "event": {"on": "click", "actions": [{"type": "validate_required", "message": "Please fill in all fields"}]}}
    out = refine.apply_ops(login_ir, [op])
    assert irm.find(out["ir"], "btn_login")[0]["events"] == [{"on": "click", "actions": [
        {"type": "validate_required", "targets": ["inp_email", "inp_password"], "message": "Please fill in all fields"}]}]


def test_navigation_creates_page_and_validation_runs_first(login_ir):
    ops = [{"op": "navigation", "target": {"ref": "login button"}, "page": {"name": "Dashboard"}},
           {"op": "interaction", "target": {"ref": "login button"},
            "event": {"on": "click", "actions": [{"type": "validate_required"}]}}]
    out = refine.apply_ops(login_ir, ops)
    ir = out["ir"]
    assert [p["id"] for p in ir["pages"]] == ["page_main", "page_dashboard"]
    actions = irm.find(ir, "btn_login")[0]["events"][0]["actions"]
    assert [a["type"] for a in actions] == ["validate_required", "navigate"]
    assert irm.find(ir, "btn_login")[0]["props"]["href_page"] == "page_dashboard"


def test_resize_and_unknown_target(login_ir):
    out = refine.apply_ops(login_ir, [{"op": "resize", "target": {"ref": "heading"}, "scale": 1.5},
                                      {"op": "remove", "target": {"ref": "video player"}}])
    assert irm.find(out["ir"], "h_login")[0]["style"] == {"size": "lg", "fontSize": 42}
    assert out["changes"][1]["ok"] is False and "not found" in out["changes"][1]["error"]


def test_resolve_target(login_ir):
    assert refine.resolve_target(login_ir, "email field")["id"] == "inp_email"
    assert refine.resolve_target(login_ir, "password")["id"] == "inp_password"
    assert refine.resolve_target(login_ir, "the second field")["id"] == "inp_password"
    assert refine.resolve_target(login_ir, "last input")["id"] == "inp_password"
    assert refine.resolve_target(login_ir, "the title")["id"] == "h_login"
    assert refine.resolve_target(login_ir, "btn_login") == {"id": "btn_login", "score": 1.0}
    assert refine.resolve_target(login_ir, "shopping cart")["id"] is None


def test_color_words():
    assert refine.normalize_color("blue") == "#2563eb"
    assert refine.normalize_color("dark green colour") == "#166534"
    assert refine.normalize_color("#ABC") == "#abc"
