"""Voice/text command understanding: transcript (+ compact IR outline) -> list of Ops (contract section 2).

The LLM only interprets intent into structured Ops (JSON-schema, temperature 0). It never writes code.
Target ids it leaves empty or invalid are resolved deterministically later by refine.resolve_target.
"""
from __future__ import annotations

import json

from .. import config
from . import ir as irm
from . import llm
from . import refine

OP_KINDS = ["add", "remove", "modify", "move", "resize", "style", "interaction", "navigation", "create"]
RELATIONS = ["below", "above", "left_of", "right_of", "inside", "first", "last"]
ACTION_TYPES = ["validate_required", "validate_format", "show_message", "navigate", "toggle_visibility", "set_text"]

_s = {"type": "string"}
_n = {"type": "number"}
_i = {"type": "integer"}
_b = {"type": "boolean"}
_ref = llm.obj({"ref": _s, "id": llm.nullable(_s)})

PROPS = llm.obj({
    "level": llm.nullable(_i), "inputType": llm.nullable({"type": "string", "enum": sorted(irm.INPUT_TYPES)}),
    "placeholder": llm.nullable(_s), "required": llm.nullable(_b), "name": llm.nullable(_s),
    "rows": llm.nullable(_i), "checked": llm.nullable(_b), "group": llm.nullable(_s),
    "options": llm.nullable({"type": "array", "items": _s}), "alt": llm.nullable(_s),
    "photo": llm.nullable({"type": "string", "enum": [*irm.PHOTO_KEYS, ""]}),
    "items": llm.nullable({"type": "array", "items": _s}),
})
STYLE = llm.obj({
    "variant": llm.nullable({"type": "string", "enum": ["primary", "secondary", "outline", "ghost", "danger"]}),
    "color": llm.nullable(_s), "textColor": llm.nullable(_s), "bg": llm.nullable(_s),
    "size": llm.nullable({"type": "string", "enum": ["sm", "md", "lg"]}),
    "width": llm.nullable(_s), "height": llm.nullable(_i),
    "align": llm.nullable({"type": "string", "enum": ["left", "center", "right"]}),
    "fontSize": llm.nullable(_i), "fontWeight": llm.nullable(_i), "radius": llm.nullable(_i),
    "hidden": llm.nullable(_b),
})
ACTION = llm.obj({
    "type": {"type": "string", "enum": ACTION_TYPES},
    "targets": llm.nullable({"type": "array", "items": _s}),
    "target": llm.nullable(_s),
    "format": llm.nullable({"type": "string", "enum": ["email", "phone", "number"]}),
    "message": llm.nullable(_s), "text": llm.nullable(_s),
    "tone": llm.nullable({"type": "string", "enum": ["success", "error", "info"]}),
    "page": llm.nullable(_s),
})
EVENT = llm.obj({"on": {"type": "string", "enum": ["click", "submit", "change"]},
                 "actions": {"type": "array", "items": ACTION}})
CHILD = llm.obj({"type": {"type": "string", "enum": [t for t in irm.TYPES if t != "page"]}, "label": _s,
                 "props": llm.nullable(PROPS), "style": llm.nullable(STYLE)})
COMPONENT = llm.obj({
    "type": {"type": "string", "enum": [t for t in irm.TYPES if t != "page"]},
    "label": _s,
    "props": llm.nullable(PROPS),
    "style": llm.nullable(STYLE),
    "events": llm.nullable({"type": "array", "items": EVENT}),
    "children": llm.nullable({"type": "array", "items": CHILD}),
})
OP = llm.obj({
    "op": {"type": "string", "enum": OP_KINDS},
    "target": llm.nullable(_ref),
    "component": llm.nullable(COMPONENT),
    "components": llm.nullable({"type": "array", "items": COMPONENT}),
    "position": llm.nullable(llm.obj({"relation": {"type": "string", "enum": RELATIONS}, "anchor": llm.nullable(_ref)})),
    "changes": llm.nullable(llm.obj({"label": llm.nullable(_s), "props": llm.nullable(PROPS), "style": llm.nullable(STYLE)})),
    "scale": llm.nullable(_n),
    "axis": llm.nullable({"type": "string", "enum": ["width", "height", "both"]}),
    "event": llm.nullable(EVENT),
    "page": llm.nullable(llm.obj({"name": _s})),
    "meta": llm.nullable(llm.obj({"title": _s, "category": _s})),
    "confidence": _n,
})
SCHEMA = llm.obj({"ops": {"type": "array", "items": OP}})

