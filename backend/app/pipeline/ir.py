"""IR (neurogenui.ir/1) helpers shared by fusion, refine, codegen, validate and repair."""
from __future__ import annotations

import re
from typing import Iterator

SCHEMA = "neurogenui.ir/1"

TYPE_PREFIX = {
    "page": "page", "container": "box", "card": "card", "form": "form", "header": "hdr",
    "navbar": "nav", "nav_item": "navi", "heading": "h", "text": "txt", "link": "lnk",
    "button": "btn", "input": "inp", "textarea": "ta", "checkbox": "chk", "radio": "rad",
    "select": "sel", "image": "img", "list": "list", "divider": "div", "icon": "ico",
}
TYPES = tuple(TYPE_PREFIX)
CONTAINER_TYPES = {"page", "container", "card", "form", "header", "navbar", "list"}
FIELD_TYPES = {"input", "textarea", "select"}
CLICKABLE_TYPES = {"button", "link", "nav_item"}
PHOTO_KEYS = ("person", "product", "banner", "food", "travel", "building", "finance", "nature")
DEFAULT_PRIMARY = "#4f46e5"

PROP_KEYS = {
    "heading": {"level"},
    "input": {"inputType", "placeholder", "required", "name"},
    "textarea": {"placeholder", "rows", "required", "name"},
    "checkbox": {"checked", "group"},
    "radio": {"checked", "group"},
    "select": {"options", "required", "name"},
    "image": {"alt", "photo"},
    "link": {"href_page"},
    "nav_item": {"href_page"},
    "button": {"href_page"},
    "list": {"items"},
}
STYLE_KEYS = {"variant", "color", "textColor", "bg", "size", "width", "height", "align",
              "fontSize", "fontWeight", "radius", "hidden"}
INPUT_TYPES = {"text", "email", "password", "tel", "number", "date", "search"}


def slugify(text: str, max_words: int = 3) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return "_".join(words[:max_words])[:28].strip("_")


def new_ir(title: str = "Untitled", category: str = "other", primary: str = DEFAULT_PRIMARY) -> dict:
    ir = {
        "schema": SCHEMA,
        "meta": {"title": title, "category": category,
                 "theme": {"primary": primary, "radius": 10, "font": "Inter"}},
        "pages": [],
        "next_id": 1,
    }
    ir["pages"].append(new_page(ir, "Main", "/", page_id="page_main"))
    return ir


def new_page(ir: dict, name: str, route: str | None = None, page_id: str | None = None) -> dict:
    page_id = page_id or unique_id(ir, "page", name)
    root = make_node(ir, "page", name, node_id=page_id, origin="voice")
    root["layout"] = {"direction": "column", "gap": 16, "align": "stretch", "justify": "start"}
    return {"id": page_id, "name": name, "route": route or "/" + (slugify(name) or page_id).replace("_", "-"), "root": root}


def all_ids(ir: dict) -> set[str]:
    return {n["id"] for n, _, _ in walk(ir)}


def unique_id(ir: dict, node_type: str, label: str = "", taken: set[str] | None = None) -> str:
    """<prefix>_<slug>[_n]; unlabeled nodes use the document counter next_id."""
    taken = all_ids(ir) if taken is None else taken
    prefix = TYPE_PREFIX.get(node_type, "box")
    slug = slugify(label)
    if not slug:
        while True:
            n = ir.get("next_id", 1)
            ir["next_id"] = n + 1
            candidate = f"{prefix}_{n}"
            if candidate not in taken:
                return candidate
    base = f"{prefix}_{slug}"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}_{n}", n + 1
    ir["next_id"] = ir.get("next_id", 1) + 1
    return candidate


def make_node(ir: dict, node_type: str, label: str = "", *, props=None, style=None, bbox=None,
              origin: str = "voice", node_id: str | None = None, taken: set[str] | None = None) -> dict:
    node_type = node_type if node_type in TYPE_PREFIX else "container"
    node = {
        "id": node_id or unique_id(ir, node_type, label, taken),
        "type": node_type,
        "label": label or "",
        "props": clean_props(node_type, props or {}),
        "style": clean_style(style or {}),
        "bbox": bbox,
        "relations": [],
        "events": [],
        "origin": origin,
    }
    if taken is not None:
        taken.add(node["id"])
    if node_type in CONTAINER_TYPES:
        direction = "row" if node_type in ("navbar", "header") else "column"
        node["layout"] = {"direction": direction, "gap": 12, "align": "stretch" if direction == "column" else "center",
                          "justify": "between" if node_type in ("navbar", "header") else "start"}
        node["children"] = []
    return node


