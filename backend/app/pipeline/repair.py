"""Targeted repair loop: validate -> find the failing component -> fix only that -> revalidate.

Fixes per failed check
- missing (a component of the reference snapshot is gone)  -> restore it from the snapshot: same parent, same slot
- snapshot_hidden (hidden, but visible in the snapshot)    -> unhide
- coverage (a sketched component is missing from the UI)   -> unhide a hidden node that is drawn there, else
                                                              re-insert it from the sketch analysis
- sketch_order (children out of the sketch's vertical order) -> reorder those siblings
- order (rendered order differs from the IR)                  -> reset that container's layout
- size (explicit 0 size / collapsed to a sliver)           -> drop the width/height that collapsed it
- presence, not visible / zero size                           -> reset the node's style
- presence, missing from the DOM                              -> recompile that node in safe mode
- runtime error                                               -> recompile from the IR (sanitised; then safe mode)
- clickable / typing failure                                  -> reset style / props of that node
- event failure                                               -> rebuild that node's event handler
"""
from __future__ import annotations

import copy

from . import codegen, fusion
from . import ir as irm
from . import refine
from . import validate as validator

STYLE_RESET_KEYS = ("hidden", "width", "height", "fontSize", "color", "textColor", "bg")


def _failed(report: dict) -> list[dict]:
    return [c for c in report.get("checks", []) if c.get("hard", True) and not c["ok"]]


def _sort_by_sketch(children: list[dict], moved: set[str]) -> list[dict]:
    """Stable reorder by sketch y; nodes without a bbox (or moved by the user) stay after their previous sibling."""
    keyed, last = [], -1.0
    for i, child in enumerate(children):
        if child.get("bbox") and child["id"] not in moved:
            last = child["bbox"]["y"]
        keyed.append((last, i, child))
    return [c for _, _, c in sorted(keyed, key=lambda t: (t[0], t[1]))]


def _reinsert(ir: dict, comp: dict) -> str:
    """Re-create a sketched component and place it where the sketch puts it."""
    taken = irm.all_ids(ir)
    node = irm.make_node(ir, comp["type"], comp.get("label", ""), bbox=comp["bbox"], origin="repair", taken=taken)
    if node["type"] == "input":
        node["props"]["inputType"] = refine.guess_input_type(node["label"])
    page = ir["pages"][0]
    containers = [n for n, _, _ in validator._walk_page(page)
                  if "children" in n and n.get("bbox") and irm.contains(n["bbox"], comp["bbox"], 0.85)]
    parent = min(containers, key=lambda n: n["bbox"]["w"] * n["bbox"]["h"]) if containers else page["root"]
    siblings = parent["children"]
    if parent.get("layout", {}).get("direction") == "row":  # a row reads left to right
        before = [i for i, s in enumerate(siblings)
                  if s.get("bbox") and s["bbox"]["x"] + s["bbox"]["w"] / 2 < comp["bbox"]["x"] + comp["bbox"]["w"] / 2]
    else:
        before = [i for i, s in enumerate(siblings)
                  if s.get("bbox") and s["bbox"]["y"] + s["bbox"]["h"] / 2 < comp["bbox"]["y"] + comp["bbox"]["h"] / 2]
    index = (max(before) + 1) if before else 0
    siblings.insert(index, node)
    return f"re-inserted {node['type']} {node['label']!r} as {node['id']} in {parent['id']}"


def _restore(ir: dict, reference: dict, node_id: str) -> str | None:
    """Put a node that vanished back where the reference snapshot had it (same parent, after the same sibling)."""
    ref_node, ref_parent, ref_page = irm.find(reference, node_id)
    if ref_node is None or ref_parent is None:
        return None
    parent = irm.find(ir, ref_parent["id"])[0]
    if parent is None or "children" not in parent:
        page = next((p for p in ir["pages"] if p["id"] == ref_page["id"]), None)
        if page is None:
            return None
        parent = page["root"]
    present = {c["id"] for c in parent["children"]}
    index = 0
    for sibling in ref_parent["children"]:
        if sibling["id"] == node_id:
            break
        if sibling["id"] in present:
            index = [c["id"] for c in parent["children"]].index(sibling["id"]) + 1
    restored = copy.deepcopy(ref_node)
    parent["children"].insert(index, restored)
    meta = ir.setdefault("meta", {})
    meta["removed_ids"] = [i for i in meta.get("removed_ids", []) if i not in {n["id"] for n, _, _ in irm.walk(
        {"pages": [{"root": restored}], "meta": {}})}]
    return f"restored {restored['type']} {restored.get('label', '')!r} as {restored['id']} in {parent['id']} at slot {index}"


