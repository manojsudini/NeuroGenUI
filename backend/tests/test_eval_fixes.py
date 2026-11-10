"""Regression tests for the defects found by the dataset evaluation (evaluation/BACKEND_ISSUES.md)."""
import copy

import pytest

from app.pipeline import codegen, fusion, refine, repair, sketch, validate
from app.pipeline import ir as irm


def box(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def comp(type_, label, b, parent=None):
    return {"type": type_, "label": label, "bbox": b, "parent": parent, "confidence": 1.0, "source": "test"}


def analysis(components, width=1000, height=800):
    return {"components": components, "width": width, "height": height}


def render(ir, an=None):
    return validate.validate(ir, codegen.generate_code(ir)["preview"], an)


def rect(report, node_id):
    return next(d["rect"] for d in report["dom"] if d["id"] == node_id)


def hard_failures(report):
    return [(c["id"], c["detail"]) for c in report["checks"] if c.get("hard", True) and not c["ok"]]


# --------------------------------------------------------------------------- 1. navigation

def test_navigation_page_only_inside_event(login_ir):
    op = {"op": "navigation", "target": {"ref": "login button", "id": "btn_login"},
          "event": {"on": "click", "actions": [{"type": "navigate", "page": "Home"}]}}
    out = refine.apply_ops(login_ir, [op])
    assert out["changes"][-1]["ok"], out["changes"]
    assert irm.find_page(out["ir"], "Home") is not None
    actions = irm.find(out["ir"], "btn_login")[0]["events"][0]["actions"]
    assert actions == [{"type": "navigate", "page": "page_home"}]


def test_navigation_keeps_other_event_actions(login_ir):
    op = {"op": "navigation", "target": {"ref": "login button"},
          "event": {"on": "click", "actions": [{"type": "validate_required"}, {"type": "navigate", "page": "Dashboard"}]}}
    out = refine.apply_ops(login_ir, [op])
    types = [a["type"] for a in irm.find(out["ir"], "btn_login")[0]["events"][0]["actions"]]
    assert types == ["validate_required", "navigate"]


# --------------------------------------------------------------------------- 2. empty components + repair

def test_fusion_never_emits_empty_components():
    an = analysis([comp("heading", "Recent orders", box(.1, .1, .3, .05)),
                   comp("list", "", box(.1, .2, .3, .2)),
                   comp("text", "", box(.1, .45, .4, .06))])
    voice = [{"op": "create", "components": [{"type": "container", "label": "Hero section",
                                              "children": [{"type": "heading", "label": "Recent orders"}]}]}]
    ir = fusion.fuse(an, voice)
    lst = irm.nodes(ir, "list")[0]
    assert lst["props"]["items"][:2] == ["Item 1", "Item 2"]
    assert all(n["label"] for n in irm.nodes(ir, "text"))
    assert not [n for n in irm.nodes(ir, "container") if not n.get("children")]
    report = render(ir, an)
    assert report["passed"], hard_failures(report)


def test_repair_fixes_invisible_nodes():
    an = analysis([comp("heading", "Orders", box(.1, .1, .3, .05)), comp("list", "", box(.1, .2, .3, .2)),
                   comp("text", "", box(.1, .45, .4, .06))])
    ir = fusion.fuse(an, [])
    broken = copy.deepcopy(ir)
    irm.nodes(broken, "list")[0]["props"].pop("items")
    irm.nodes(broken, "text")[0]["label"] = ""
    wrapper = irm.make_node(broken, "container", "", origin="voice")
    broken["pages"][0]["root"]["children"].append(wrapper)
    before = render(broken, an)
    assert not before["passed"]
    result = repair.repair_loop(broken, an)
    actions = {r["action"]: r["result"] for r in result["repairs"]}
    assert actions == {"default_items": "fixed", "fill_placeholder": "fixed", "remove_empty_wrapper": "fixed"}
    assert result["report"]["passed"], hard_failures(result["report"])
    assert result["code"]["preview"] != codegen.generate_code(broken)["preview"]


# --------------------------------------------------------------------------- 3. geometry-aware layout

ROW_SKETCH = analysis([
    comp("heading", "Plans", box(.2, .05, .3, .06)),
    comp("button", "Basic", box(.2, .2, .28, .08)),
    comp("button", "Pro", box(.52, .2, .28, .08)),
    comp("button", "Half", box(.2, .4, .3, .08)),
    comp("input", "Full", box(.2, .55, .6, .08)),
], width=1000, height=700)


def test_rows_stay_side_by_side_with_drawn_widths():
    ir = fusion.fuse(ROW_SKETCH, [])
    report = render(ir, ROW_SKETCH)
    assert report["passed"], hard_failures(report)
    basic, pro = rect(report, "btn_basic"), rect(report, "btn_pro")
    half, full = rect(report, "btn_half"), rect(report, "inp_full")
    assert abs(basic["y"] - pro["y"]) < 4 and pro["x"] > basic["x"] + basic["w"]
    assert 0.4 < half["w"] / full["w"] < 0.6          # a half-width button stays half width
    assert 0.4 < basic["w"] / full["w"] < 0.55
    assert report["visual"]["layout_iou"] > 0.6


def test_page_frame_follows_sketch_aspect():
    desktop = fusion.fuse(ROW_SKETCH, [])
    phone = fusion.fuse(analysis(ROW_SKETCH["components"], width=600, height=1200), [])
    assert desktop["meta"]["frame"]["kind"] == "desktop" and desktop["meta"]["frame"]["page_width"] == 720
    assert phone["meta"]["frame"]["kind"] == "mobile" and phone["meta"]["frame"]["page_width"] <= 430
    page = codegen.generate_code(phone)["files"]["src/pages/MainPage.jsx"]
    assert f'maxWidth: {phone["meta"]["frame"]["page_width"]}' in page


def test_tall_item_beside_a_stack_keeps_two_columns():
    an = analysis([comp("heading", "Cloud storage", box(.06, .2, .4, .07)), comp("text", "Fast and safe", box(.06, .3, .4, .1)),
                   comp("button", "Try", box(.06, .44, .19, .07)), comp("button", "Learn", box(.27, .44, .19, .07)),
                   comp("image", "", box(.52, .2, .41, .4))])
    ir = fusion.fuse(an, [])
    report = render(ir, an)
    head, try_btn, image = rect(report, "h_cloud_storage"), rect(report, "btn_try"), rect(report, "img_1") \
        if irm.find(ir, "img_1")[0] else None
    img = next(n["id"] for n in irm.nodes(ir, "image"))
    image = rect(report, img)
    assert image["x"] > head["x"] + head["w"]            # image to the right of the text column
    assert try_btn["y"] > head["y"] + head["h"]          # buttons below the heading, not beside it
    assert report["visual"]["layout_iou"] > 0.5


def test_sidebar_navbar_is_vertical():
    an = analysis([comp("navbar", "", box(.05, .1, .2, .6)),
                   comp("nav_item", "Home", box(.07, .2, .1, .05), 0), comp("nav_item", "Reports", box(.07, .3, .1, .05), 0)])
    ir = fusion.fuse(an, [])
    assert irm.nodes(ir, "navbar")[0]["layout"]["direction"] == "column"


# --------------------------------------------------------------------------- 4. resize + move in a row

def test_resize_image_with_explicit_height_and_textarea_rows(login_ir):
    img = irm.find(login_ir, "img_logo")[0]
    img["style"]["height"] = 200
    form = irm.find(login_ir, "form_login")[0]
    form["children"].append(irm.make_node(login_ir, "textarea", "Message", props={"rows": 4}))
    out = refine.apply_ops(login_ir, [
        {"op": "resize", "target": {"ref": "image"}, "changes": {"style": {"size": "sm"}}},
        {"op": "resize", "target": {"ref": "message box"}, "changes": {"props": {"rows": 8}}}])
    assert all(c["ok"] for c in out["changes"]), out["changes"]
    assert irm.find(out["ir"], "img_logo")[0]["style"]["height"] == 140
    assert irm.find(out["ir"], "ta_message")[0]["props"]["rows"] == 8


def test_width_full_in_a_row_takes_the_free_space():
    ir = fusion.fuse(ROW_SKETCH, [])
    out = refine.apply_ops(ir, [{"op": "resize", "target": {"id": "btn_pro", "ref": "pro button"},
                                 "changes": {"style": {"width": "full"}}}])
    before, after = render(ir, ROW_SKETCH), render(out["ir"], ROW_SKETCH)
    assert rect(after, "btn_pro")["w"] > rect(before, "btn_pro")["w"] + 20


def test_move_below_an_anchor_inside_a_row():
    ir = fusion.fuse(ROW_SKETCH, [])
    out = refine.apply_ops(ir, [{"op": "move", "target": {"ref": "half button"},
                                 "position": {"relation": "below", "anchor": {"ref": "basic button"}}}])
    assert out["changes"][0]["ok"]
    report = render(out["ir"], ROW_SKETCH)
    assert report["passed"], hard_failures(report)
    basic, half = rect(report, "btn_basic"), rect(report, "btn_half")
    assert half["y"] >= basic["y"] + basic["h"] - 1                   # really below
    assert half["x"] < basic["x"] + basic["w"] and half["x"] + half["w"] > basic["x"]  # under it, not to the right


# --------------------------------------------------------------------------- 5. hidden sketched components

def test_hidden_sketch_component_is_flagged_and_repaired():
    ir = fusion.fuse(ROW_SKETCH, [])
    broken = copy.deepcopy(ir)
    irm.find(broken, "h_plans")[0]["style"]["hidden"] = True
    report = render(broken, ROW_SKETCH)
    assert ("presence:h_plans", "hidden although it is drawn in the sketch") in hard_failures(report)
    result = repair.repair_loop(broken, ROW_SKETCH)
    assert result["report"]["passed"]
    assert any(r["action"] == "unhide" and r["result"] == "fixed" for r in result["repairs"])
    assert "hidden" not in irm.find(result["ir"], "h_plans")[0]["style"]


def test_user_hidden_and_toggled_components_stay_hidden():
    ir = fusion.fuse(ROW_SKETCH, [])
    hidden = refine.apply_ops(ir, [{"op": "style", "target": {"ref": "plans heading"}, "changes": {"style": {"hidden": True}}}])["ir"]
    assert render(hidden, ROW_SKETCH)["passed"]
    toggled = copy.deepcopy(ir)
    irm.find(toggled, "h_plans")[0]["style"]["hidden"] = True
    irm.find(toggled, "btn_basic")[0]["events"] = [{"on": "click", "actions": [{"type": "toggle_visibility", "target": "h_plans"}]}]
    assert render(toggled, ROW_SKETCH)["passed"]


# --------------------------------------------------------------------------- 6. fusion / targeting artefacts

def test_drawn_label_wins_over_a_different_spoken_label():
    an = analysis([comp("text", "Time slot", box(.1, .1, .2, .04)), comp("radio", "9:00", box(.1, .2, .1, .04)),
                   comp("radio", "11:00", box(.25, .2, .1, .04))])
    voice = [{"op": "create", "components": [{"type": "radio", "label": "Time slot", "props": {"group": "slot"}},
                                             {"type": "radio", "label": "11:00"}]}]
    labels = [n["label"] for n in irm.nodes(fusion.fuse(an, voice), "radio")]
    assert "9:00" in labels and "11:00" in labels


def test_field_reference_never_targets_its_text_label():
    an = analysis([comp("input", "Email", box(.4, .1, .4, .06)), comp("text", "Note", box(.1, .3, .2, .04)),
                   comp("text", "Email", box(.1, .5, .2, .04))])  # a separate "Email" text elsewhere on the page
    ir = fusion.fuse(an, [])
    txt = next(n["id"] for n in irm.nodes(ir, "text") if n["label"] == "Email")
    inp = irm.nodes(ir, "input")[0]["id"]
    op = {"op": "modify", "target": {"ref": "the email field", "id": txt}, "changes": {"props": {"placeholder": "you@x.com"}}}
    out = refine.apply_ops(ir, [op])
    assert out["changes"][0]["target"] == inp
    assert irm.find(out["ir"], inp)[0]["props"]["placeholder"] == "you@x.com"


def test_duplicate_detections_are_merged():
    comps = [comp("heading", "Dashboard", box(.3, .1, .1, .05)), comp("text", "Dashboard", box(.41, .1, .1, .05)),
             comp("text", "Dashboard", box(.3, .5, .1, .05))]
    merged = sketch.merge_duplicates(comps)
    assert len(merged) == 2
    assert merged[0]["type"] == "heading" and merged[0]["bbox"]["w"] == pytest.approx(0.21)


def test_overlapping_drawn_buttons_are_relaid_out():
    an = analysis([comp("button", "Basic", box(.2, .2, .3, .08)), comp("button", "Pro", box(.35, .21, .3, .08))])
    ir = fusion.fuse(an, [])
    report = render(ir, an)
    covered = [c for c in report["checks"] if c["id"].startswith("clickable") and not c["ok"]]
    result = repair.repair_loop(ir, an)
    assert result["report"]["passed"], hard_failures(result["report"])
    if covered:
        assert any(r["action"] == "relayout" and r["result"] == "fixed" for r in result["repairs"])


# --------------------------------------------------------------------------- recorded real analysis (land_01)

def _recorded_land():
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).parent / "fixtures" / "land_01_hybrid.json").read_text())
    an = dict(data["analysis"])
    comps = sketch.clean_components([dict(c) for c in an["components"]])
    sketch.containment_tree(comps)
    an["components"] = comps
    return an, data["ops"]


