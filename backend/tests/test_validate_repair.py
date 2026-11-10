import copy

from app.pipeline import codegen, fusion, repair, validate
from app.pipeline import ir as irm


def test_generated_ui_passes(login_ir):
    btn = irm.find(login_ir, "btn_login")[0]
    btn["events"] = [{"on": "click", "actions": [
        {"type": "validate_required", "targets": ["inp_email", "inp_password"], "message": "Please fill in all fields"},
        {"type": "show_message", "text": "Welcome back", "tone": "success"}]}]
    code = codegen.generate_code(login_ir)
    report = validate.validate(login_ir, code["preview"])
    assert report["passed"], [c for c in report["checks"] if not c["ok"]]
    assert report["visual"]["presence"] == 1.0
    assert report["functional"]["interactions_total"] == 1 and report["functional"]["interactions_passed"] == 1
    assert report["screenshot_b64"] and report["duration_ms"] < 10000
    assert {d["id"] for d in report["dom"]} >= {"btn_login", "inp_email", "page_main"}


def test_broken_ui_is_caught(login_ir):
    code = codegen.generate_code(login_ir)["preview"].replace("function Button(", "function Butt0n(")
    report = validate.validate(login_ir, code)
    assert not report["passed"]
    assert any("Button is not defined" in e for e in report["functional"]["runtime_errors"])


def test_missing_handler_is_caught(login_ir):
    btn = irm.find(login_ir, "btn_login")[0]
    btn["events"] = [{"on": "click", "actions": [{"type": "validate_required", "targets": ["inp_email"], "message": "x"}]}]
    code = codegen.generate_code(login_ir)["preview"].replace("onClick={handleBtnLoginClick}", "")
    report = validate.validate(login_ir, code)
    failed = [c["id"] for c in report["checks"] if not c["ok"]]
    assert "event:btn_login:click" in failed


def test_extract_dom(login_ir):
    dom = validate.extract_dom(codegen.generate_code(login_ir)["preview"])
    found = {(c["type"], c["label"]) for c in dom["components"]}
    assert {("heading", "Login"), ("input", "Email"), ("input", "Password"), ("button", "Login")} <= found
    assert dom["errors"] == []


def test_repair_restores_removed_node(fixture_truth):
    analysis = {"width": fixture_truth["width"], "height": fixture_truth["height"],
                "components": fixture_truth["components"]}
    ir = fusion.fuse(analysis, [])
    broken = copy.deepcopy(ir)
    button = next(n for n, _, _ in irm.walk(broken) if n["type"] == "button")
    irm.find(broken, button["id"])[1]["children"].remove(button)  # node lost (not a user removal)
    result = repair.repair_loop(broken, analysis)
    assert result["report"]["passed"], [c for c in result["report"]["checks"] if not c["ok"]]
    assert any(r["action"] == "reinsert_from_sketch" and r["result"] == "fixed" for r in result["repairs"])
    restored = [n for n, _, _ in irm.walk(result["ir"]) if n["type"] == "button"]
    assert restored and restored[0]["label"] == "Login" and restored[0]["origin"] == "repair"


def test_repair_reorders_siblings(fixture_truth):
    analysis = {"width": fixture_truth["width"], "height": fixture_truth["height"],
                "components": fixture_truth["components"]}
    ir = fusion.fuse(analysis, [])
    card = next(n for n, _, _ in irm.walk(ir) if n["type"] in ("card", "form"))
    card["children"].reverse()
    result = repair.repair_loop(ir, analysis)
    assert result["report"]["passed"]
    assert any(r["action"] == "reorder_siblings" for r in result["repairs"])


def test_user_removal_is_not_undone(fixture_truth):
    from app.pipeline import refine
    analysis = {"width": fixture_truth["width"], "height": fixture_truth["height"],
                "components": fixture_truth["components"]}
    ir = refine.apply_ops(fusion.fuse(analysis, []), [{"op": "remove", "target": {"ref": "the image"}}])["ir"]
    report = validate.validate(ir, codegen.generate_code(ir)["preview"], analysis)
    assert report["passed"], [c for c in report["checks"] if not c["ok"]]


def test_user_move_is_kept_and_not_duplicated(fixture_truth):
    from app.pipeline import refine
    analysis = {"width": fixture_truth["width"], "height": fixture_truth["height"],
                "components": fixture_truth["components"]}
    ir = fusion.fuse(analysis, [])
    button = next(n["id"] for n, _, _ in irm.walk(ir) if n["type"] == "button")
    heading = next(n["id"] for n, _, _ in irm.walk(ir) if n["type"] == "heading")
    moved = refine.apply_ops(ir, [{"op": "move", "target": {"id": button, "ref": "button"},
                                   "position": {"relation": "below", "anchor": {"id": heading, "ref": "heading"}}}])["ir"]
    result = repair.repair_loop(moved, analysis)
    assert result["report"]["passed"] and result["repairs"] == []
    buttons = [n["id"] for n, _, _ in irm.walk(result["ir"]) if n["type"] == "button"]
    assert buttons == [button]
    siblings = [c["id"] for c in irm.find(result["ir"], button)[1]["children"]]
    assert siblings.index(button) == siblings.index(heading) + 1
