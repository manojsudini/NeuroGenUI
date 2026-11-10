"""Voice-guided refinement: apply Ops to an IR.

`apply_ops` is pure: it deep-copies the input, changes only the nodes an op targets
(untouched nodes stay byte-identical) and reports every change as ok/error.
"""
from __future__ import annotations

import copy
import difflib
import re

from . import ir as irm

COLOR_WORDS: dict[str, str] = {
    "blue": "#2563eb", "light blue": "#60a5fa", "dark blue": "#1e40af", "navy": "#1e3a8a",
    "sky": "#0ea5e9", "sky blue": "#0ea5e9", "cyan": "#06b6d4", "teal": "#0d9488",
    "turquoise": "#14b8a6", "green": "#16a34a", "light green": "#4ade80", "dark green": "#166534",
    "lime": "#65a30d", "emerald": "#059669", "mint": "#34d399", "olive": "#4d7c0f",
    "yellow": "#eab308", "gold": "#ca8a04", "amber": "#f59e0b", "orange": "#ea580c",
    "red": "#dc2626", "light red": "#f87171", "dark red": "#991b1b", "crimson": "#be123c",
    "maroon": "#7f1d1d", "pink": "#ec4899", "hot pink": "#db2777", "magenta": "#c026d3",
    "rose": "#e11d48", "purple": "#9333ea", "violet": "#7c3aed", "indigo": "#4f46e5",
    "lavender": "#a78bfa", "brown": "#92400e", "beige": "#f5f5dc", "black": "#111827",
    "white": "#ffffff", "gray": "#6b7280", "grey": "#6b7280", "light gray": "#e5e7eb",
    "light grey": "#e5e7eb", "dark gray": "#374151", "dark grey": "#374151", "silver": "#cbd5e1",
    "slate": "#475569", "coral": "#f97362",
}
COLOR_STYLE_KEYS = ("color", "textColor", "bg")

TYPE_WORDS: dict[str, str] = {
    "button": "button", "buttons": "button", "btn": "button", "cta": "button",
    "field": "input", "fields": "input", "input": "input", "inputs": "input", "textbox": "input",
    "textfield": "input", "textarea": "textarea", "link": "link", "links": "link",
    "image": "image", "images": "image", "picture": "image", "photo": "image", "img": "image",
    "logo": "image", "avatar": "image", "banner": "image",
    "heading": "heading", "title": "heading", "headline": "heading", "header": "header",
    "text": "text", "paragraph": "text", "label": "text", "caption": "text", "description": "text",
    "checkbox": "checkbox", "check": "checkbox", "tickbox": "checkbox", "radio": "radio",
    "dropdown": "select", "select": "select", "menu": "navbar", "navbar": "navbar",
    "navigation": "navbar", "nav": "navbar", "tab": "nav_item", "navitem": "nav_item", "card": "card", "form": "form",
    "container": "container", "section": "container", "panel": "container",
    "divider": "divider", "separator": "divider", "line": "divider", "icon": "icon", "list": "list",
}
COMPATIBLE = [{"button", "link", "nav_item"}, {"input", "textarea", "select"}, {"heading", "text"},
              {"container", "card", "form", "header", "list"}, {"checkbox", "radio"}, {"navbar", "header"}]
ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3,
            "fifth": 4, "5th": 4, "last": -1, "top": 0, "bottom": -1, "final": -1}
STOPWORDS = {"the", "a", "an", "my", "this", "that", "to", "of", "on", "in", "with", "for", "and", "it",
             "page", "one", "ui", "element", "component"}
INPUT_TYPE_WORDS = {"email": "email", "mail": "email", "password": "password", "phone": "tel",
                    "mobile": "tel", "telephone": "tel", "number": "number", "date": "date", "search": "search"}
DEFAULT_SIZES = ("sm", "md", "lg")
SIZE_FACTORS = {"sm": 0.7, "md": 1.0, "lg": 1.4}
SCALED_BOXES = {"image", "textarea", "container", "card"}
FIELD_ONLY_PROPS = {"placeholder", "required", "inputType", "rows", "options", "name"}
OPTION_TYPES = {"radio", "checkbox"}
TEXT_SIZED = {"heading", "text", "link", "nav_item", "label"}
DEFAULT_WIDTHS = {"button": 160, "input": 280, "select": 280, "textarea": 320, "image": 240, "card": 320}
DEFAULT_HEIGHTS = {"button": 40, "input": 40, "select": 40, "image": 180, "card": 160, "container": 120}
DEFAULT_FONTS = {"heading": 28, "text": 15, "link": 15, "nav_item": 15, "button": 15}
RESOLVE_THRESHOLD = 0.35


# --------------------------------------------------------------------------- colours