def test_recorded_land_01_fuses_without_duplicates_or_losses():
    an, ops = _recorded_land()
    ir = fusion.fuse(an, ops)
    main = [n for n, _, page in irm.walk(ir) if page is ir["pages"][0] and n["type"] != "page"]
    placeholders = set(fusion.PLACEHOLDER_LABELS.values())
    labels = [n["label"] for n in main if n["label"] and n["type"] not in irm.CONTAINER_TYPES
              and n["label"] not in placeholders]
    drawn = [sketch.norm_label(c["label"]) for c in an["components"] if c["label"]]
    for label in set(labels):
        # fusion never adds a second copy of something already drawn
        assert labels.count(label) <= max(1, drawn.count(sketch.norm_label(label))), label
    for word in ("Try free", "Learn more", "Features", "Pricing"):
        assert labels.count(word) == 1, (word, labels)
    nav = irm.nodes(ir, "navbar")[0]
    nav_labels = [c["label"] for c in nav["children"]]
    assert nav_labels[0] == "Nimbus"                                  # the brand at the bar's left
    assert {"Features", "Pricing", "About", "Get started"} <= set(nav_labels)
    assert not irm.nodes(ir, "radio") and len(irm.nodes(ir, "icon")) >= 2   # circled glyphs are icons
    cards = irm.nodes(ir, "card")
    assert len(cards) == 3
    for card in cards:                                                # each card holds its drawn contents
        for child in card["children"]:
            assert child.get("bbox") is None or irm.contains(card["bbox"], child["bbox"], 0.8), (card["id"], child["id"])
        assert len(card["children"]) >= 3
    hero_texts = [n for n in main if n["type"] == "text" and n.get("bbox") and n["bbox"]["y"] < 0.45]
    assert any(n["label"] == "Paragraph" for n in hero_texts)          # spoken paragraph = the hero scribble