SYSTEM = """You convert spoken UI instructions into structured edit operations ("ops") for a UI intent representation.
You never write code. Output only ops that the instruction asks for. One utterance may contain several ops.

Op kinds:
- create: describe a whole new screen. Give meta {title, category} (category one of: login, registration, dashboard,
  profile, ecommerce, banking, booking, contact, settings, landing, other) and `components` in reading order
  (top to bottom). Infer sensible components the user implies (a login page has email + password inputs and a
  login button). Use props.inputType for inputs (email, password, tel, number, date, search, text) and
  props.required when fields are mandatory. Put behaviour described for a component in its `events`.
  Navbars list their nav_item children in `children`.
  List EVERY component the user names (each field, button, link, brand name, card title, section heading, price,
  option) as its own entry with its exact label; nest components that sit inside a navbar, header, card, form or
  panel in `children`. Never summarise several named components into one container ("three stat cards").
  Brand / logo names and card, section and page titles are headings; items of a navbar or sidebar are nav_items;
  a field named by a noun (Email, Zip code) is an input; a dropdown is a select.
  Labels are the exact text shown on screen ("Add to cart", "120 posts", "$29", "Search products"), never a
  description ("Add to cart button for Sneakers", "Posts count", "Search box", "ShopEasy logo"). If the user
  only describes content, write realistic visible text. Images and icons get an empty label (describe them in
  props.alt). A radio's label is its option text ("Male"); the question ("Gender") goes in props.group.
- add: one new component (`component`), placed with `position` {relation, anchor{ref,id}}.
- remove: delete `target`.
- modify: change `target` text (changes.label), props (changes.props) or style.
- style: visual change of `target`: changes.style.color (main fill of buttons / text colour of text), textColor,
  bg, variant, fontWeight, radius, align. Colours may be plain words ("blue"); they are converted later.
  "Make the theme/app/page purple" = style on target {ref:"page"} with color.
- move: put `target` at `position` relative to an anchor.
- resize: EVERY change of size, width or height is a `resize` op (never `style`, never `size`/`rows` props).
  Relative wording becomes `scale`, a multiplier of the current size, plus `axis` (width for wider/narrower,
  height for taller/shorter, both otherwise): bigger/larger/increase 1.3, a bit/slightly bigger 1.15,
  much/a lot bigger 1.6, twice/double 2, half the size 0.5, smaller/reduce 0.75, a bit smaller 0.87,
  much smaller 0.6, N% bigger 1+N/100. "full width", "edge to edge", "across the page" = changes.style.width
  "full" (no scale). Only an explicit number of pixels goes into changes.style.width / height / fontSize.
- interaction: behaviour of `target` on an event: event {on: click|submit|change, actions:[...]}.
  Actions: validate_required {targets:[field refs] or null for "all fields of the form", message},
  validate_format {target, format: email|phone|number, message}, show_message {text, tone},
  navigate {page: page name}, toggle_visibility {target}, set_text {target, text}.
  Validation actions come first. "show an error when X is clicked with empty fields" =
  validate_required with targets null and a clear message.
- navigation: clicking `target` opens page `page.name` (the page is created if it does not exist).
  Always put the destination in `page.name` (not only inside an event).

Disambiguation of targets (the outline lists every component with its id, parent and, where set, [size hints]):
- Several components of the same type: decide by the words (label text, "second", "last", "top", "search",
  "login"), by what the instruction is about, and by the outline order (document order = reading order). A
  button that names a label ("the Subscribe button") is that label's button; a bare "the button" in a UI with
  one primary action is that primary action.
- Plural references name a group ("the time slots", "the options"): set target.ref as written; the app uses the
  whole group. "above / below X" anchors on X itself, never on the thing being moved.
- A text node with the same label as an input is only the caption of that field. "The email field / box /
  input" is the input, even if a text "Email" is listed first; if no input exists at all, still give the
  text node's id and the app turns it into a field.
- Never invent ids; if you are not sure which component is meant, leave id null and give the clearest ref.

Targets: `target.ref` is the user's words for the component ("login button", "email field", "second button",
"the image"). When the current UI outline is given, also set `target.id` to the exact id from the outline if
you are sure; otherwise null. Same for position.anchor.
When the user says field, input, box or textbox, the target is the input/textarea/select itself, never
the text label written next to it (e.g. "the email field" -> the input labelled Email, not a text "Email").
Change only what the user asked for: set only the style keys / props that the instruction mentions
(for "make the button blue" set only color; do not add bg, textColor or variant).
Fill every field of the schema; use null for fields that do not apply. confidence is 0..1.

Examples (null fields omitted here for brevity):

"Create a login page with email and password and a login button"
{"ops":[{"op":"create","meta":{"title":"Login","category":"login"},"components":[
 {"type":"heading","label":"Login","props":{"level":1}},
 {"type":"input","label":"Email","props":{"inputType":"email","placeholder":"you@example.com","required":true}},
 {"type":"input","label":"Password","props":{"inputType":"password","required":true}},
 {"type":"button","label":"Login"}],"confidence":0.95}]}

"Add a forgot password link below the login button"
{"ops":[{"op":"add","component":{"type":"link","label":"Forgot password?"},
 "position":{"relation":"below","anchor":{"ref":"login button","id":"btn_login"}},"confidence":0.95}]}

"Make the login button blue"
{"ops":[{"op":"style","target":{"ref":"login button","id":"btn_login"},"changes":{"style":{"color":"blue"}},"confidence":0.97}]}

"Move the button below password"
{"ops":[{"op":"move","target":{"ref":"button","id":"btn_login"},
 "position":{"relation":"below","anchor":{"ref":"password field","id":"inp_password"}},"confidence":0.9}]}

"Add a phone number field below email"
{"ops":[{"op":"add","component":{"type":"input","label":"Phone number","props":{"inputType":"tel"}},
 "position":{"relation":"below","anchor":{"ref":"email field","id":"inp_email"}},"confidence":0.95}]}

"Remove the image"
{"ops":[{"op":"remove","target":{"ref":"image","id":"img_logo"},"confidence":0.95}]}

"Show an error when login is clicked with empty fields"
{"ops":[{"op":"interaction","target":{"ref":"login button","id":"btn_login"},"event":{"on":"click","actions":[
 {"type":"validate_required","targets":null,"message":"Please fill in all fields"}]},"confidence":0.93}]}

"Make the heading bigger and center it"
{"ops":[{"op":"resize","target":{"ref":"heading","id":"h_login"},"scale":1.3,"axis":"both","confidence":0.9},
 {"op":"style","target":{"ref":"heading","id":"h_login"},"changes":{"style":{"align":"center"}},"confidence":0.9}]}

"When I click sign up go to a welcome page"
{"ops":[{"op":"navigation","target":{"ref":"sign up button","id":null},"page":{"name":"Welcome"},"confidence":0.9}]}

"Change the submit button text to Send message"
{"ops":[{"op":"modify","target":{"ref":"submit button","id":"btn_submit"},"changes":{"label":"Send message"},"confidence":0.95}]}

"After a successful login show a success message and go to the dashboard"
{"ops":[{"op":"interaction","target":{"ref":"login button","id":"btn_login"},"event":{"on":"click","actions":[
 {"type":"show_message","text":"Login successful","tone":"success"},{"type":"navigate","page":"Dashboard"}]},"confidence":0.9}]}

"Make the email field required and check it is a valid email when I press register"
{"ops":[{"op":"modify","target":{"ref":"email field","id":"inp_email"},"changes":{"props":{"required":true}},"confidence":0.9},
 {"op":"interaction","target":{"ref":"register button","id":"btn_register"},"event":{"on":"click","actions":[
 {"type":"validate_required","targets":["email field"],"message":"Email is required"},
 {"type":"validate_format","target":"email field","format":"email","message":"Enter a valid email address"}]},"confidence":0.9}]}

"Make the newsletter input wider"
{"ops":[{"op":"resize","target":{"ref":"newsletter input","id":"inp_newsletter"},"scale":1.3,"axis":"width","confidence":0.92}]}

"Make the Sign up button span the whole width"
{"ops":[{"op":"resize","target":{"ref":"Sign up button","id":"btn_sign_up"},"changes":{"style":{"width":"full"}},"confidence":0.95}]}

"The comment box should be a lot taller"
{"ops":[{"op":"resize","target":{"ref":"comment box","id":"ta_comment"},"scale":1.6,"axis":"height","confidence":0.92}]}

"Make the logo twice as big and the subtitle a bit smaller"
{"ops":[{"op":"resize","target":{"ref":"logo","id":"img_logo"},"scale":2,"axis":"both","confidence":0.9},
 {"op":"resize","target":{"ref":"subtitle","id":"txt_subtitle"},"scale":0.87,"axis":"both","confidence":0.9}]}

"Set the placeholder of the phone field to 555 0100"
{"ops":[{"op":"modify","target":{"ref":"phone field","id":"inp_phone"},"changes":{"props":{"placeholder":"555 0100"}},"confidence":0.93}]}

"Put a remember me checkbox above the login button and make the button full width"
{"ops":[{"op":"add","component":{"type":"checkbox","label":"Remember me"},
 "position":{"relation":"above","anchor":{"ref":"login button","id":"btn_login"}},"confidence":0.92},
 {"op":"resize","target":{"ref":"login button","id":"btn_login"},"changes":{"style":{"width":"full"}},"confidence":0.9}]}
"""