def normalize_color(value) -> str | None:
    """Map colour words ("blue", "dark green") to hex; pass CSS colours through."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}([0-9a-f]{3})?", text) or text.startswith(("rgb", "hsl")):
        return text
    text = re.sub(r"\b(colou?r(ed)?|the|shade|of)\b", " ", text).strip()
    text = re.sub(r"\s+", " ", text)
    if text in COLOR_WORDS:
        return COLOR_WORDS[text]
    for word in sorted(COLOR_WORDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", text):
            return COLOR_WORDS[word]
    return str(value).strip() or None


def normalize_style(style: dict) -> dict:
    out = dict(style)
    for key in COLOR_STYLE_KEYS:
        if key in out and out[key] is not None:
            out[key] = normalize_color(out[key])
    return out


# --------------------------------------------------------------------------- target resolution

ITEM_PHRASES = re.compile(r"\b(nav[ _-]?items?|navigation items?|menu items?|nav links?|menu links?)\b")


def _tokens(text: str) -> list[str]:
    text = ITEM_PHRASES.sub(" navitem ", (text or "").lower())  # "Pricing nav item" is an item, not the bar
    return re.findall(r"[a-z0-9]+", text)


def _node_tokens(node: dict) -> set[str]:
    words = set(_tokens(node.get("label", "")))
    words |= set(_tokens(node["id"].split("_", 1)[-1]))
    props = node.get("props", {})
    for key in ("inputType", "placeholder", "name", "alt", "photo"):
        if props.get(key):
            words |= set(_tokens(str(props[key])))
    if props.get("inputType") == "tel":
        words |= {"phone", "mobile"}
    return words


def _token_match(word: str, candidates: set[str]) -> float:
    if word in candidates:
        return 1.0
    best = max((difflib.SequenceMatcher(None, word, c).ratio() for c in candidates), default=0.0)
    return best if best >= 0.8 else 0.0


def _type_score(wanted: str | None, actual: str) -> float:
    if wanted is None:
        return 0.5
    if wanted == actual:
        return 1.0
    if any(wanted in group and actual in group for group in COMPATIBLE):
        return 0.6
    return 0.0


def _ref_type_conflict(ref: str, node_type: str) -> bool:
    """True when the words of a reference name a component type incompatible with node_type."""
    wanted = next((TYPE_WORDS[w] for w in reversed(_tokens(ref)) if w in TYPE_WORDS), None)
    return wanted is not None and _type_score(wanted, node_type) == 0.0


def resolve_target(ir: dict, ref, type_hint: str | None = None) -> dict:
    """Deterministically map a spoken reference ("the second button", "email field") to a node id."""
    if isinstance(ref, dict):
        ref = ref.get("ref") or ref.get("id") or ""
    ref = str(ref or "").strip()
    if not ref:
        return {"id": None, "score": 0.0}
    node, _, _ = irm.find(ir, ref)
    if node is not None:
        return {"id": node["id"], "score": 1.0}
    page = irm.find_page(ir, ref)
    if page is not None and type_hint in (None, "page"):
        return {"id": page["root"]["id"], "score": 0.9}

    words = _tokens(ref)
    wanted_type = type_hint if type_hint in irm.TYPE_PREFIX else None
    ordinal = None
    label_words = []
    box_hint = "box" in words  # "search box", "message box": usually a field, but not decisive
    words = [w for w in words if w != "box"]
    head = next((w for w in reversed(words) if w in TYPE_WORDS), None)  # "Select flight button" -> button
    for w in words:
        if w in ORDINALS and ordinal is None:
            ordinal = ORDINALS[w]
        elif w == head and wanted_type is None:
            wanted_type = TYPE_WORDS[w]
        elif w in STOPWORDS:
            continue
        else:
            label_words.append(w)  # other type-like words ("select" in "Select flight") are label text
    # "password" alone means the password field; "email" alone the email field.
    if wanted_type is None and len(label_words) == 1 and label_words[0] in INPUT_TYPE_WORDS:
        wanted_type = "input"

    scored = []
    for node, _, _ in irm.walk(ir):
        if node["type"] == "page" and wanted_type != "page":
            continue
        t_score = _type_score(wanted_type, node["type"])
        if wanted_type is not None and t_score == 0.0:
            continue
        if label_words:
            node_words = _node_tokens(node)
            l_score = sum(_token_match(w, node_words) for w in label_words) / len(label_words)
            if node["type"] == "input" and any(INPUT_TYPE_WORDS.get(w) == node["props"].get("inputType") for w in label_words):
                l_score = max(l_score, 0.9)
        else:
            l_score = None
        if l_score is None:
            score = 0.8 * t_score
        elif wanted_type is None:
            score = l_score * 0.9
        else:
            score = 0.4 * t_score + 0.6 * l_score
        if box_hint and node["type"] in irm.FIELD_TYPES:
            score += 0.15
        scored.append((score, node))

    if not scored:
        return {"id": None, "score": 0.0}
    best = max(s for s, _ in scored)
    if ordinal is not None:
        # Ordinals pick among nodes of the wanted type, in document (reading) order.
        pool = [n for s, n in scored if s >= best - 0.05] if label_words else \
               [n for s, n in scored if _type_score(wanted_type, n["type"]) == 1.0] or [n for _, n in scored]
        if -len(pool) <= ordinal < len(pool):
            return {"id": pool[ordinal]["id"], "score": round(max(best, 0.75), 3)}
        return {"id": None, "score": 0.0}
    ties = [n for s, n in scored if s == best]
    score = best if len(ties) == 1 else best * 0.85
    if score < RESOLVE_THRESHOLD:
        return {"id": None, "score": round(score, 3)}
    return {"id": ties[0]["id"], "score": round(score, 3)}


# --------------------------------------------------------------------------- tree editing helpers

def _parent_of(ir: dict, node_id: str) -> tuple[dict | None, dict | None]:
    node, parent, _ = irm.find(ir, node_id)
    return node, parent


def _detach(ir: dict, node_id: str) -> dict | None:
    node, parent = _parent_of(ir, node_id)
    if node is None or parent is None:
        return None
    parent["children"].remove(node)
    _collapse_row(ir, parent)
    return node


def _collapse_row(ir: dict, box: dict) -> None:
    """Remove auto-created wrappers (sketch rows, move stacks) left with zero or one child."""
    if box["type"] != "container" or box.get("label"):
        return
    if box.get("layout", {}).get("direction") != "row" and box.get("origin") == "sketch":
        return
    if len(box["children"]) > 1:
        return
    _, grand = _parent_of(ir, box["id"])
    if grand is None:
        return
    idx = grand["children"].index(box)
    grand["children"][idx:idx + 1] = box["children"]


def _direction(node: dict) -> str:
    return node.get("layout", {}).get("direction", "column")


def insert_relative(ir: dict, new: dict, anchor_id: str | None, relation: str | None, taken: set[str],
                    stack_in_row: bool = True) -> str:
    """Insert `new` relative to an anchor node. Returns a short description of where it went."""
    relation = (relation or "below").lower()
    relation = {"after": "below", "under": "below", "before": "above", "over": "above", "into": "inside",
                "left": "left_of", "right": "right_of", "beside": "right_of", "next_to": "right_of"}.get(relation, relation)
    anchor, parent = _parent_of(ir, anchor_id) if anchor_id else (None, None)
    if anchor is None:
        root = ir["pages"][0]["root"]
        if relation == "first":
            root["children"].insert(0, new)
        else:
            root["children"].append(new)
        return f"{relation} of page"

    if relation in ("inside", "first", "last") and "children" in anchor:
        if relation == "first":
            anchor["children"].insert(0, new)
        else:
            anchor["children"].append(new)
        return f"{relation} {anchor['id']}"
    if parent is None:  # anchor is a page root
        anchor["children"].insert(0 if relation in ("above", "first") else len(anchor["children"]), new)
        return f"{relation} {anchor['id']}"

    vertical = relation in ("below", "above", "inside", "first", "last")
    if relation in ("below", "above") and _direction(parent) == "row" and not stack_in_row:
        # placing "after" something that sits in a row: go below the whole row
        row, grand = anchor, parent
        while grand is not None and _direction(grand) == "row":
            row, grand = grand, _parent_of(ir, grand["id"])[1]
        if grand is not None:
            anchor, parent = row, grand
    if relation in ("below", "above") and _direction(parent) == "row":
        # "below the password field" when the field sits in a row: stack the two in a column in the
        # anchor's slot, so the new node really ends up under the anchor (not to its right).
        stack = irm.make_node(ir, "container", "", origin=new.get("origin", "voice"), taken=taken)
        stack["layout"] = {"direction": "column", "gap": 8, "align": "stretch", "justify": "start"}
        stack["bbox"] = anchor.get("bbox")
        stack["children"] = [anchor, new] if relation == "below" else [new, anchor]
        parent["children"][parent["children"].index(anchor)] = stack
        return f"{relation} {anchor['id']}"
    siblings = parent["children"]
    idx = siblings.index(anchor)
    if vertical:
        siblings.insert(idx if relation in ("above", "first") else idx + 1, new)
        return f"{relation} {anchor['id']}"
    if _direction(parent) == "row":
        siblings.insert(idx if relation == "left_of" else idx + 1, new)
        return f"{relation} {anchor['id']}"
    row = irm.make_node(ir, "container", "", origin=new.get("origin", "voice"), taken=taken)
    row["layout"] = {"direction": "row", "gap": 12, "align": "center", "justify": "start"}
    row["bbox"] = anchor.get("bbox")
    row["children"] = [new, anchor] if relation == "left_of" else [anchor, new]
    siblings[idx] = row
    return f"{relation} {anchor['id']}"


def default_anchor(ir: dict, node_type: str) -> tuple[str | None, str]:
    """Sensible position for a component added without a position."""
    order = [n for n, _, _ in irm.walk(ir)]
    fields = [n for n in order if n["type"] in irm.FIELD_TYPES | {"checkbox", "radio"}]
    buttons = [n for n in order if n["type"] == "button"]
    if node_type == "heading":
        return ir["pages"][0]["root"]["id"], "first"
    if node_type == "navbar":
        return ir["pages"][0]["root"]["id"], "first"
    if node_type == "nav_item":
        navs = [n for n in order if n["type"] == "navbar"]
        if navs:
            return navs[0]["id"], "last"
    if node_type in irm.FIELD_TYPES | {"checkbox", "radio"} and fields:
        return fields[-1]["id"], "below"
    if node_type == "button" and buttons:
        return buttons[-1]["id"], "below"
    if node_type == "button" and fields:
        return fields[-1]["id"], "below"
    if node_type == "link" and buttons:
        return buttons[-1]["id"], "below"
    return ir["pages"][0]["root"]["id"], "last"


def field_scope(ir: dict, node_id: str) -> list[str]:
    """Fields belonging to the same form/container as node_id (falls back to the whole page)."""
    node, _, page = irm.find(ir, node_id)
    if node is None:
        return []
    for container in [node, *irm.ancestors(ir, node_id)]:
        if "children" not in container:
            continue
        found = [n["id"] for n in _subtree(container) if n["type"] in irm.FIELD_TYPES]
        if found:
            return found
    return [n["id"] for n in _subtree(page["root"]) if n["type"] in irm.FIELD_TYPES]


def _subtree(node: dict) -> list[dict]:
    out, stack = [], [node]
    while stack:
        cur = stack.pop()
        out.append(cur)
        stack.extend(reversed(cur.get("children", [])))
    return out


def ensure_page(ir: dict, name: str, taken: set[str]) -> tuple[dict, bool]:
    """Find a page by id/name, or create it with a heading, a short text and a back link."""
    page = irm.find_page(ir, name)
    if page is not None:
        return page, False
    title = name.strip().title() or "New Page"
    page = irm.new_page(ir, title, page_id=irm.unique_id(ir, "page", title, taken))
    taken.add(page["id"])
    root = page["root"]
    heading = irm.make_node(ir, "heading", title, props={"level": 1}, taken=taken)
    text = irm.make_node(ir, "text", f"Welcome to the {title} page.", taken=taken)
    back = irm.make_node(ir, "link", "Back", props={"href_page": ir["pages"][0]["id"]}, taken=taken)
    back["events"] = [{"on": "click", "actions": [{"type": "navigate", "page": ir["pages"][0]["id"]}]}]
    root["children"] = [heading, text, back]
    ir["pages"].append(page)
    return page, True


def resolve_actions(ir: dict, owner_id: str, actions: list[dict], taken: set[str]) -> tuple[list[dict], list[str]]:
    """Turn refs inside actions into ids; fill default targets. Returns (actions, problems)."""
    out, problems = [], []
    for raw in actions or []:
        action = {k: v for k, v in dict(raw).items() if v is not None}
        kind = action.get("type")
        if kind == "validate_required":
            targets = []
            for ref in action.get("targets") or []:
                rid = resolve_target(ir, ref, "input")["id"]
                if rid and rid not in targets:
                    targets.append(rid)
            action["targets"] = targets or field_scope(ir, owner_id)
            action.setdefault("message", "Please fill in all required fields")
            if not action["targets"]:
                problems.append("validate_required: no fields to validate")
                continue
        elif kind == "validate_format":
            fmt = action.get("format", "email")
            action["format"] = fmt if fmt in ("email", "phone", "number") else "email"
            target = resolve_target(ir, action.get("target"), "input")["id"] if action.get("target") else None
            if not target:
                wanted = {"email": "email", "phone": "tel", "number": "number"}[action["format"]]
                scope = field_scope(ir, owner_id)
                target = next((i for i in scope if irm.find(ir, i)[0]["props"].get("inputType") == wanted), None)
            if not target:
                problems.append(f"validate_format: no {action['format']} field")
                continue
            action["target"] = target
            action.setdefault("message", {"email": "Enter a valid email address", "phone": "Enter a valid phone number",
                                          "number": "Enter a number"}[action["format"]])
        elif kind == "navigate":
            page, _ = ensure_page(ir, str(action.get("page") or "Home"), taken)
            action["page"] = page["id"]
        elif kind in ("toggle_visibility", "set_text"):
            target = resolve_target(ir, action.get("target"))["id"]
            if not target:
                problems.append(f"{kind}: target {action.get('target')!r} not found")
                continue
            action["target"] = target
            if kind == "set_text":
                action.setdefault("text", "")
        elif kind == "show_message":
            action.setdefault("text", "Done")
            action["tone"] = action.get("tone") if action.get("tone") in ("success", "error", "info") else "info"
        else:
            problems.append(f"unknown action type {kind!r}")
            continue
        out.append(_ordered_action(action))
    return out, problems


ACTION_KEY_ORDER = ("type", "targets", "target", "format", "page", "text", "tone", "message")


def _ordered_action(action: dict) -> dict:
    keys = [k for k in ACTION_KEY_ORDER if k in action] + [k for k in action if k not in ACTION_KEY_ORDER]
    return {k: action[k] for k in keys}


def merge_event(node: dict, on: str, actions: list[dict]) -> None:
    """Merge actions into node.events[on]: same-kind actions are replaced, validations run first."""
    events = node.setdefault("events", [])
    event = next((e for e in events if e.get("on") == on), None)
    if event is None:
        event = {"on": on, "actions": []}
        events.append(event)
    merged = list(event["actions"])
    for action in actions:
        same = next((i for i, a in enumerate(merged) if a["type"] == action["type"] and
                     a.get("target") == action.get("target")), None)
        if same is None:
            merged.append(action)
        else:
            merged[same] = action
    merged.sort(key=lambda a: 0 if a["type"].startswith("validate_") else 1)
    event["actions"] = merged


# --------------------------------------------------------------------------- applying ops

class _Applier:
    def __init__(self, ir: dict):
        self.ir = copy.deepcopy(ir)
        self.taken = irm.all_ids(self.ir)
        self.changes: list[dict] = []

    # helpers ------------------------------------------------------------
    def target_id(self, op: dict, type_hint: str | None = None) -> tuple[str | None, str]:
        target = op.get("target") or {}
        if isinstance(target, str):
            target = {"ref": target}
        ref = target.get("ref") or ""
        tid = target.get("id")
        node = irm.find(self.ir, tid)[0] if tid else None
        if node is not None and _ref_type_conflict(ref, node["type"]):
            node = None  # e.g. "the email field" given the id of the "Email" text label
        if node is not None:
            return tid, ref or tid
        resolved = resolve_target(self.ir, ref or tid or "", type_hint)
        return resolved["id"], ref or tid or ""

    def anchor_id(self, position: dict | None) -> str | None:
        anchor = (position or {}).get("anchor") or {}
        if isinstance(anchor, str):
            anchor = {"ref": anchor}
        aid = anchor.get("id")
        ref = anchor.get("ref") or aid
        if aid and irm.find(self.ir, aid)[0] is not None and not _ref_type_conflict(ref or "", irm.find(self.ir, aid)[0]["type"]):
            found = aid
        else:
            found = resolve_target(self.ir, ref)["id"] if ref else None
        return self._option_group_edge(found, ref, (position or {}).get("relation"))

    def _option_group_edge(self, anchor_id: str | None, ref: str | None, relation: str | None) -> str | None:
        """"below the time slots" names the whole group of radio buttons / checkboxes, not one option:
        use the last (below) or first (above) option of the run of options that contains the anchor."""
        node = irm.find(self.ir, anchor_id)[0] if anchor_id else None
        words = _tokens(ref or "")
        if node is None or node["type"] not in OPTION_TYPES or not words or relation not in ("below", "above", "after", "before"):
            return anchor_id
        if not (words[-1].endswith("s") and not words[-1].endswith("ss")):
            return anchor_id  # singular reference: that one option
        order = [n for n, _, _ in irm.walk(self.ir) if "children" not in n or n["type"] in OPTION_TYPES]
        pos = next((i for i, n in enumerate(order) if n["id"] == anchor_id), None)
        if pos is None:
            return anchor_id
        stop = lambda n: n["type"] in irm.FIELD_TYPES or n["type"] in irm.CLICKABLE_TYPES  # noqa: E731
        edge, step = pos, (1 if relation in ("below", "after") else -1)
        i = pos + step
        while 0 <= i < len(order) and not stop(order[i]) and order[i]["type"] != "heading":
            if order[i]["type"] in OPTION_TYPES:
                edge = i
            i += step
        return order[edge]["id"]

    def record(self, op: str, target: str | None, detail: str, ok: bool = True, error: str | None = None) -> None:
        change = {"op": op, "target": target, "detail": detail, "ok": ok}
        if error:
            change["error"] = error
        self.changes.append(change)

    def build_node(self, comp: dict, origin: str = "voice") -> dict:
        node_type = comp.get("type") if comp.get("type") in irm.TYPE_PREFIX else "text"
        style = normalize_style(comp.get("style") or {})
        node = irm.make_node(self.ir, node_type, comp.get("label") or "", props=comp.get("props") or {},
                             style=style, origin=origin, taken=self.taken)
        if node_type == "input" and "inputType" not in node["props"]:
            node["props"]["inputType"] = guess_input_type(node["label"])
        for child in comp.get("children") or []:
            if "children" in node:
                node["children"].append(self.build_node(child, origin))
        return node

    # ops ------------------------------------------------------------------
    def add(self, op: dict) -> None:
        comp = op.get("component") or {}
        if not comp.get("type"):
            return self.record("add", None, "no component given", False, "missing component")
        node = self.build_node(comp)
        position = op.get("position") or {}
        anchor = self.anchor_id(position)
        relation = position.get("relation")
        if anchor is None:
            if (position.get("anchor") or {}).get("ref"):
                return self.record("add", node["id"], "", False, f"anchor {position['anchor']['ref']!r} not found")
            anchor, relation = default_anchor(self.ir, node["type"])
        where = insert_relative(self.ir, node, anchor, relation, self.taken)
        _set_relation(node, where)
        for event in comp.get("events") or []:
            actions, _ = resolve_actions(self.ir, node["id"], event.get("actions") or [], self.taken)
            if actions:
                merge_event(node, event.get("on", "click"), actions)
        self.record("add", node["id"], f"added {node['type']} {node['label']!r} {where}")

    def remove(self, op: dict) -> None:
        tid, ref = self.target_id(op)
        node, _, _ = irm.find(self.ir, tid) if tid else (None, None, None)
        if node is None:
            return self.record("remove", None, "", False, f"target {ref!r} not found")
        if node["type"] == "page":
            return self._remove_page(tid)
        removed_ids = {n["id"] for n in _subtree(node)}
        for gone in _subtree(node):
            if gone.get("bbox") and gone.get("origin") == "sketch":
                self.ir["meta"].setdefault("removed_sketch", []).append(
                    {"type": gone["type"], "label": gone["label"], "bbox": gone["bbox"]})
        _detach(self.ir, tid)
        self._drop_references(removed_ids)
        self.ir["meta"].setdefault("removed_ids", []).extend(sorted(removed_ids))  # intentional: not a defect
        self.record("remove", tid, f"removed {node['type']} {node['label']!r}")

    def _remove_page(self, page_root_id: str) -> None:
        page = next((p for p in self.ir["pages"] if p["root"]["id"] == page_root_id), None)
        if page is None or page is self.ir["pages"][0]:
            return self.record("remove", page_root_id, "", False, "the main page cannot be removed")
        self.ir["pages"].remove(page)
        self.record("remove", page_root_id, f"removed page {page['name']!r}")

    def _drop_references(self, removed: set[str]) -> None:
        for node, _, _ in irm.walk(self.ir):
            if any(r.get("target") in removed for r in node.get("relations", [])):
                node["relations"] = [r for r in node["relations"] if r.get("target") not in removed]
            touched = False
            for event in node.get("events", []):
                kept = []
                for action in event["actions"]:
                    if action.get("target") in removed:
                        touched = True
                        continue
                    if any(t in removed for t in action.get("targets", [])):
                        touched = True
                        action = {**action, "targets": [t for t in action["targets"] if t not in removed]}
                        if not action["targets"]:
                            continue
                    kept.append(action)
                event["actions"] = kept
            if touched:
                node["events"] = [e for e in node["events"] if e["actions"]]

    def modify(self, op: dict, kind: str = "modify") -> None:
        tid, ref = self.target_id(op)
        node, _, _ = irm.find(self.ir, tid) if tid else (None, None, None)
        changes = op.get("changes") or {}
        if node is None and set(k for k, v in (changes.get("props") or {}).items() if v is not None) & FIELD_ONLY_PROPS:
            node = self._promote_label_to_field(ref)
            tid = node["id"] if node else tid
        if node is None:
            return self.record(kind, None, "", False, f"target {ref!r} not found")
        details = []
        if changes.get("label") is not None and kind == "modify":
            node["label"] = str(changes["label"])
            details.append(f"label={node['label']!r}")
        if changes.get("props"):
            props = dict(node["props"])
            for key, value in changes["props"].items():
                if value is None:
                    props.pop(key, None)
                else:
                    props[key] = value
            node["props"] = irm.clean_props(node["type"], props)
            details.append(f"props={changes['props']}")
        style_changes = normalize_style(changes.get("style") or {})
        if node["type"] == "page" and kind == "style" and style_changes.get("color"):
            self.ir["meta"]["theme"]["primary"] = style_changes["color"]
            details.append(f"theme primary={style_changes['color']}")
        elif style_changes:
            self._merge_style(node, style_changes)
            details.append(f"style={style_changes}")
            if "hidden" in style_changes:
                hidden = self.ir["meta"].setdefault("hidden_by_user", [])
                if style_changes["hidden"] and tid not in hidden:
                    hidden.append(tid)
                elif not style_changes["hidden"] and tid in hidden:
                    hidden.remove(tid)
        if not details:
            return self.record(kind, tid, "", False, "no changes given")
        self.record(kind, tid, ", ".join(details))

    def _promote_label_to_field(self, ref: str) -> dict | None:
        """"the email field" when the UI only has a text "Email" where the field should be (a drawn input whose
        label was read as plain text): the user speaks of a field, so that text node becomes the input."""
        words = _tokens(ref)
        if not any(TYPE_WORDS.get(w) in irm.FIELD_TYPES for w in words):
            return None
        label_words = {w for w in words if w not in STOPWORDS and w not in TYPE_WORDS and w != "box"}
        cands = [n for n, _, _ in irm.walk(self.ir) if n["type"] in ("text", "heading") and "children" not in n
                 and label_words and label_words <= set(_tokens(n.get("label", "")))]
        if len(cands) != 1:
            return None
        node = cands[0]
        node["type"] = "input"
        node["props"] = irm.clean_props("input", {"inputType": guess_input_type(node.get("label", ""))})
        return node

    @staticmethod
    def _merge_style(node: dict, changes: dict) -> None:
        style = dict(node.get("style", {}))
        for key, value in changes.items():
            if value is None:
                style.pop(key, None)
            else:
                style[key] = value
        if "color" in changes and node["type"] == "button" and style.get("variant") in ("ghost", "outline", "secondary"):
            style["variant"] = "primary"
        node["style"] = irm.clean_style(style)

    def resize(self, op: dict) -> None:
        """Resize `target`. Semantics (all deterministic, see RELATIVE SIZES below):

        - style.width == "full"      -> full width of the container (button, input, image, ...)
        - scale s (+ optional axis)  -> multiply the current extent by s. `axis` is "width", "height" or "both"
                                        (default): both scales every extent the node type has (text: font size;
                                        button: height + font; image/card/input: drawn width and height;
                                        textarea: rows). The current extent is the explicit style value, else the
                                        size drawn in the sketch, else a per-type default.
        - a size word sm|md|lg       -> the same as scale 0.7 / 1.0 / 1.4 relative to the current size word
        - absolute width/height/fontSize/rows -> applied as given
        """
        tid, ref = self.target_id(op)
        node, _, _ = irm.find(self.ir, tid) if tid else (None, None, None)
        if node is None:
            return self.record("resize", None, "", False, f"target {ref!r} not found")
        changes = op.get("changes") or {}
        style = {k: v for k, v in (changes.get("style") or {}).items() if v is not None}
        rows = (changes.get("props") or {}).get("rows")
        scale = op.get("scale") or changes.get("scale") or style.pop("scale", None)
        axis = op.get("axis") or changes.get("axis") or "both"
        current = node.get("style", {})
        if not scale and style.get("size") in SIZE_FACTORS and not any(k in style for k in ("width", "height", "fontSize")):
            # a size word is a step on the size scale: turn it into a relative factor
            word = style["size"]
            scale = SIZE_FACTORS[word] / SIZE_FACTORS.get(current.get("size", "md"), 1.0)
            if abs(scale - 1) < 0.01:  # "small" while already sm/md-sized: still apply the full step
                scale = SIZE_FACTORS[word]
            axis = "both"
        if scale:
            style.pop("size", None)  # the size word is recomputed from the factor
            style.update(self._scaled(node, float(scale), axis))
        if node["type"] == "textarea" and (rows or scale) and axis in ("both", "height"):
            base = node["props"].get("rows") or max(2, round((drawn_height(self.ir, node) or 96) / 24))
            rows = int(rows or max(2, round(base * float(scale))))
            node["props"] = {**node["props"], "rows": rows}
        elif rows:
            node["props"] = {**node["props"], "rows": int(rows)}
        if not style and not rows:
            return self.record("resize", tid, "", False, "no size given")
        if style:
            self._merge_style(node, style)
        applied = {k: node["style"].get(k) for k in style}
        if rows:
            applied["rows"] = node["props"].get("rows")
        self.record("resize", tid, f"style={applied}")

    def _scaled(self, node: dict, scale: float, axis: str) -> dict:
        """Style keys for `node` after multiplying its extent by `scale` along `axis`."""
        kind, current = node["type"], node.get("style", {})
        out: dict = {}
        scale = max(0.2, min(4.0, scale))
        page_w = (self.ir.get("meta", {}).get("frame") or {}).get("page_width") or 1000
        text_like = kind in TEXT_SIZED
        if axis in ("width", "both") and kind not in TEXT_SIZED | {"icon", "divider"}:
            base = current.get("width") if isinstance(current.get("width"), int) else \
                drawn_width(self.ir, node) or (None if axis == "both" else DEFAULT_WIDTHS.get(kind, 280))
            if current.get("width") == "full" and scale > 1:
                base = None  # already as wide as it gets
            elif current.get("width") == "full":
                base = page_w
            if base:
                width = round(base * scale)
                out["width"] = "full" if scale > 1 and width >= 0.95 * page_w else max(40, width)
        if axis in ("height", "both") and kind not in TEXT_SIZED | {"icon", "divider", "textarea"}:
            base = current.get("height") if isinstance(current.get("height"), int) else \
                drawn_height(self.ir, node) or DEFAULT_HEIGHTS.get(kind, 40)
            out["height"] = max(24, min(900, round(base * scale)))
        if axis in ("both", "height") and (text_like or (axis == "both" and kind in ("button", "link"))):
            base_font = current.get("fontSize") or DEFAULT_FONTS.get(kind, 15)
            out["fontSize"] = max(8, round(base_font * scale))
        if axis == "width" and text_like and not out:
            out["fontSize"] = max(8, round((current.get("fontSize") or DEFAULT_FONTS.get(kind, 15)) * scale))
        if kind in ("button", "heading", "text", "link", "nav_item", "image") and abs(scale - 1) >= 0.25:
            idx = DEFAULT_SIZES.index(current.get("size", "md")) if current.get("size", "md") in DEFAULT_SIZES else 1
            out["size"] = DEFAULT_SIZES[max(0, min(2, idx + (1 if scale > 1 else -1)))]
        return out

    def move(self, op: dict) -> None:
        tid, ref = self.target_id(op)
        node, _, _ = irm.find(self.ir, tid) if tid else (None, None, None)
        if node is None:
            return self.record("move", None, "", False, f"target {ref!r} not found")
        position = op.get("position") or {}
        anchor = self.anchor_id(position)
        if anchor is None:
            if position.get("relation") in ("first", "last"):
                _, parent, _ = irm.find(self.ir, tid)
                anchor = parent["id"] if parent else None
            if anchor is None:
                return self.record("move", tid, "", False, "anchor not found")
        if anchor == tid or anchor in {n["id"] for n in _subtree(node)}:
            return self.record("move", tid, "", False, "cannot move a component relative to itself")
        _detach(self.ir, tid)
        moved = self.ir["meta"].setdefault("moved", [])
        if tid not in moved:
            moved.append(tid)  # the user placed it: sketch-order checks and repairs must leave it alone
        where = insert_relative(self.ir, node, anchor, position.get("relation"), self.taken)
        _set_relation(node, where)
        self.record("move", tid, f"moved {where}")

    def interaction(self, op: dict) -> None:
        tid, ref = self.target_id(op)
        node, _, _ = irm.find(self.ir, tid) if tid else (None, None, None)
        if node is None:
            return self.record("interaction", None, "", False, f"target {ref!r} not found")
        event = op.get("event") or {}
        on = event.get("on") or ("change" if node["type"] in irm.FIELD_TYPES else
                                 "submit" if node["type"] == "form" else "click")
        if on == "click" and node["type"] in irm.FIELD_TYPES:
            on = "change"  # "when the doctor is selected/typed" - fields react to changes, not clicks
        actions, problems = resolve_actions(self.ir, tid, event.get("actions") or [], self.taken)
        if not actions:
            return self.record("interaction", tid, "", False, "; ".join(problems) or "no actions")
        merge_event(node, on, actions)
        for action in actions:
            if action["type"] == "navigate" and node["type"] in irm.CLICKABLE_TYPES:
                node["props"]["href_page"] = action["page"]
        detail = f"on {on}: " + ", ".join(a["type"] for a in actions)
        self.record("interaction", tid, detail + (f" (skipped: {'; '.join(problems)})" if problems else ""))

    def navigation(self, op: dict) -> None:
        tid, ref = self.target_id(op, None)
        node, _, _ = irm.find(self.ir, tid) if tid else (None, None, None)
        if node is None:
            return self.record("navigation", None, "", False, f"target {ref!r} not found")
        name = navigation_page_name(op)
        if not name:
            return self.record("navigation", tid, "", False, "no page name")
        extra = [a for a in (op.get("event") or {}).get("actions") or [] if a.get("type") != "navigate"]
        if extra:  # e.g. validate first, then navigate: keep the other actions too
            self.interaction({**op, "event": {"on": "click", "actions": extra}})
        page, created = ensure_page(self.ir, name, self.taken)
        merge_event(node, "change" if node["type"] in irm.FIELD_TYPES else "click",
                    [{"type": "navigate", "page": page["id"]}])
        if node["type"] in irm.CLICKABLE_TYPES:
            node["props"]["href_page"] = page["id"]
        self.record("navigation", tid, f"click navigates to {page['id']}" + (" (page created)" if created else ""))

    def create(self, op: dict) -> None:
        from .fusion import fuse  # local import: fusion uses refine helpers

        theme = self.ir["meta"].get("theme")
        fresh = fuse(None, [op])
        if theme:
            fresh["meta"]["theme"] = theme
        self.ir = fresh
        self.taken = irm.all_ids(self.ir)
        self.record("create", "page_main", f"created {len(irm.nodes(fresh)) - len(fresh['pages'])} components")


def navigation_page_name(op: dict) -> str:
    """Destination of a navigation op: `page.name`, or the page of a navigate action in `event`."""
    name = ((op.get("page") or {}).get("name") or "").strip()
    if name:
        return name
    for action in (op.get("event") or {}).get("actions") or []:
        if action.get("type") == "navigate" and str(action.get("page") or "").strip():
            return str(action["page"]).strip()
    return ""


def _set_relation(node: dict, where: str) -> None:
    """Record the spatial relation the user asked for ("below btn_login") on the placed node."""
    relation, _, target = where.partition(" ")
    if relation in ("below", "above", "left_of", "right_of", "inside") and target and target != "of":
        node["relations"] = [{"type": relation, "target": target}]


def drawn_height(ir: dict, node: dict) -> int | None:
    """CSS height the geometry-aware compiler gives a node from its sketch box (None without geometry)."""
    frame = ir.get("meta", {}).get("frame")
    if not frame or not node.get("bbox") or node["id"] in ir.get("meta", {}).get("moved", []):
        return None
    return int(round(node["bbox"]["h"] * frame["sketch_height"] * frame["scale"]))


# RELATIVE SIZES: how a spoken size change becomes a factor (used by intent.py on the utterance, so the
# magnitude never depends on how the LLM happens to round "a bit bigger").
#   "full width", "edge to edge"      -> width "full"
#   "twice as wide", "double"         -> x2 ;  "half the size" -> x0.5 ;  "3 times" -> x3 ;  "20% bigger" -> x1.2
#   "a bit / slightly / a little"     -> x1.15 (x0.87 smaller)
#   plain "bigger / wider / taller"   -> x1.3  (smaller / narrower / shorter -> x0.75)
#   "much / a lot / way / significantly" -> x1.6 (x0.6)
# axis: wider/narrower/width -> "width"; taller/shorter/height -> "height"; everything else "both".
_UP = r"bigger|larger|wider|taller|increase|enlarge|grow|expand|broader|longer|greater|upsize|boost"
_DOWN = r"smaller|narrower|shorter|shrink|reduce|decrease|tinier|thinner|compact|lesser|downsize|slimmer"
FULL_WIDTH = re.compile(r"\b(full|whole|entire|complete)[ -]?width\b|\bedge[ -]to[ -]edge\b|\bfill(s|ing)? (the )?(whole |entire |full )?width\b"
                        r"|\bacross the (whole |entire |full )?(page|screen|width|form|card)\b|\bas wide as (the )?(page|screen|form|card|container)\b")


def parse_resize_phrase(text: str) -> dict | None:
    """{"scale": float|None, "axis": "width|height|both", "full_width": bool, "direction": "up|down"|None} for the
    size words in an utterance, or None when it has none. See RELATIVE SIZES above."""
    low = (text or "").lower().replace("-", " ")
    full = bool(FULL_WIDTH.search(low))
    up, down = re.search(rf"\b({_UP})\b", low), re.search(rf"\b({_DOWN})\b", low)
    direction = None
    if up and down:
        direction = "up" if up.start() < down.start() else "down"
    elif up or down:
        direction = "up" if up else "down"
    width_w = re.search(r"\b(wider|wide|narrower|narrow|broader|width|slimmer|thinner)\b", low)
    height_w = re.search(r"\b(taller|tall|shorter|short|height|longer)\b", low)
    axis = "width" if width_w and not height_w else "height" if height_w and not width_w else "both"
    scale = None
    if m := re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", low):
        pct = float(m.group(1)) / 100
        scale = 1 + pct if direction != "down" else max(0.1, 1 - pct)
    elif m := re.search(r"\b(\d+(?:\.\d+)?)\s*(?:x|times)\b", low):
        scale = float(m.group(1))
    elif re.search(r"\b(twice|double|two times|2x)\b", low):
        scale = 0.5 if direction == "down" else 2.0
    elif re.search(r"\b(triple|three times)\b", low):
        scale = 3.0
    elif re.search(r"\bhalf (the |its |of the )?(size|width|height)|\bhalf as\b|\bhalve\b", low):
        scale = 0.5
    elif direction:
        if re.search(r"\b(a bit|a little|slightly|a tad|somewhat|marginally|just a)\b", low):
            magnitude = 1.15
        elif re.search(r"\b(much|a lot|way|significantly|really|far|huge|hugely|massively|considerably)\b", low):
            magnitude = 1.6
        else:
            magnitude = 1.3
        scale = magnitude if direction == "up" else {1.15: 0.87, 1.3: 0.75, 1.6: 0.6}[magnitude]
    if not (full or direction or scale):
        return None
    return {"scale": scale, "axis": axis, "full_width": full, "direction": direction}


def drawn_width(ir: dict, node: dict) -> int | None:
    """CSS width the geometry-aware compiler gives a node from its sketch box (None without geometry)."""
    frame = ir.get("meta", {}).get("frame")
    if not frame or not node.get("bbox") or node["id"] in ir.get("meta", {}).get("moved", []):
        return None
    return int(round(min(node["bbox"]["w"], frame["content"]["w"]) * frame["sketch_width"] * frame["scale"]))


def guess_input_type(label: str) -> str:
    words = set(_tokens(label))
    for word, input_type in INPUT_TYPE_WORDS.items():
        if word in words:
            return input_type
    return "text"


def apply_ops(ir: dict, ops: list[dict]) -> dict:
    """Apply ops in order to a copy of `ir`. Returns {"ir", "changes"}."""
    applier = _Applier(ir)
    for op in ops or []:
        kind = (op.get("op") or "").lower()
        try:
            if kind == "add":
                applier.add(op)
            elif kind == "remove":
                applier.remove(op)
            elif kind in ("modify", "style"):
                applier.modify(op, kind)
            elif kind == "resize":
                applier.resize(op)
            elif kind == "move":
                applier.move(op)
            elif kind == "interaction":
                applier.interaction(op)
            elif kind == "navigation":
                applier.navigation(op)
            elif kind == "create":
                applier.create(op)
            else:
                applier.record(kind or "?", None, "", False, f"unknown op {kind!r}")
        except Exception as exc:  # report, never crash the whole command
            applier.record(kind, None, "", False, f"{type(exc).__name__}: {exc}")
    return {"ir": applier.ir, "changes": applier.changes}