def _covered(ir: dict, comp: dict) -> bool:
    """A visible node already represents the sketch component (same rule as the validator's coverage check)."""
    nodes = [n for n, _, _ in irm.walk(ir) if n.get("bbox") and not irm.is_hidden(ir, n["id"])]
    label = (comp.get("label") or "").strip().lower()
    return (any(irm.iou(n["bbox"], comp["bbox"]) > 0.5 for n in nodes)
            or any(irm.contains(n["bbox"], comp["bbox"], 0.9) and n["type"] in irm.FIELD_TYPES | {"checkbox", "radio"} for n in nodes)
            or (comp.get("type") == "text" and bool(label) and any((n.get("label") or "").strip().lower() == label for n in nodes)))


def _caption(analysis: dict, comp: dict) -> str:
    """The text drawn right after a checkbox / radio on the same line is its label."""
    box = comp["bbox"]
    near = [c for c in analysis.get("components", []) if c.get("type") == "text" and c.get("label")
            and c["bbox"]["x"] >= box["x"] - 0.01 and c["bbox"]["x"] - (box["x"] + box["w"]) < 0.08
            and abs((c["bbox"]["y"] + c["bbox"]["h"] / 2) - (box["y"] + box["h"] / 2)) < max(box["h"], c["bbox"]["h"])]
    return min(near, key=lambda c: c["bbox"]["x"])["label"] if near else ""


PRIORITY = {"missing": 0, "snapshot_hidden": 1, "presence": 1, "size": 2, "coverage": 3}


def _rebuild_events(ir: dict, node: dict) -> str:
    taken = irm.all_ids(ir)
    rebuilt = []
    for event in node.get("events", []):
        actions = []
        for action in event.get("actions", []):
            action = dict(action)
            if action.get("targets"):
                action["targets"] = [t for t in action["targets"] if irm.find(ir, t)[0] is not None] or None
            if action.get("target") and irm.find(ir, action["target"])[0] is None:
                action["target"] = None if action["type"] == "validate_format" else action["target"]
            actions.append({k: v for k, v in action.items() if v is not None})
        resolved, _ = refine.resolve_actions(ir, node["id"], actions, taken)
        if resolved:
            rebuilt.append({"on": event.get("on", "click"), "actions": resolved})
    node["events"] = []
    for event in rebuilt:
        refine.merge_event(node, event["on"], event["actions"])
    return f"rebuilt {len(rebuilt)} event handler(s)"


def _sanitize(ir: dict) -> None:
    for node, _, _ in irm.walk(ir):
        if node["type"] not in irm.TYPE_PREFIX:
            node["type"] = "container"
        node["props"] = irm.clean_props(node["type"], node.get("props") or {})
        node["style"] = irm.clean_style(node.get("style") or {})
        if node["type"] in irm.CONTAINER_TYPES:
            node.setdefault("children", [])
            node.setdefault("layout", {"direction": "column", "gap": 12, "align": "stretch", "justify": "start"})


def _fix_invisible(ir: dict, node: dict) -> tuple[str, str]:
    """A node that renders with nothing to show: give it content, or drop an empty wrapper."""
    if node["type"] in fusion.PLACEHOLDER_LABELS and not (node.get("label") or "").strip():
        node["label"] = fusion.PLACEHOLDER_LABELS[node["type"]]
        return "fill_placeholder", f"gave {node['id']} placeholder text {node['label']!r}"
    if node["type"] == "list" and not node["props"].get("items") and not node.get("children"):
        node["props"]["items"] = fusion.default_list_items(node, ir.get("meta", {}).get("frame"))
        return "default_items", f"gave {node['id']} {len(node['props']['items'])} placeholder items"
    if "children" in node and not _has_visible_content(node):
        _, parent, _ = irm.find(ir, node["id"])
        if parent is not None and not (node.get("bbox") and node.get("origin") == "sketch"):
            parent["children"].remove(node)
            ir.setdefault("meta", {}).setdefault("removed_ids", []).append(node["id"])
            return "remove_empty_wrapper", f"removed {node['id']}, a wrapper with nothing to show"
        node["style"] = {**node.get("style", {}), "height": refine.drawn_height(ir, node) or 80}
        return "give_height", f"gave the drawn box {node['id']} its sketch height"
    node["style"] = {k: v for k, v in node.get("style", {}).items() if k not in STYLE_RESET_KEYS}
    return "reset_style", f"reset style of {node['id']}"