RESIZE_STYLE_KEYS = {"size", "width", "height", "fontSize"}


def ir_summary(ir: dict) -> str:
    """The UI as the LLM sees it: one line per node (id | type | label | parent) with size hints, then notes that
    resolve the usual ambiguities: nodes of the same type in reading order and labels shared by several nodes."""
    lines, by_type, by_label = [], {}, {}
    for node, parent, page in irm.walk(ir):
        if node["type"] == "page":
            lines.append(f"{node['id']} | page | {page['name']} | -")
            continue
        extra = ""
        if node["type"] == "input" and node["props"].get("inputType"):
            extra = f" ({node['props']['inputType']})"
        st = node.get("style", {})
        hints = [f"{k}={st[k]}" for k in ("width", "height", "fontSize", "size") if st.get(k) not in (None, "md")]
        if node["type"] == "textarea" and node["props"].get("rows"):
            hints.append(f"rows={node['props']['rows']}")
        if node.get("style", {}).get("hidden"):
            hints.append("hidden")
        hint = f" [{', '.join(hints)}]" if hints else ""
        lines.append(f"{node['id']} | {node['type']}{extra} | {node['label']!r}{hint} | {parent['id'] if parent else '-'}")
        by_type.setdefault(node["type"], []).append(node["id"])
        label = (node.get("label") or "").strip().lower()
        if label:
            by_label.setdefault(label, []).append(f"{node['id']} ({node['type']})")
    notes = []
    for kind in ("button", "input", "textarea", "select", "image", "heading", "link", "nav_item", "checkbox", "radio"):
        if len(by_type.get(kind, [])) > 1:
            notes.append(f"{kind}s in reading order: " + ", ".join(by_type[kind]))
    for label, ids in by_label.items():
        if len(ids) > 1:
            notes.append(f"label {label!r} is shared by " + ", ".join(ids) +
                         " (a text with a field's label is only its caption)")
    return "\n".join(lines) + ("\nNotes:\n- " + "\n- ".join(notes) if notes else "")