def test_recorded_land_01_renders_and_navigates():
    an, ops = _recorded_land()
    ir = fusion.fuse(an, ops)
    pricing = next(n for n in irm.nodes(ir, "nav_item") if n["label"] == "Pricing")
    assert pricing["events"][0]["actions"] == [{"type": "navigate", "page": "page_pricing"}]
    report = render(ir, an)
    assert report["passed"], hard_failures(report)
    assert report["functional"]["interactions_passed"] == report["functional"]["interactions_total"]
    assert report["visual"]["layout_iou"] > 0.5


def test_click_on_a_container_runs_its_actions():
    an = analysis([comp("card", "", box(.1, .1, .4, .3)), comp("heading", "Plan", box(.15, .15, .2, .05), 0)])
    ir = fusion.fuse(an, [])
    card = irm.nodes(ir, "card")[0]
    out = refine.apply_ops(ir, [{"op": "navigation", "target": {"id": card["id"], "ref": "card"}, "page": {"name": "Plan"}}])
    report = render(out["ir"], an)
    assert report["passed"], hard_failures(report)


def test_nav_item_reference_targets_the_item_not_the_bar():
    an = analysis([comp("navbar", "", box(.05, .05, .9, .1)), comp("nav_item", "Home", box(.5, .07, .08, .05), 0),
                   comp("nav_item", "Pricing", box(.6, .07, .08, .05), 0)])
    ir = fusion.fuse(an, [])
    assert refine.resolve_target(ir, "Pricing nav_item")["id"] == "navi_pricing"
    assert refine.resolve_target(ir, "the pricing menu item")["id"] == "navi_pricing"