def clean_props(node_type: str, props: dict) -> dict:
    allowed = PROP_KEYS.get(node_type, set())
    out = {k: v for k, v in props.items() if k in allowed and v is not None}
    if node_type == "input":
        if out.get("inputType") not in INPUT_TYPES:
            out.pop("inputType", None)
    if node_type == "heading" and "level" in out:
        try:
            out["level"] = max(1, min(4, int(out["level"])))
        except (TypeError, ValueError):
            out.pop("level")
    if node_type == "image" and out.get("photo") not in (*PHOTO_KEYS, ""):
        out.pop("photo", None)
    return out


def clean_style(style: dict) -> dict:
    out = {}
    for key, value in style.items():
        if key not in STYLE_KEYS or value is None or value == "":
            continue
        if key in ("height", "fontSize", "radius", "fontWeight"):
            try:
                value = int(float(value))
            except (TypeError, ValueError):
                continue
        if key == "width" and value not in ("auto", "full"):
            try:
                value = int(float(str(value).replace("px", "")))
            except (TypeError, ValueError):
                continue
        out[key] = value
    return out


def walk(ir: dict) -> Iterator[tuple[dict, dict | None, dict]]:
    """Yield (node, parent, page) depth-first in document order."""
    for page in ir.get("pages", []):
        stack = [(page["root"], None)]
        while stack:
            node, parent = stack.pop()
            yield node, parent, page
            for child in reversed(node.get("children", [])):
                stack.append((child, node))


def find(ir: dict, node_id: str) -> tuple[dict | None, dict | None, dict | None]:
    for node, parent, page in walk(ir):
        if node["id"] == node_id:
            return node, parent, page
    return None, None, None


def find_page(ir: dict, page_id_or_name: str) -> dict | None:
    key = (page_id_or_name or "").strip().lower()
    for page in ir.get("pages", []):
        if key in (page["id"].lower(), page["name"].lower(), slugify(page["name"])):
            return page
    return None


def nodes(ir: dict, node_type: str | None = None) -> list[dict]:
    return [n for n, _, _ in walk(ir) if node_type is None or n["type"] == node_type]


def ancestors(ir: dict, node_id: str) -> list[dict]:
    """Ancestors from the node's parent up to the page root."""
    parents = {n["id"]: p for n, p, _ in walk(ir)}
    out, cur = [], parents.get(node_id)
    while cur is not None:
        out.append(cur)
        cur = parents.get(cur["id"])
    return out


def is_hidden(ir: dict, node_id: str) -> bool:
    node, _, _ = find(ir, node_id)
    if node is None:
        return False
    return bool(node.get("style", {}).get("hidden")) or any(a.get("style", {}).get("hidden") for a in ancestors(ir, node_id))


def union_bbox(boxes: list[dict]) -> dict | None:
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["w"] for b in boxes)
    y1 = max(b["y"] + b["h"] for b in boxes)
    return {"x": round(x0, 4), "y": round(y0, 4), "w": round(x1 - x0, 4), "h": round(y1 - y0, 4)}


def iou(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    ix = max(0.0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0.0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    inter = ix * iy
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def contains(outer: dict, inner: dict, min_frac: float = 0.85) -> bool:
    """True when at least min_frac of inner's area lies inside outer."""
    ix = max(0.0, min(outer["x"] + outer["w"], inner["x"] + inner["w"]) - max(outer["x"], inner["x"]))
    iy = max(0.0, min(outer["y"] + outer["h"], inner["y"] + inner["h"]) - max(outer["y"], inner["y"]))
    area = inner["w"] * inner["h"]
    return area > 0 and ix * iy / area >= min_frac and outer["w"] * outer["h"] > area


def outline(ir: dict) -> str:
    """Compact text outline (id | type | label | parent) shown to the intent LLM."""
    lines = []
    for node, parent, page in walk(ir):
        extra = ""
        if node["type"] == "input" and node["props"].get("inputType"):
            extra = f" ({node['props']['inputType']})"
        if node["type"] == "page":
            lines.append(f"{node['id']} | page | {page['name']} | -")
        else:
            lines.append(f"{node['id']} | {node['type']}{extra} | {node['label']!r} | {parent['id'] if parent else '-'}")
    return "\n".join(lines)
