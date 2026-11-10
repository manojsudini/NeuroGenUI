"""Deterministic multimodal fusion: SketchAnalysis (structure, geometry, order) + create Ops (semantics) -> IR.

The sketch decides *where* things are: rows are grouped by vertical overlap, containment gives parents.
The voice description decides *what* they are: labels, input types, required flags, events, title.
Voice components are matched to sketch components by type compatibility, reading order and label similarity.
Unmatched voice components are inserted next to the voice component spoken before them; unmatched
sketch components are kept.
"""
from __future__ import annotations

import difflib
import re

from . import ir as irm
from . import refine
from . import sketch as sketch_mod

COMPAT = refine.COMPATIBLE
TEXTUAL = {"text", "heading", "button", "link", "nav_item"}
SAME_LABEL = 0.85  # label similarity at which a spoken and a drawn component are the same thing
DESKTOP_WIDTH = 1200  # CSS px a full-width desktop sketch maps to
MOBILE_WIDTH = 430    # CSS px a full-width phone sketch maps to
PLACEHOLDER_LABELS = {"text": "Text", "heading": "Heading", "button": "Button", "link": "Link",
                      "nav_item": "Menu item", "checkbox": "Option", "radio": "Option"}
FORM_CATEGORIES = {"login", "registration", "signup", "register", "contact", "booking", "settings", "profile"}


def _type_affinity(voice_type: str, sketch_type: str) -> float:
    if voice_type == sketch_type:
        return 1.0
    if any(voice_type in g and sketch_type in g for g in COMPAT):
        return 0.6
    if {voice_type, sketch_type} <= TEXTUAL:
        return 0.4  # a word drawn as plain text may be spoken as a menu item, link or button (label decides)
    return 0.0