def _has_visible_content(node: dict) -> bool:
    for child in node.get("children", []):
        if child.get("style", {}).get("hidden"):
            continue
        if "children" not in child or _has_visible_content(child) or child.get("props", {}).get("items"):
            return True
    return False


def _relayout(ir: dict, node: dict, levels: int = 1) -> str:
    """Lay the node's sibling group (and, with levels > 1, its ancestors' groups) out without sketch offsets."""
    free = ir["meta"].setdefault("free_layout", [])
    current, done = node, []
    for _ in range(levels):
        _, parent, _ = irm.find(ir, current["id"])
        group = parent["children"] if parent is not None else [current]
        free.extend(c["id"] for c in group if c["id"] not in free)
        done.append(parent["id"] if parent else current["id"])
        if parent is None or parent["id"] == "page_main" or irm.find(ir, parent["id"])[1] is None:
            break
        current = parent
    return f"laid out {', '.join(done)} without sketch offsets"


def _escalate(ir: dict, check: dict, safe_ids: set[str], state: dict) -> tuple[str, str] | None:
    """A hard check kept failing after its targeted fix: widen the repair, first to the surrounding groups, then to the whole page."""
    node = irm.find(ir, check.get("target"))[0] if check.get("target") else None
    stage = state.setdefault("escalation", {}).get(check["id"], 0) + 1
    state["escalation"][check["id"]] = stage
    if node is None or stage > 2:
        return None
    if stage == 1:
        return "relayout", _relayout(ir, node, levels=3)
    free = ir["meta"].setdefault("free_layout", [])
    free.extend(n["id"] for n, _, _ in irm.walk(ir) if n["id"] not in free)
    return "relayout_page", "laid out the whole page without sketch offsets"


def _fix(ir: dict, check: dict, analysis: dict | None, safe_ids: set[str], state: dict,
         reference: dict | None = None) -> tuple[str, str] | None:
    cid, target = check["id"], check.get("target")
    kind = cid.split(":", 1)[0]
    node = irm.find(ir, target)[0] if target else None

    if kind == "missing" and reference is not None:
        detail = _restore(ir, reference, target)
        return ("restore_from_snapshot", detail) if detail else None
    if kind == "snapshot_hidden" and node is not None:
        node["style"] = {k: v for k, v in node["style"].items() if k != "hidden"}
        return "unhide", f"made {node['id']} visible again (it was visible in the previous version)"
    if kind == "size" and node is not None:
        node["style"] = {k: v for k, v in node.get("style", {}).items() if k not in ("width", "height")}
        return "reset_size", f"dropped the width/height that collapsed {node['id']}"
    if kind == "coverage" and analysis:
        idx = int(cid.split(":", 1)[1])
        comp = analysis["components"][idx]
        if _covered(ir, comp):
            return None  # an earlier fix in this pass (restore / unhide) already brought it back
        hidden = next((n for n, _, _ in irm.walk(ir) if n.get("bbox") and n.get("style", {}).get("hidden")
                       and irm.iou(n["bbox"], comp["bbox"]) > 0.5), None)
        if hidden is not None:  # it is there, just hidden: show it instead of adding a duplicate
            hidden["style"] = {k: v for k, v in hidden["style"].items() if k != "hidden"}
            return "unhide", f"made {hidden['id']} visible again"
        if comp["type"] in ("checkbox", "radio") and not (comp.get("label") or "").strip():
            comp = {**comp, "label": _caption(analysis, comp)}  # its caption was a separate text component
        return "reinsert_from_sketch", _reinsert(ir, comp)
    if kind == "sketch_order" and node is not None:
        node["children"] = _sort_by_sketch(node["children"], set(ir.get("meta", {}).get("moved", [])))
        return "reorder_siblings", f"reordered children of {node['id']} by sketch position"
    if kind == "order" and node is not None:
        node["layout"] = {**node.get("layout", {}), "direction": node.get("layout", {}).get("direction", "column")}
        safe_ids.add(node["id"])
        return "reset_layout", f"rendered {node['id']} in safe mode"
    if kind == "presence" and node is not None:
        if "missing" in check["detail"]:
            safe_ids.add(node["id"])
            return "recompile_safe", f"recompiled {node['id']} in safe mode"
        if "hidden although" in check["detail"]:
            node["style"] = {k: v for k, v in node["style"].items() if k != "hidden"}
            return "unhide", f"made {node['id']} visible again (it is drawn in the sketch)"
        return _fix_invisible(ir, node)
    if kind in ("clickable", "typing", "event") and node is not None and "covered" in check["detail"]:
        # overlapping drawn boxes made siblings overlap: lay this group out naturally instead
        return "relayout", _relayout(ir, node) + " (overlap)"
    if kind == "clickable" and node is not None:
        node["style"] = {k: v for k, v in node.get("style", {}).items() if k not in STYLE_RESET_KEYS}
        return "reset_style", f"reset style of {node['id']} so it can be clicked"
    if kind == "typing" and node is not None:
        if node["type"] == "input":
            node["props"]["inputType"] = node["props"].get("inputType") if node["props"].get("inputType") in irm.INPUT_TYPES else "text"
        safe_ids.add(node["id"])
        return "recompile_safe", f"recompiled field {node['id']} in safe mode"
    if kind == "event" and node is not None:
        given = [n for n in fusion.finalize_content(ir) if n.startswith("default options")]
        if given:
            return "default_options", "; ".join(given) + " (a required dropdown without options cannot be filled in)"
        return "rebuild_handler", f"{node['id']}: " + _rebuild_events(ir, node)
    if kind == "runtime":
        if state.get("manual_code"):
            state["manual_code"] = False
            return "recompile", "replaced the edited code with code compiled from the IR"
        if not state.get("sanitized"):
            _sanitize(ir)
            state["sanitized"] = True
            return "recompile", "sanitised the IR and recompiled"
        safe_ids.update(n["id"] for n, _, _ in irm.walk(ir))
        return "recompile_safe", "recompiled every component in safe mode"
    return None