# --------------------------------------------------------------------------- real-run review round (7 sketches)

def test_head_noun_decides_the_target_type():
    an = analysis([comp("select", "Sort by", box(.1, .1, .3, .06)), comp("button", "Select flight", box(.1, .3, .3, .06))])
    ir = fusion.fuse(an, [])
    assert refine.resolve_target(ir, "Select flight button")["id"] == "btn_select_flight"
    assert refine.resolve_target(ir, "the sort by dropdown")["id"] == "sel_sort_by"


def test_wide_bar_is_a_row_even_with_ragged_items():
    an = analysis([comp("navbar", "", box(.05, .05, .9, .12)),
                   comp("text", "Brand", box(.07, .06, .1, .05), 0), comp("nav_item", "Home", box(.5, .1, .08, .05), 0),
                   comp("button", "Start", box(.75, .07, .15, .07), 0)])
    nav = irm.nodes(fusion.fuse(an, []), "navbar")[0]
    assert nav["layout"]["direction"] == "row"


def test_drawn_picture_box_is_an_image_and_circles_stay_round():
    comps = [comp("card", "", box(.05, .05, .9, .3)), comp("icon", "", box(.2, .1, .03, .04)),
             comp("divider", "", box(.1, .2, .7, .1)),
             {**comp("image", "", box(.05, .4, .15, .2)), "shape": "circle"}]
    cleaned = sketch.clean_components([dict(c) for c in comps])
    assert [c["type"] for c in cleaned] == ["image", "image"]
    ir = fusion.fuse(analysis(cleaned), [])
    assert any(n["style"].get("radius") == 999 for n in irm.nodes(ir, "image"))