def _label_similarity(a: str, b: str) -> float:
    """Fuzzy similarity of two labels, ignoring case and punctuation ("Log in" ~ "log-in")."""
    a, b = sketch_mod.norm_label(a), sketch_mod.norm_label(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _proto(comp: dict, origin: str) -> dict:
    style = refine.normalize_style(comp.get("style") or {})
    if comp.get("shape") == "circle" and comp.get("type") in ("image", "icon"):
        style.setdefault("radius", 999)  # a drawn circle (avatar) stays round
    props = dict(comp.get("props") or {})
    if comp.get("type") == "list" and comp.get("items") and not props.get("items"):
        props["items"] = [str(t) for t in comp["items"]]  # the lines read inside a drawn list
    return {
        "type": comp.get("type") if comp.get("type") in irm.TYPE_PREFIX else "text",
        "label": (comp.get("label") or "").strip(),
        "props": props,
        "style": style,
        "bbox": comp.get("bbox") if origin == "sketch" else None,
        "events": list(comp.get("events") or []),
        "origin": origin,
        "children": [],
    }


# --------------------------------------------------------------------------- sketch side

def _sketch_protos(analysis: dict) -> tuple[list[dict], list[int | None]]:
    protos, parents = [], []
    for comp in analysis.get("components", []):
        if comp.get("type") == "page" or not comp.get("bbox"):
            continue
        proto = _proto(comp, "sketch")
        if proto["type"] == "container":
            proto["type"] = "card"  # a box drawn on a wireframe is a visible box (becomes a form if it holds fields)
        protos.append(proto)
        parents.append(comp.get("parent"))
    # Re-map parent indices after skipping; fall back to geometric containment.
    valid = {i for i in range(len(protos))}
    parents = [p if isinstance(p, int) and p in valid and p != i else None for i, p in enumerate(parents)]
    for i, proto in enumerate(protos):
        if parents[i] is None:
            parents[i] = _geometric_parent(protos, i)
    return protos, parents


def _geometric_parent(protos: list[dict], idx: int) -> int | None:
    box = protos[idx]["bbox"]
    best, best_area = None, None
    for j, other in enumerate(protos):
        if j == idx or other["type"] not in irm.CONTAINER_TYPES:
            continue
        if irm.contains(other["bbox"], box, 0.85):
            area = other["bbox"]["w"] * other["bbox"]["h"]
            if best_area is None or area < best_area:
                best, best_area = j, area
    return best


def _absorb_labels(protos: list[dict], parents: list[int | None]) -> set[int]:
    """Text written right above / left of a field (or right of a checkbox) is that field's label."""
    absorbed: set[int] = set()
    for i, field in enumerate(protos):
        if field["type"] not in irm.FIELD_TYPES | {"checkbox", "radio"}:
            continue
        fb = field["bbox"]
        best, best_gap = None, None
        for j, text in enumerate(protos):
            if j in absorbed or text["type"] != "text" or parents[j] != parents[i]:
                continue
            if field["label"] and text["label"].strip().lower() != field["label"].strip().lower():
                continue  # the field already has its own label: this text is separate content
            tb = text["bbox"]
            if field["type"] in ("checkbox", "radio"):
                same_row = abs((tb["y"] + tb["h"] / 2) - (fb["y"] + fb["h"] / 2)) < max(fb["h"], tb["h"]) * 0.7
                gap = tb["x"] - (fb["x"] + fb["w"])
                ok = same_row and -0.01 <= gap < 0.06
            else:
                above_gap = fb["y"] - (tb["y"] + tb["h"])
                overlaps_x = tb["x"] < fb["x"] + fb["w"] * 0.6 and tb["x"] + tb["w"] > fb["x"] - 0.02
                above = -0.01 <= above_gap < max(0.05, tb["h"] * 1.6) and overlaps_x and tb["w"] <= fb["w"] * 1.1
                left_gap = fb["x"] - (tb["x"] + tb["w"])
                same_row = abs((tb["y"] + tb["h"] / 2) - (fb["y"] + fb["h"] / 2)) < fb["h"] * 0.6
                left = same_row and -0.01 <= left_gap < 0.05
                ok, gap = above or left, min(abs(above_gap), abs(left_gap))
            if ok and (best_gap is None or gap < best_gap):
                best, best_gap = j, gap
        if best is not None:
            if not field["label"]:
                field["label"] = protos[best]["label"]
            field["bbox"] = irm.union_bbox([field["bbox"], protos[best]["bbox"]])  # the field renders its label
            absorbed.add(best)
    return absorbed


# --------------------------------------------------------------------------- voice side

def _voice_protos(ops: list[dict]) -> tuple[list[dict], list[int | None], dict]:
    protos, parents, meta = [], [], {}

    def visit(comp: dict, parent: int | None) -> None:
        protos.append(_proto(comp, "voice"))
        parents.append(parent)
        me = len(protos) - 1
        for child in comp.get("children") or []:
            visit(child, me)

    for op in ops:
        kind = op.get("op")
        if kind == "create":
            meta.update({k: v for k, v in (op.get("meta") or {}).items() if v})
            for comp in op.get("components") or ([op["component"]] if op.get("component") else []):
                visit(comp, None)
        elif kind == "add" and op.get("component"):
            visit(op["component"], None)
    return protos, parents, meta


def _match(voice: list[dict], sketch: list[dict], skip: set[int]) -> dict[int, int]:
    """Global voice->sketch matching in two passes.

    1. Anchors: pairs whose labels are (nearly) identical and whose types are compatible, anywhere on the page.
    2. The rest: a spoken component between two anchors should be a drawn one between the same anchors in the
       sketch's reading order (rows by vertical overlap, left to right). Score = type affinity + label
       similarity + closeness to that window. Spoken generic containers only group and are never matched.
    """
    voice_seq = [i for i, v in enumerate(voice) if v["type"] != "container"]
    reading = [i for row in _rows([(i, p) for i, p in enumerate(sketch) if i not in skip]) for i, _ in row]
    position = {si: k for k, si in enumerate(reading)}
    pairs: dict[int, int] = {}

    anchors = []
    for vi in voice_seq:
        for si in reading:
            affinity = _type_affinity(voice[vi]["type"], sketch[si]["type"])
            label = _label_similarity(voice[vi]["label"], sketch[si]["label"])
            if affinity > 0 and label >= SAME_LABEL:
                anchors.append((label + affinity, vi, si))
    for _, vi, si in sorted(anchors, key=lambda a: (-a[0], a[1], a[2])):
        if vi not in pairs and si not in pairs.values():
            pairs[vi] = si

    def window(vi: int) -> tuple[int, int]:
        before = [position[pairs[j]] for j in voice_seq if j < vi and j in pairs]
        after = [position[pairs[j]] for j in voice_seq if j > vi and j in pairs]
        return (max(before) if before else -1), (min(after) if after else len(reading))

    candidates = []
    for vi in voice_seq:
        if vi in pairs:
            continue
        v = voice[vi]
        low, high = window(vi)
        for si in reading:
            if si in pairs.values():
                continue
            s = sketch[si]
            affinity = _type_affinity(v["type"], s["type"])
            if affinity == 0.0:
                continue
            label = _label_similarity(v["label"], s["label"])
            if affinity < 0.5 and label < SAME_LABEL:
                continue  # across kinds (a spoken button vs a drawn heading) only the very same text counts
            if affinity < 1.0 and v["label"] and s["label"] and label < 0.5:
                continue  # a different kind of component with different text is a different component
            k = position[si]
            outside = max(0, low - k, k - high) if not (low < k < high) else 0
            order = 1.0 if outside == 0 else max(0.0, 1.0 - outside / max(4, len(reading) / 4))
            label_term = 1.2 * label if not (v["label"] and s["label"] and label < 0.5) else -0.5
            candidates.append((affinity + label_term + 0.5 * order, vi, si))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    used = set(pairs.values())
    for score, vi, si in candidates:
        if vi in pairs or si in used or score < 0.6:
            continue
        pairs[vi] = si
        used.add(si)
    return pairs


CONTROL_TYPES = irm.FIELD_TYPES | {"checkbox", "radio"}


def _place_controls_on_read_text(voice: list[dict], sketch: list[dict], pairs: dict[int, int], absorbed: set[int]) -> None:
    """A spoken control (field/checkbox/radio) left unmatched whose text was read on the sketch: if an unlabeled
    drawn control of that kind sits next to the text, that control is it (the text is its label); otherwise the
    control's box was missed and the read text marks where it is."""
    used = set(pairs.values())
    for vi, v in enumerate(voice):
        if vi in pairs or v["type"] not in CONTROL_TYPES or not v["label"]:
            continue
        # the read text, or a drawn leaf of another kind carrying the same text (a dropdown typed "button")
        text = next((i for i, s in enumerate(sketch) if i not in used and i not in absorbed
                     and s["type"] not in irm.CONTAINER_TYPES | {"image", "icon", "divider"}
                     and _label_similarity(s["label"], v["label"]) >= SAME_LABEL), None)
        if text is None:
            continue
        near = [i for i, s in enumerate(sketch) if i not in used and i not in absorbed and not s["label"]
                and _type_affinity(v["type"], s["type"]) > 0
                and _adjacent(s["bbox"], sketch[text]["bbox"])]
        target = min(near, key=lambda i: sketch_mod._center_distance(sketch[i]["bbox"], sketch[text]["bbox"])) \
            if near else text
        if target == text:
            sketch[text]["type"] = v["type"]
        _merge(sketch[target], v)
        pairs[vi] = target
        used.add(target)


def _adjacent(a: dict, b: dict) -> bool:
    """Side by side on one line with a small gap, or stacked with a small gap and overlapping horizontally."""
    v_overlap = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    h_gap = max(a["x"], b["x"]) - min(a["x"] + a["w"], b["x"] + b["w"])
    if v_overlap > 0.3 * min(a["h"], b["h"]) and h_gap < 0.12:
        return True
    h_overlap = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    v_gap = max(a["y"], b["y"]) - min(a["y"] + a["h"], b["y"] + b["h"])
    return h_overlap > 0 and v_gap < 0.08


def _label_echoes(protos: list[dict], parents: list[int | None], absorbed: set[int]) -> set[int]:
    """A drawn text that repeats the label of an adjacent field/checkbox/radio is that control's label,
    which the control already renders: drop the separate text."""
    echoes = set()
    controls = [p for p in protos if p["type"] in irm.FIELD_TYPES | {"checkbox", "radio"} and p["label"]]
    for i, text in enumerate(protos):
        if i in absorbed or text["type"] != "text" or not text["label"]:
            continue
        for ctl in controls:
            if _label_similarity(ctl["label"], text["label"]) >= SAME_LABEL and _adjacent(ctl["bbox"], text["bbox"]):
                echoes.add(i)
                break
    return echoes


def _drawn_twin(proto: dict, sketch: list[dict], absorbed: set[int], registry: dict[int, str]) -> str | None:
    """Id of a drawn component whose label is (nearly) the same as this spoken one, with a compatible type."""
    if not proto["label"] or proto["type"] in irm.CONTAINER_TYPES:
        return None
    best, best_score = None, SAME_LABEL
    for i, other in enumerate(sketch):
        if i in absorbed or id(other) not in registry:
            continue
        score = _label_similarity(proto["label"], other["label"])
        if score >= best_score and (_type_affinity(proto["type"], other["type"]) > 0 or proto["type"] in TEXTUAL):
            best, best_score = registry[id(other)], score
    return best


def _merge(sketch_proto: dict, voice_proto: dict) -> None:
    if voice_proto["type"] != sketch_proto["type"] and _type_affinity(voice_proto["type"], sketch_proto["type"]) > 0 \
            and voice_proto["type"] != "container":  # a generic spoken "container" keeps the drawn list/card/form
        sketch_proto["type"] = voice_proto["type"]
    if voice_proto["label"] and not sketch_proto["label"]:
        # What is written on the sketch always wins; the spoken label only fills components drawn without text.
        sketch_proto["label"] = voice_proto["label"]
    sketch_proto["props"].update(voice_proto["props"])
    sketch_proto["style"].update(voice_proto["style"])
    sketch_proto["events"] = voice_proto["events"] or sketch_proto["events"]


# --------------------------------------------------------------------------- layout

def _rows(items: list[tuple[int, dict]]) -> list[list[tuple[int, dict]]]:
    """Group items into rows by vertical overlap, rows top-to-bottom, items left-to-right."""
    rows: list[dict] = []
    for idx, proto in sorted(items, key=lambda it: (it[1]["bbox"]["y"], it[1]["bbox"]["x"])):
        b = proto["bbox"]
        for row in rows:
            top, bottom = row["top"], row["bottom"]
            overlap = min(bottom, b["y"] + b["h"]) - max(top, b["y"])
            if overlap > 0.5 * min(b["h"], bottom - top):
                row["items"].append((idx, proto))
                row["top"], row["bottom"] = min(top, b["y"]), max(bottom, b["y"] + b["h"])
                break
        else:
            rows.append({"top": b["y"], "bottom": b["y"] + b["h"], "items": [(idx, proto)]})
    rows.sort(key=lambda r: r["top"])
    return [sorted(r["items"], key=lambda it: it[1]["bbox"]["x"]) for r in rows]


def _arrange(children: list[int], protos: list[dict], kids: dict[int, list[int]], frame: dict,
             parent_direction: str, sketch_size: tuple[int, int]) -> list[dict]:
    """Recursively turn sketch protos into nested protos with row containers."""
    out = []
    items = [(i, protos[i]) for i in children]
    if parent_direction == "row":
        rows = [sorted(items, key=lambda it: it[1]["bbox"]["x"])]
    else:
        rows = _rows(items)
    for row in rows:
        built = []
        columns = _columns(row) if parent_direction != "row" and len(row) > 1 else [row]
        if len(columns) > 1 and any(len(col) > 1 for col in columns):
            # A tall item (e.g. a hero image) beside stacked items: keep the stack as its own column.
            for col in columns:
                if len(col) == 1:
                    built.extend(_build_items(col, protos, kids, sketch_size))
                    continue
                box = irm.union_bbox([p["bbox"] for _, p in col])
                stack = _arrange([i for i, _ in col], protos, kids, box, "column", sketch_size)
                built.append({"type": "container", "label": "", "props": {}, "style": {}, "events": [],
                              "bbox": box, "origin": "sketch", "children": stack,
                              "layout": {"direction": "column", "gap": 12, "align": "stretch", "justify": "start"}})
        else:
            built = _build_items(row, protos, kids, sketch_size)
        if len(built) > 1 and parent_direction != "row":
            boxes = [p["bbox"] for p in built]
            out.append({"type": "container", "label": "", "props": {}, "style": {}, "events": [],
                        "bbox": irm.union_bbox(boxes), "origin": "sketch", "children": built, "_row": True,
                        "layout": {"direction": "row", "gap": 12, "align": "center",
                                   "justify": _row_justify(built, frame)}})
        else:
            out.extend(built)
    return out


def _columns(row: list[tuple[int, dict]]) -> list[list[tuple[int, dict]]]:
    """Split a row into groups that overlap horizontally (items stacked above each other)."""
    groups: list[dict] = []
    for idx, proto in sorted(row, key=lambda it: it[1]["bbox"]["x"]):
        b = proto["bbox"]
        if groups and b["x"] < groups[-1]["right"] - 0.005:
            groups[-1]["items"].append((idx, proto))
            groups[-1]["right"] = max(groups[-1]["right"], b["x"] + b["w"])
        else:
            groups.append({"right": b["x"] + b["w"], "items": [(idx, proto)]})
    return [g["items"] for g in groups]


def _build_items(row: list[tuple[int, dict]], protos: list[dict], kids: dict[int, list[int]],
                 sketch_size: tuple[int, int]) -> list[dict]:
    """Protos of one row; containers get their own children arranged recursively."""
    built = []
    for idx, proto in row:
        if proto["type"] in irm.CONTAINER_TYPES:
            children = kids.get(idx, [])
            # Bars are rows unless their items are drawn stacked (a sidebar menu).
            b = proto["bbox"]
            wide = b["w"] * sketch_size[0] > 3 * b["h"] * sketch_size[1]
            horizontal_bar = proto["type"] in ("navbar", "header") and (wide or not children or _single_row(children, protos))
            direction = "row" if horizontal_bar else "column"
            inner = _arrange(children, protos, kids, proto["bbox"], direction, sketch_size)
            proto["children"] = inner
            if proto["type"] in ("navbar", "header") and direction == "column":
                proto["layout"] = {"direction": "column", "gap": 12, "align": "stretch", "justify": "start"}
            if direction == "column" and inner and _single_row(kids.get(idx, []), protos):
                proto["layout"] = {"direction": "row", "gap": 12, "align": "center", "justify": "start"}
                proto["children"] = [c for r in inner for c in (r["children"] if r.get("_row") else [r])]
            if proto["type"] in ("container", "card") and _has_fields(proto) and not _has_nested_boxes(proto):
                proto["type"] = "form"
        built.append(proto)
    return built


def _single_row(children: list[int], protos: list[dict]) -> bool:
    return len(children) > 1 and len(_rows([(i, protos[i]) for i in children])) == 1


def _row_justify(items: list[dict], frame: dict) -> str:
    left = min(p["bbox"]["x"] for p in items) - frame["x"]
    right = frame["x"] + frame["w"] - max(p["bbox"]["x"] + p["bbox"]["w"] for p in items)
    if left > 0.15 * frame["w"] and abs(left - right) < 0.1 * frame["w"]:
        return "center"
    total = sum(p["bbox"]["w"] for p in items)
    return "between" if total < 0.6 * frame["w"] and left < 0.1 * frame["w"] and right < 0.1 * frame["w"] else "start"


def _has_nested_boxes(proto: dict) -> bool:
    return any(c["type"] in ("card", "form") for c in proto.get("children", []))


def _has_fields(proto: dict) -> bool:
    stack = list(proto.get("children", []))
    while stack:
        cur = stack.pop()
        if cur["type"] in irm.FIELD_TYPES:
            return True
        if cur["type"] not in ("card", "form"):
            stack.extend(cur.get("children", []))
    return False


# --------------------------------------------------------------------------- materialise

def _materialize(ir: dict, proto: dict, taken: set[str], registry: dict[int, str]) -> dict:
    node = irm.make_node(ir, proto["type"], proto["label"], props=proto["props"], style=proto["style"],
                         bbox=proto["bbox"], origin=proto["origin"], taken=taken)
    if node["type"] == "input" and "inputType" not in node["props"]:
        node["props"]["inputType"] = refine.guess_input_type(node["label"])
    if proto.get("layout") and "layout" in node:
        node["layout"] = dict(proto["layout"])
    node["_events"] = proto["events"]
    registry[id(proto)] = node["id"]
    for child in proto.get("children", []):
        if "children" in node:
            node["children"].append(_materialize(ir, child, taken, registry))
    return node


def _relations(ir: dict) -> None:
    for node, _, _ in irm.walk(ir):
        kids = node.get("children", [])
        direction = node.get("layout", {}).get("direction", "column")
        for prev, cur in zip(kids, kids[1:]):
            rel = "right_of" if direction == "row" else "below"
            if not any(r["target"] == prev["id"] for r in cur["relations"]):
                cur["relations"].append({"type": rel, "target": prev["id"]})


def _wrap_voice_form(ir: dict, taken: set[str]) -> None:
    """Voice-only generation: put the run of fields/buttons into a form container."""
    root = ir["pages"][0]["root"]
    kids = root["children"]
    form_types = irm.FIELD_TYPES | {"checkbox", "radio", "button", "link"}
    first = next((i for i, n in enumerate(kids) if n["type"] in irm.FIELD_TYPES), None)
    if first is None:
        return
    last = first
    for i in range(first, len(kids)):
        if kids[i]["type"] in form_types:
            last = i
        else:
            break
    form = irm.make_node(ir, "form", "", origin="voice", taken=taken)
    form["children"] = kids[first:last + 1]
    root["children"] = kids[:first] + [form] + kids[last + 1:]


def fuse_with_report(analysis: dict | None, ops: list[dict], title: str | None = None) -> tuple[dict, list[dict]]:
    ops = ops or []
    voice, voice_parents, meta = _voice_protos(ops)
    category = (meta.get("category") or (analysis or {}).get("category") or "other").lower()
    first_heading = next((v["label"] for v in voice if v["type"] == "heading" and v["label"]), "")
    ir = irm.new_ir(title or meta.get("title") or first_heading or category.title() or "Untitled", category)
    taken = irm.all_ids(ir)
    root = ir["pages"][0]["root"]
    registry: dict[int, str] = {}

    sketch, sketch_parents = ([], [])
    if analysis and analysis.get("components"):
        sketch, sketch_parents = _sketch_protos(analysis)
    absorbed = _absorb_labels(sketch, sketch_parents) if sketch else set()
    pairs = _match(voice, sketch, absorbed) if sketch else {}
    if sketch:
        _place_controls_on_read_text(voice, sketch, pairs, absorbed)
    for vi, si in pairs.items():
        _merge(sketch[si], voice[vi])

    if sketch:
        absorbed |= _label_echoes(sketch, sketch_parents, absorbed)
        kids: dict[int, list[int]] = {}
        top = []
        for i, parent in enumerate(sketch_parents):
            if i in absorbed:
                continue
            (kids.setdefault(parent, []) if parent is not None and parent not in absorbed else top).append(i)
        frame = irm.union_bbox([sketch[i]["bbox"] for i in top]) or {"x": 0, "y": 0, "w": 1, "h": 1}
        size = (analysis.get("width") or 1000, analysis.get("height") or 1000)
        for proto in _arrange(top, sketch, kids, frame, "column", size):
            root["children"].append(_materialize(ir, proto, taken, registry))
        ir["meta"]["frame"] = frame_meta(size, frame)

    # Unmatched voice components: place each after the voice component spoken before it.
    placed: dict[int, str] = {vi: registry[id(sketch[si])] for vi, si in pairs.items() if id(sketch[si]) in registry}
    for vi, proto in enumerate(voice):
        if vi in placed:
            continue
        twin = _drawn_twin(proto, sketch, absorbed, registry)
        if twin is not None:  # already drawn: enrich it, never add a second copy
            node, _, _ = irm.find(ir, twin)
            node["props"].update(irm.clean_props(node["type"], proto["props"]))
            node["style"].update(irm.clean_style(proto["style"]))
            node["_events"] = (node.get("_events") or []) + proto["events"]
            placed[vi] = twin
            continue
        parent_vi = voice_parents[vi]
        if parent_vi is not None and parent_vi in placed:
            node = _materialize(ir, proto, taken, registry)
            parent_node, _, _ = irm.find(ir, placed[parent_vi])
            if parent_node is not None and "children" in parent_node:
                parent_node["children"].append(node)
                placed[vi] = node["id"]
                continue
        if parent_vi is not None:
            continue  # parent was matched to a non-container; skip nested child
        node = _materialize(ir, proto, taken, registry)
        prev = next((placed[j] for j in range(vi - 1, -1, -1) if j in placed and voice_parents[j] is None), None)
        if prev is None:
            following = next((placed[j] for j in range(vi + 1, len(voice)) if j in placed), None)
            if following is not None and sketch:
                refine.insert_relative(ir, node, following, "above", taken, stack_in_row=False)
            else:
                anchor, relation = refine.default_anchor(ir, node["type"]) if sketch else (root["id"], "last")
                refine.insert_relative(ir, node, anchor, relation, taken)
        else:
            refine.insert_relative(ir, node, prev, "below", taken, stack_in_row=False)
        node["relations"] = []
        placed[vi] = node["id"]

    if sketch:
        infer_row_geometry(ir)
    if not sketch:
        _wrap_voice_form(ir, taken)
        if category in FORM_CATEGORIES:
            root["style"]["width"] = 480
    # Voice-described events: resolve refs to ids now that every node exists.
    for node, _, _ in list(irm.walk(ir)):
        events = node.pop("_events", None) or []
        for event in events:
            actions, _ = refine.resolve_actions(ir, node["id"], event.get("actions") or [], taken)
            if actions:
                refine.merge_event(node, event.get("on") or "click", actions)
                for action in actions:
                    if action["type"] == "navigate" and node["type"] in irm.CLICKABLE_TYPES:
                        node["props"]["href_page"] = action["page"]
    finalize_content(ir)
    _relations(ir)

    if meta.get("primary"):
        ir["meta"]["theme"]["primary"] = refine.normalize_color(meta["primary"])
    rest = [op for op in ops if op.get("op") not in ("create", "add")]
    changes: list[dict] = []
    if rest:
        result = refine.apply_ops(ir, rest)
        ir, changes = result["ir"], result["changes"]
    return ir, changes


def infer_row_geometry(ir: dict) -> None:
    """A spoken component added to a drawn row (e.g. a menu item the detector missed) gets a box right after
    its previous sibling, same line, width from its text, so the row keeps its drawn alignment."""
    for node, _, _ in irm.walk(ir):
        if node.get("layout", {}).get("direction") != "row" or not node.get("bbox"):
            continue
        frame, prev = node["bbox"], None
        for child in node.get("children", []):
            if child.get("bbox"):
                prev = child["bbox"]
                continue
            if prev is None:
                continue
            x = prev["x"] + prev["w"] + 0.015
            w = min(0.012 * max(4, len(child.get("label", ""))) + 0.03, frame["x"] + frame["w"] - x - 0.005)
            if w <= 0.01:
                continue
            child["bbox"] = {"x": round(x, 4), "y": prev["y"], "w": round(w, 4), "h": prev["h"]}
            prev = child["bbox"]


def frame_meta(size: tuple[int, int], content: dict) -> dict:
    """Page frame for the geometry-aware compiler: phone vs desktop from the sketch aspect ratio,
    and the CSS px per sketch px scale so spacing stays proportional to the drawing."""
    width, height = size
    kind = "mobile" if width / max(1, height) < 0.8 else "desktop"
    target = MOBILE_WIDTH if kind == "mobile" else DESKTOP_WIDTH
    page_width = int(max(280, min(DESKTOP_WIDTH, round(content["w"] * target))))
    return {"kind": kind, "sketch_width": width, "sketch_height": height, "content": content,
            "page_width": page_width, "scale": round(page_width / max(1.0, content["w"] * width), 4)}


def default_list_items(node: dict, frame: dict | None) -> list[str]:
    count = 3
    if node.get("bbox") and frame:
        px = node["bbox"]["h"] * frame["sketch_height"] * frame["scale"]
        count = int(max(2, min(6, round(px / 32))))
    return [f"Item {i}" for i in range(1, count + 1)]


def finalize_content(ir: dict) -> list[str]:
    """Every component must render something visible: fill empty labels with neutral placeholders,
    give lists without items default rows, and drop wrapper containers that hold nothing.
    Returns a description of what was changed (used by repair as well)."""
    notes = []
    frame = ir.get("meta", {}).get("frame")
    for node, _, _ in irm.walk(ir):
        if not (node.get("label") or "").strip() and node["type"] in PLACEHOLDER_LABELS:
            node["label"] = PLACEHOLDER_LABELS[node["type"]]
            notes.append(f"placeholder text for {node['id']}")
        if node["type"] == "list" and not node["props"].get("items") and not node.get("children"):
            node["props"]["items"] = default_list_items(node, frame)
            notes.append(f"default items for {node['id']}")
        if node["type"] == "select" and not node["props"].get("options"):
            node["props"]["options"] = ["Option 1", "Option 2", "Option 3"]  # an empty dropdown can never satisfy a required field
            notes.append(f"default options for {node['id']}")
    changed = True
    while changed:  # removing a wrapper can leave its parent empty
        changed = False
        for node, parent, _ in list(irm.walk(ir)):
            if parent is None or node["type"] not in ("container", "card", "form", "header", "navbar") or node.get("children"):
                continue
            if node.get("bbox") and node.get("origin") == "sketch":
                continue  # a drawn empty box stays (the compiler gives it the drawn height)
            parent["children"].remove(node)
            notes.append(f"removed empty wrapper {node['id']}")
            changed = True
    return notes


def fuse(analysis: dict | None, ops: list[dict], title: str | None = None) -> dict:
    """SketchAnalysis + create Ops -> IR (see module docstring)."""
    return fuse_with_report(analysis, ops, title)[0]


def category_from_text(text: str) -> str:
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    for category in ("login", "registration", "dashboard", "profile", "ecommerce", "banking", "booking",
                     "contact", "settings", "landing"):
        if category in words:
            return category
    return "other"