def _normalise_resize(ops: list[dict], text: str) -> None:
    """Make every size change a `resize` op with a deterministic factor (see refine.RELATIVE SIZES).
    The LLM picks the target; the magnitude comes from the words of the utterance when it has any."""
    hint = refine.parse_resize_phrase(text)

    def size_only(op: dict) -> bool:
        keys = set(((op.get("changes") or {}).get("style")) or {})
        return op.get("op") == "style" and bool(keys & RESIZE_STYLE_KEYS) and not keys - RESIZE_STYLE_KEYS

    sized = [op for op in ops if op.get("op") == "resize" or size_only(op)]
    for op in sized:
        op["op"] = "resize"
        changes = dict(op.get("changes") or {})
        style = {k: v for k, v in (changes.get("style") or {}).items() if v is not None}
        props = {k: v for k, v in (changes.get("props") or {}).items() if v is not None}
        if len(sized) == 1 and hint is not None:
            if hint["full_width"]:
                op.pop("scale", None)
                op.pop("axis", None)
                style, props = {"width": "full"}, {}
            elif hint["scale"]:
                op["scale"], op["axis"] = hint["scale"], hint["axis"]
                style, props = {}, {}  # the stated factor supersedes size words, pixels or rows guessed by the model
        if op.get("axis") is None:
            op.pop("axis", None)
        for key, value in (("style", style), ("props", props)):
            if value:
                changes[key] = value
            else:
                changes.pop(key, None)
        changes = {k: v for k, v in changes.items() if v}
        if changes:
            op["changes"] = changes
        else:
            op.pop("changes", None)