def test_spoken_field_takes_the_place_of_its_read_placeholder_text():
    an = analysis([comp("input", "Name", box(.1, .1, .5, .06)), comp("text", "Email", box(.12, .2, .1, .04)),
                   comp("button", "Send", box(.1, .3, .2, .06))])
    voice = [{"op": "create", "components": [{"type": "input", "label": "Name"}, {"type": "input", "label": "Email",
                                                                                 "props": {"inputType": "email"}},
                                             {"type": "button", "label": "Send"}]}]
    ir = fusion.fuse(an, voice)
    order = [(n["type"], n["label"]) for n, _, _ in irm.walk(ir) if n["type"] != "page"]
    assert order == [("input", "Name"), ("input", "Email"), ("button", "Send")]


def test_label_text_echoing_a_checkbox_is_dropped():
    an = analysis([comp("checkbox", "", box(.1, .1, .03, .04)), comp("text", "Non-stop only", box(.2, .1, .2, .04)),
                   comp("button", "Search", box(.1, .3, .2, .06))])
    voice = [{"op": "create", "components": [{"type": "checkbox", "label": "Non-stop only"}]}]
    labels = [n["label"] for n, _, _ in irm.walk(fusion.fuse(an, voice))]
    assert labels.count("Non-stop only") == 1


