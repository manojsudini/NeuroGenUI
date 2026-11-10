from app.pipeline import fusion
from app.pipeline import ir as irm


def box(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


ANALYSIS = {"width": 1000, "height": 1000, "components": [
    {"type": "card", "label": "", "bbox": box(0.3, 0.1, 0.4, 0.7), "parent": None},
    {"type": "heading", "label": "Sign in", "bbox": box(0.42, 0.15, 0.16, 0.05), "parent": 0},
    {"type": "text", "label": "Email", "bbox": box(0.33, 0.24, 0.08, 0.03), "parent": 0},
    {"type": "input", "label": "", "bbox": box(0.33, 0.28, 0.34, 0.06), "parent": 0},
    {"type": "input", "label": "", "bbox": box(0.33, 0.38, 0.34, 0.06), "parent": 0},
    {"type": "button", "label": "Cancel", "bbox": box(0.33, 0.5, 0.15, 0.06), "parent": 0},
    {"type": "button", "label": "Go", "bbox": box(0.52, 0.5, 0.15, 0.06), "parent": 0},
]}
CREATE = {"op": "create", "meta": {"title": "Sign in", "category": "login"}, "components": [
    {"type": "input", "label": "Email", "props": {"inputType": "email", "required": True}},
    {"type": "input", "label": "Password", "props": {"inputType": "password"}},
    {"type": "button", "label": "Log in", "events": [{"on": "click", "actions": [{"type": "validate_required"}]}]},
    {"type": "link", "label": "Forgot password?"},
]}


def test_sketch_structure_and_voice_semantics():
    ir = fusion.fuse(ANALYSIS, [CREATE])
    outline = [(n["type"], n["label"]) for n, _, _ in irm.walk(ir)]
    # the card with fields becomes the container; "Email" text is absorbed as the first field's label
    assert ("text", "Email") not in outline
    email = irm.find(ir, "inp_email")[0]
    assert email["props"] == {"inputType": "email", "required": True} and email["bbox"] is not None
    password = irm.find(ir, "inp_password")[0]
    assert password["props"]["inputType"] == "password" and password["origin"] == "sketch"
    # the two buttons drawn side by side form a row container
    row = irm.find(ir, "btn_cancel")[1]
    assert row["layout"]["direction"] == "row"
    assert {c["type"] for c in row["children"]} == {"button"}
    # the spoken "Log in" button matched a drawn button: the handwriting stays, the voice behaviour is merged
    clicks = [n for n, _, _ in irm.walk(ir) if n["events"]]
    assert len(clicks) == 1 and clicks[0]["label"] in ("Cancel", "Go")
    assert clicks[0]["events"][0]["actions"][0]["targets"] == ["inp_email", "inp_password"]
    # the unmatched voice link is inserted after the voice component spoken before it
    labels = [n["label"] for n, _, _ in irm.walk(ir)]
    assert labels.index("Forgot password?") > labels.index(clicks[0]["label"])
    assert ir["meta"]["title"] == "Sign in"


def test_voice_only_wraps_form():
    ir = fusion.fuse(None, [CREATE])
    root = ir["pages"][0]["root"]
    assert root["children"][0]["type"] == "form"
    assert [c["type"] for c in root["children"][0]["children"]] == ["input", "input", "button", "link"]


def test_sketch_only_keeps_everything():
    ir = fusion.fuse(ANALYSIS, [])
    types = [n["type"] for n, _, _ in irm.walk(ir)]
    assert types.count("input") == 2 and types.count("button") == 2 and "heading" in types
    assert ids_unique(ir)


def ids_unique(ir):
    all_ids = [n["id"] for n, _, _ in irm.walk(ir)]
    return len(all_ids) == len(set(all_ids))