def _canonical_navigation(op: dict) -> dict:
    """An interaction whose only action is `navigate` is a navigation op (one canonical form for "go to X")."""
    actions = (op.get("event") or {}).get("actions") or []
    if op.get("op") == "interaction" and actions and all(a.get("type") == "navigate" for a in actions) \
            and actions[0].get("page") and (op.get("event") or {}).get("on", "click") == "click":
        return {**{k: v for k, v in op.items() if k != "event"}, "op": "navigation",
                "page": {"name": actions[0]["page"]}}
    return op


def _clean_op(op: dict, ir: dict | None) -> dict:
    op = _canonical_navigation(llm.strip_nulls(op))
    for key in ("target",):
        ref = op.get(key)
        if isinstance(ref, dict) and ref.get("id") and ir is not None and irm.find(ir, ref["id"])[0] is None:
            ref.pop("id")  # hallucinated id: let the deterministic resolver handle it
    anchor = (op.get("position") or {}).get("anchor")
    if isinstance(anchor, dict) and anchor.get("id") and ir is not None and irm.find(ir, anchor["id"])[0] is None:
        anchor.pop("id")
    changes = op.get("changes") or {}
    if changes.get("style"):
        changes["style"] = refine.normalize_style(changes["style"])
        if changes["style"].get("width") not in (None, "auto", "full"):
            changes["style"]["width"] = irm.clean_style({"width": changes["style"]["width"]}).get("width")
    for comp in [op.get("component"), *(op.get("components") or [])]:
        if comp and comp.get("style"):
            comp["style"] = refine.normalize_style(comp["style"])
    return op


def parse_commands(text: str, ir: dict | None = None) -> dict:
    """Transcript -> {"ops":[Op], "model", "latency_ms", "raw"}."""
    text = (text or "").strip()
    if not text:
        return {"ops": [], "model": None, "latency_ms": 0, "raw": ""}
    if ir is not None:
        context = "Current UI outline (id | type | label [size hints] | parent):\n" + ir_summary(ir)
        pages = ", ".join(f"{p['id']} ({p['name']})" for p in ir.get("pages", []))
        context += f"\nPages: {pages}\nThe instruction edits this existing UI."
    else:
        context = "There is no UI yet. The instruction describes a new screen: answer with a create op (plus any other ops it implies)."
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"{context}\n\nInstruction: {json.dumps(text)}"},
    ]
    result, info = llm.chat_json(messages, SCHEMA, "ui_ops", config.get("OPENAI_TEXT_MODEL"))
    ops = [_clean_op(op, ir) for op in result.get("ops", [])]
    _normalise_resize(ops, text)
    return {"ops": ops, "model": info["model"], "latency_ms": info["latency_ms"], "raw": info["raw"]}