def repair_loop(ir: dict, analysis: dict | None = None, max_iter: int = 3, code: dict | None = None,
                report: dict | None = None, manual_code: bool = False, reference: dict | None = None) -> dict:
    """Validate and repair until the UI passes or max_iter passes are used.

    `code`/`report` let callers pass an already generated + validated result; `manual_code` marks code that was
    edited by hand (a runtime error then triggers a recompile from the IR). `reference` is an earlier snapshot of the
    IR (the previous version): components that disappeared from it are restored.
    Returns {"ir", "code", "report", "repairs":[{"iteration","check","target","action","detail","result"}], "changed"}.
    """
    ir = copy.deepcopy(ir)
    safe_ids: set[str] = set()
    state = {"manual_code": manual_code}
    current = code or codegen.generate_code(ir)
    report = report or validator.validate(ir, current["preview"], analysis, reference)
    repairs: list[dict] = []
    for iteration in range(1, max_iter + 1):
        failed = sorted(_failed(report), key=lambda c: PRIORITY.get(c["id"].split(":", 1)[0], 4))
        if not failed:
            break
        applied = []
        for check in failed:
            if any(r["check"] == check["id"] and r["result"] == "still failing" for r in repairs) and \
                    not check["id"].startswith("runtime"):
                fix = _escalate(ir, check, safe_ids, state)  # the targeted fix did not help: widen it (bounded: 2 steps per check)
                if fix is not None:
                    applied.append({"iteration": iteration, "check": check["id"], "target": check.get("target"),
                                    "action": fix[0], "detail": fix[1], "result": "pending"})
                continue
            if check["id"].startswith("coverage:") and any(a["action"] in ("restore_from_snapshot", "unhide") for a in applied):
                continue  # a node was just brought back: let the next validation say whether this one is still missing
            fix = _fix(ir, check, analysis, safe_ids, state, reference)
            if fix is None:
                continue
            action, detail = fix
            applied.append({"iteration": iteration, "check": check["id"], "target": check.get("target"),
                            "action": action, "detail": detail, "result": "pending"})
        if not applied:
            break
        current = codegen.generate_code(ir, safe_ids=safe_ids)
        report = validator.validate(ir, current["preview"], analysis, reference)
        still = {c["id"] for c in _failed(report)}
        for item in applied:
            item["result"] = "still failing" if item["check"] in still else "fixed"
        repairs.extend(applied)
    return {"ir": ir, "code": current, "report": report, "repairs": repairs, "changed": bool(repairs),
            "safe_ids": sorted(safe_ids)}
