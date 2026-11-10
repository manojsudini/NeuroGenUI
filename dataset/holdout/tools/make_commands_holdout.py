"""Write dataset/holdout/commands/commands.jsonl: 30 held-out voice commands (all 8 categories).

Same record format as dataset/commands/commands.jsonl. Every target/anchor is validated against the holdout
labels. Ids are cmd_h001..cmd_h030. None of the 7 brief examples are reused.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]     # dataset/holdout
C = []


def T(label, type=None):
    d = {"label": label}
    if type:
        d["type"] = type
    return d


def exists(type, label):
    return {"kind": "node_exists", "type": type, "label_contains": label}


def order(first, then, relation="below"):
    return {"kind": "order", "first": first, "then": then, "relation": relation}


def ALL(*c):
    return {"kind": "all", "checks": list(c)}


def relabel(type, old, new):
    return {"kind": "label_changed", "type": type, "old": old, "new": new}


def size(type, label, direction, dim="area"):
    return {"kind": "size_change", "type": type, "target_label": label, "direction": direction, "dim": dim}


def hue(type, label, h, key="color"):
    return {"kind": "style_eq", "type": type, "target_label": label, "key": key, "hue": h}


def ev(label, action, **kw):
    return {"kind": "event", "target_label": label, "action": action, **kw}


def nav(label, page):
    return {"kind": "navigates", "target_label": label, "page": page}


def cmd(cat, sid, text, op, target, params, check, base="generated"):
    C.append(dict(category=cat, sketch_id=sid, text=text, base=base,
                  expected={"op": op, "target_ref": target.get("label") if target else None,
                            "target_label": target.get("label") if target else None,
                            "target_type": target.get("type") if target else None, "params": params},
                  check=check))


# ---- add (4)
cmd("add", "hold_login_01", "Add a Resend code link below the Send code button.", "add", T("Send code", "button"),
    {"component": {"type": "link", "label": "resend code"}, "relation": "below", "anchor": "Send code"},
    ALL(exists("link", "resend code"), order(T("Send code", "button"), T("resend code", "link"))))
cmd("add", "hold_bank_01", "Put a note field under the amount field.", "add", T("Amount", "input"),
    {"component": {"type": "input", "label": "note"}, "relation": "below", "anchor": "Amount"},
    ALL(exists("input", "note"), order(T("Amount", "input"), T("note", "input"))))
cmd("add", "hold_book_01", "Can you add an email field right under the phone one?", "add", T("Phone", "input"),
    {"component": {"type": "input", "label": "email"}, "relation": "below", "anchor": "Phone"},
    ALL(exists("input", "email"), order(T("Phone", "input"), T("email", "input"))))
cmd("add", "hold_shop_02", "add a cancel order button below the track button", "add", T("Track", "button"),
    {"component": {"type": "button", "label": "cancel order"}, "relation": "below", "anchor": "Track"},
    ALL(exists("button", "cancel order"), order(T("Track", "button"), T("cancel order", "button"))))

# ---- remove (4)
cmd("remove", "hold_reg_02", "Remove the Send me study tips checkbox.", "remove", T("Send me study tips", "checkbox"), {},
    {"kind": "removed", "type": "checkbox", "label_contains": "study tips"})
cmd("remove", "hold_prof_01", "Get rid of the Jobs tab.", "remove", T("Jobs", "nav_item"), {},
    {"kind": "removed", "type": "link", "label_contains": "jobs"})
cmd("remove", "hold_contact_02", "Delete the world map image.", "remove", T("", "image"), {},
    {"kind": "removed", "type": "image"})
cmd("remove", "hold_bank_02", "We don't need the Sell all button anymore.", "remove", T("Sell all", "button"), {},
    {"kind": "removed", "type": "button", "label_contains": "sell all"})

# ---- modify (4)
cmd("modify", "hold_land_01", "Change the headline to Handmade pasta daily.", "modify", T("Fresh pasta daily", "heading"),
    {"label": "Handmade pasta daily"}, relabel("heading", "Fresh pasta daily", "Handmade pasta daily"))
cmd("modify", "hold_book_02", "Rename the Rent now button to Book this car.", "modify", T("Rent now", "button"),
    {"label": "Book this car"}, relabel("button", "Rent now", "Book this car"))
cmd("modify", "hold_dash_02", "the Start workout button should say Begin instead", "modify", T("Start workout", "button"),
    {"label": "Begin"}, relabel("button", "Start workout", "Begin"))
cmd("modify", "hold_contact_01", "Change the placeholder of the Tell us more box to Anything helps.", "modify",
    T("Tell us more", "textarea"), {"props": {"placeholder": "Anything helps"}},
    {"kind": "attr_contains", "type": "textarea", "target_label": "Tell us more", "attr": "placeholder",
     "value": "Anything helps"})

# ---- move (4)
cmd("move", "hold_reg_01", "Move the Add another link below the Send invites button.", "move", T("Add another", "link"),
    {"relation": "below", "anchor": "Send invites"}, order(T("Send invites", "button"), T("Add another", "link")))
cmd("move", "hold_login_01", "Put the Use email instead link above the Send code button.", "move",
    T("Use email instead", "link"), {"relation": "above", "anchor": "Send code"},
    order(T("Send code", "button"), T("Use email instead", "link"), "above"))
cmd("move", "hold_bank_01", "Can the Repeat monthly checkbox go above the account number field?", "move",
    T("Repeat monthly", "checkbox"), {"relation": "above", "anchor": "Account number"},
    order(T("Account number", "input"), T("Repeat monthly", "checkbox"), "above"))
cmd("move", "hold_prof_02", "Place the Post review button above the review box.", "move", T("Post review", "button"),
    {"relation": "above", "anchor": "Write a review"},
    order(T("Write a review", "textarea"), T("Post review", "button"), "above"))

# ---- resize (4)
cmd("resize", "hold_login_02", "Make the Continue with GitHub button bigger.", "resize",
    T("Continue with GitHub", "button"), {"direction": "increase"},
    size("button", "Continue with GitHub", "increase"))
cmd("resize", "hold_prof_02", "the doctor photo is too big, make it smaller", "resize", T("", "image"),
    {"direction": "decrease"}, size("image", "", "decrease"))
cmd("resize", "hold_contact_01", "Make the feedback box taller.", "resize", T("Tell us more", "textarea"),
    {"direction": "increase", "dim": "height"}, size("textarea", "Tell us more", "increase", "height"))
cmd("resize", "hold_land_02", "Increase the font size of the DevSummit heading.", "resize",
    T("DevSummit 2027", "heading"), {"direction": "increase"}, size("heading", "DevSummit 2027", "increase", "font"))

# ---- style (4)
cmd("style", "hold_land_01", "Make the Order online button orange.", "style", T("Order online", "button"),
    {"color": "orange"}, hue("button", "Order online", "orange"))
cmd("style", "hold_dash_01", "Color the Add vehicle button green.", "style", T("Add vehicle", "button"),
    {"color": "green"}, hue("button", "Add vehicle", "green"))
cmd("style", "hold_set_02", "I want the Delete account button in red.", "style", T("Delete account", "button"),
    {"color": "red"}, hue("button", "Delete account", "red"))
cmd("style", "hold_book_01", "Paint the Reserve button purple.", "style", T("Reserve", "button"),
    {"color": "purple"}, hue("button", "Reserve", "purple"))

# ---- interaction (3)
cmd("interaction", "hold_reg_02", "When Join now is clicked, complain if any field is empty.", "interaction",
    T("Join now", "button"), {"on": "click", "action": "validate_required"}, ev("Join now", "validate_required"))
cmd("interaction", "hold_shop_02", "Make the Need help link show the message An agent will call you.", "interaction",
    T("Need help with this order?", "link"), {"on": "click", "action": "show_message", "text": "agent"},
    ev("Need help", "show_message", text_contains="agent"))
cmd("interaction", "hold_contact_02", "Check that the email is valid when Request a call is clicked.", "interaction",
    T("Request a call", "button"), {"on": "click", "action": "validate_format", "format": "email"},
    ev("Request a call", "validate_format", format="email"))

# ---- navigation (3)
cmd("navigation", "hold_bank_02", "Clicking Support should open a Help center page.", "navigation",
    T("Support", "nav_item"), {"page": "Help center"}, nav("Support", "Help center"))
cmd("navigation", "hold_prof_01", "The About tab should take me to an About us page.", "navigation",
    T("About", "nav_item"), {"page": "About us"}, nav("About", "About us"))
cmd("navigation", "hold_book_02", "When Apply is clicked, go to a Results page.", "navigation",
    T("Apply", "button"), {"page": "Results"}, nav("Apply", "Results"))


def check_targets():
    problems = []
    for i, c in enumerate(C):
        lab = json.loads((ROOT / "labels" / f"{c['sketch_id']}.json").read_text())
        comps = lab["components"]
        e = c["expected"]
        if e["target_type"] and not any(x["type"] == e["target_type"] and e["target_label"].lower() in x["label"].lower()
                                        for x in comps):
            problems.append(f"{i}: {c['sketch_id']} has no {e['target_type']} '{e['target_label']}'")
        anchor = e["params"].get("anchor")
        if anchor and not any(anchor.lower() in x["label"].lower() for x in comps):
            problems.append(f"{i}: {c['sketch_id']} has no anchor '{anchor}'")
        ch = c["check"]
        for sub in (ch["checks"] if ch["kind"] == "all" else [ch]):
            for k in ("first", "then"):
                if k in sub and not any(sub[k].get("type") == x["type"] and sub[k]["label"].lower() in x["label"].lower()
                                        for x in comps if sub[k]["label"] or True) and sub[k]["label"]:
                    # 'then' of an add check refers to a component that does not exist yet
                    if not (c["expected"]["op"] == "add" and k == "then"):
                        problems.append(f"{i}: order {k} {sub[k]} missing in {c['sketch_id']}")
    return problems


def main():
    probs = check_targets()
    if probs:
        print("\n".join(probs)); sys.exit(1)
    cats = ["add", "remove", "modify", "move", "resize", "style", "interaction", "navigation"]
    assert set(c["category"] for c in C) == set(cats) and len(C) == 30, len(C)
    out = ROOT / "commands" / "commands.jsonl"
    out.parent.mkdir(exist_ok=True)
    meta_path = ROOT / "commands" / "audio_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    with out.open("w") as f:
        for i, c in enumerate(C, 1):
            cid = f"cmd_h{i:03d}"
            rec = {"id": cid, "category": c["category"], "sketch_id": c["sketch_id"], "text": c["text"],
                   "expected": c["expected"], "check": c["check"], "base": c["base"], "brief_example": False,
                   "split": "holdout", "audio": f"audio/{cid}.mp3"}
            if cid in meta and meta[cid]["text"] == c["text"]:
                rec["tts"] = meta[cid]
            f.write(json.dumps(rec) + "\n")
    print(f"wrote {len(C)} commands -> {out}")


if __name__ == "__main__":
    main()