def test_split_input_fragments_merge():
    comps = [comp("input", "Se", box(.5, .1, .05, .06)), comp("input", "Search products", box(.555, .1, .3, .06))]
    merged = sketch.clean_components([dict(c) for c in comps])
    assert len(merged) == 1 and merged[0]["label"] == "Search products"


def test_label_copied_onto_another_box_is_dropped_and_field_takes_vision_box():
    comps = [{**comp("button", "Submit", box(.09, .26, .23, .07)), "source": "hybrid"},
             {**comp("heading", "Get in touch", box(.1, .26, .22, .06)), "source": "hybrid"},
             {**comp("textarea", "Message", box(.1, .67, .08, .03)), "source": "hybrid"},
             {**comp("text", "Message", box(.09, .62, .4, .16)), "source": "vision"},
             {**comp("button", "Submit", box(.09, .86, .17, .09)), "source": "hybrid"}]
    cleaned = sketch.clean_components([dict(c) for c in comps])
    kinds = [(c["type"], c["label"]) for c in cleaned]
    assert kinds.count(("button", "Submit")) == 1 and ("heading", "Get in touch") in kinds
    area = next(c for c in cleaned if c["type"] == "textarea")["bbox"]
    assert area["h"] > 0.15 and ("text", "Message") not in kinds


def test_text_cluster_typed_like_its_box_merges_into_it():
    comps = [comp("button", "", box(.06, .81, .24, .1)), comp("button", "Add to cart", box(.13, .84, .1, .03))]
    cleaned = sketch.clean_components([dict(c) for c in comps])
    assert len(cleaned) == 1 and cleaned[0]["label"] == "Add to cart" and cleaned[0]["bbox"]["w"] == 0.24


def test_spoken_control_type_corrects_a_mistyped_drawn_box():
    an = analysis([comp("heading", "Flights", box(.05, .05, .3, .08)), comp("button", "Sort by", box(.05, .2, .25, .1)),
                   comp("button", "Load more", box(.4, .6, .2, .08))])
    voice = [{"op": "create", "components": [{"type": "select", "label": "Sort by", "props": {"options": ["Price"]}}]}]
    ir = fusion.fuse(an, voice)
    assert [(n["type"], n["label"]) for n in irm.nodes(ir) if n["label"] == "Sort by"] == [("select", "Sort by")]


def test_unreadable_square_mark_is_an_icon_and_bars_are_one_line():
    comps = [{**comp("heading", "", box(.38, .69, .045, .058)), "shape": "rect"},
             {**comp("heading", "Secure", box(.38, .78, .07, .03)), "shape": "text"}]
    cleaned = sketch.clean_components([dict(c) for c in comps])
    assert [c["type"] for c in cleaned] == ["icon", "heading"]
    an = analysis([comp("navbar", "", box(.05, .05, .9, .14)), comp("text", "Brand", box(.08, .06, .05, .02), 0),
                   comp("nav_item", "About", box(.4, .06, .06, .012), 0), comp("button", "Start", box(.8, .07, .1, .04), 0)])
    page = codegen.generate_code(fusion.fuse(an, []))["files"]["src/pages/MainPage.jsx"]
    assert 'align: "center"' in page


def test_vision_box_just_outside_a_bar_snaps_into_it():
    comps = [{**comp("navbar", "", box(.05, .05, .9, .12)), "source": "hybrid"},
             {**comp("text", "Brand", box(.08, .03, .06, .03)), "source": "vision"}]
    sketch.containment_tree(comps)
    assert comps[1]["parent"] == 0 and comps[1]["bbox"]["y"] >= 0.05
