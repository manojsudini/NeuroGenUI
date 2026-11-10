"""Write dataset/commands/commands.jsonl: 80 voice refinement commands (10 per category).

Every command is tied to a sketch whose generated UI contains the target. `expected` gives the
operation, the target and the parameters we expect the interpreter to produce. `check` is a
machine-checkable post-condition evaluated on the rendered DOM (and on the IR for the pipeline)
by evaluation/checks.py. The script asserts that every referenced label exists in the sketch's
ground truth, so a command can never point at a component that is not there.

Commands marked brief=True are the 7 example commands from brief section 4.4, verbatim.
`base` is "generated" (apply to the UI generated from the sketch) or "empty" (the create command).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


C = []


def cmd(cat, sid, text, op, target, params, check, brief=False, base="generated"):
    C.append(dict(category=cat, sketch_id=sid, text=text, brief=brief, base=base,
                  expected={"op": op, "target_ref": target.get("label") if target else None,
                            "target_label": target.get("label") if target else None,
                            "target_type": target.get("type") if target else None, "params": params},
                  check=check))


# ------------------------------------------------------------------ add
cmd("add", "login_01", "Create a login page with email and password fields and a login button.",
    "create", None, {"components": [{"type": "input", "label": "email"}, {"type": "input", "label": "password"},
                                    {"type": "button", "label": "login"}]},
    ALL(exists("input", "email"), exists("input", "password"), exists("button", "login")),
    brief=True, base="empty")
cmd("add", "login_01", "Add a forgot password link below the login button.", "add", T("Login", "button"),
    {"component": {"type": "link", "label": "forgot"}, "relation": "below", "anchor": "Login"},
    ALL(exists("link", "forgot"), order(T("Login", "button"), T("forgot", "link"))), brief=True)
cmd("add", "reg_01", "Add a phone number field below email.", "add", T("Email", "input"),
    {"component": {"type": "input", "label": "phone"}, "relation": "below", "anchor": "Email"},
    ALL(exists("input", "phone"), order(T("Email", "input"), T("phone", "input"))), brief=True)
cmd("add", "contact_01", "Put a company name field under the name field.", "add", T("Name", "input"),
    {"component": {"type": "input", "label": "company"}, "relation": "below", "anchor": "Name"},
    ALL(exists("input", "company"), order(T("Name", "input"), T("company", "input"))))
cmd("add", "prof_01", "Add a Share profile button under the Message button.", "add", T("Message", "button"),
    {"component": {"type": "button", "label": "share"}, "relation": "below", "anchor": "Message"},
    ALL(exists("button", "share"), order(T("Message", "button"), T("share", "button"))))
cmd("add", "shop_03", "add a continue shopping link below the checkout button", "add", T("Checkout", "button"),
    {"component": {"type": "link", "label": "continue shopping"}, "relation": "below", "anchor": "Checkout"},
    ALL(exists("link", "continue shopping"), order(T("Checkout", "button"), T("continue shopping", "link"))))
cmd("add", "set_01", "Can you add a checkbox for SMS alerts right after email updates?", "add",
    T("Email updates", "checkbox"),
    {"component": {"type": "checkbox", "label": "sms"}, "relation": "below", "anchor": "Email updates"},
    ALL(exists("checkbox", "sms"), order(T("Email updates", "checkbox"), T("sms", "checkbox"))))
cmd("add", "land_03", "Add a small text saying Free for 30 days under the Download app button.", "add",
    T("Download app", "button"),
    {"component": {"type": "text", "label": "free for 30 days"}, "relation": "below", "anchor": "Download app"},
    ALL(exists("text", "free for 30 days"), order(T("Download app", "button"), T("free for 30 days", "text"))))
cmd("add", "dash_03", "add a Pay bills button next to the Request button", "add", T("Request", "button"),
    {"component": {"type": "button", "label": "pay bills"}, "relation": "right_of", "anchor": "Request"},
    exists("button", "pay bills"))
cmd("add", "book_02", "Add an email field below the date field so we can send a confirmation.", "add",
    T("Date", "input"),
    {"component": {"type": "input", "label": "email"}, "relation": "below", "anchor": "Date"},
    ALL(exists("input", "email"), order(T("Date", "input"), T("email", "input"))))

# ------------------------------------------------------------------ remove
cmd("remove", "login_01", "Remove the image.", "remove", T("", "image"), {},
    {"kind": "removed", "type": "image"}, brief=True)
cmd("remove", "login_03", "Remove the Continue with Google button.", "remove", T("Continue with Google", "button"), {},
    {"kind": "removed", "type": "button", "label_contains": "google"})
cmd("remove", "reg_01", "get rid of the confirm password field", "remove", T("Confirm password", "input"), {},
    {"kind": "removed", "type": "input", "label_contains": "confirm"})
cmd("remove", "dash_01", "Delete the Settings link from the navbar.", "remove", T("Settings", "nav_item"), {},
    {"kind": "removed", "type": "link", "label_contains": "settings"})
cmd("remove", "prof_02", "remove the phone field", "remove", T("Phone", "input"), {},
    {"kind": "removed", "type": "input", "label_contains": "phone"})
cmd("remove", "shop_02", "We don't need the Buy now button anymore.", "remove", T("Buy now", "button"), {},
    {"kind": "removed", "type": "button", "label_contains": "buy now"})
cmd("remove", "bank_02", "Remove the save recipient checkbox.", "remove", T("Save recipient", "checkbox"), {},
    {"kind": "removed", "type": "checkbox", "label_contains": "save recipient"})
cmd("remove", "contact_03", "Take out the Email me a copy checkbox.", "remove", T("Email me a copy", "checkbox"), {},
    {"kind": "removed", "type": "checkbox", "label_contains": "copy"})
cmd("remove", "set_04", "Remove the reset button.", "remove", T("Reset", "button"), {},
    {"kind": "removed", "type": "button", "label_contains": "reset"})
cmd("remove", "land_03", "remove the watch demo button", "remove", T("Watch demo", "button"), {},
    {"kind": "removed", "type": "button", "label_contains": "watch demo"})


# ------------------------------------------------------------------ modify
def relabel(type, old, new):
    return {"kind": "label_changed", "type": type, "old": old, "new": new}


cmd("modify", "login_01", "Change the login button text to Sign in.", "modify", T("Login", "button"),
    {"label": "Sign in"}, relabel("button", "Login", "Sign in"))
cmd("modify", "reg_01", "Rename the Register button to Create account.", "modify", T("Register", "button"),
    {"label": "Create account"}, relabel("button", "Register", "Create account"))
cmd("modify", "contact_01", "change the Send button so it says Send message", "modify", T("Send", "button"),
    {"label": "Send message"}, relabel("button", "Send", "Send message"))
cmd("modify", "dash_01", "Change the Dashboard heading to Overview.", "modify", T("Dashboard", "heading"),
    {"label": "Overview"}, relabel("heading", "Dashboard", "Overview"))
cmd("modify", "shop_01", "Rename the New arrivals heading to Best sellers.", "modify", T("New arrivals", "heading"),
    {"label": "Best sellers"}, relabel("heading", "New arrivals", "Best sellers"))
cmd("modify", "bank_04", "Make the Calculate button say Compute payment.", "modify", T("Calculate", "button"),
    {"label": "Compute payment"}, relabel("button", "Calculate", "Compute payment"))
cmd("modify", "prof_01", "Change the name Jane Doe to John Smith.", "modify", T("Jane Doe", "heading"),
    {"label": "John Smith"}, relabel("heading", "Jane Doe", "John Smith"))
cmd("modify", "land_02", "The headline should read Ship apps faster instead.", "modify",
    T("Build apps faster", "heading"), {"label": "Ship apps faster"},
    relabel("heading", "Build apps faster", "Ship apps faster"))
cmd("modify", "set_02", "Change the placeholder of the email field to you@example.com.", "modify",
    T("Email", "input"), {"props": {"placeholder": "you@example.com"}},
    {"kind": "attr_contains", "type": "input", "target_label": "Email", "attr": "placeholder",
     "value": "you@example.com"})
cmd("modify", "contact_04", "Change the Subscribe button label to Join.", "modify", T("Subscribe", "button"),
    {"label": "Join"}, relabel("button", "Subscribe", "Join"))

# ------------------------------------------------------------------ move
cmd("move", "login_02", "Move the button below the password field.", "move", T("Log In", "button"),
    {"relation": "below", "anchor": "Password"}, order(T("Password", "input"), T("Log In", "button")), brief=True)
cmd("move", "login_03", "Move the Forgot password link below the Sign in button.", "move",
    T("Forgot password?", "link"), {"relation": "below", "anchor": "Sign in"},
    order(T("Sign in", "button"), T("Forgot password", "link")))
cmd("move", "reg_03", "Put the subscribe to newsletter checkbox above the email field.", "move",
    T("Subscribe to newsletter", "checkbox"), {"relation": "above", "anchor": "Email"},
    order(T("Email", "input"), T("Subscribe to newsletter", "checkbox"), "above"))
cmd("move", "prof_01", "Move the About heading above the Follow button.", "move", T("About", "heading"),
    {"relation": "above", "anchor": "Follow"}, order(T("Follow", "button"), T("About", "heading"), "above"))
cmd("move", "shop_02", "Move the size dropdown below the quantity field.", "move", T("Size", "select"),
    {"relation": "below", "anchor": "Quantity"}, order(T("Quantity", "input"), T("Size", "select")))
cmd("move", "bank_02", "Move the amount field to the top of the form, above From account.", "move",
    T("Amount", "input"), {"relation": "above", "anchor": "From account"},
    order(T("From account", "select"), T("Amount", "input"), "above"))
cmd("move", "contact_02", "Move the subject field above the name field.", "move", T("Subject", "input"),
    {"relation": "above", "anchor": "Name"}, order(T("Name", "input"), T("Subject", "input"), "above"))
cmd("move", "set_01", "move the privacy policy link under the log out button", "move", T("Privacy policy", "link"),
    {"relation": "below", "anchor": "Log out"}, order(T("Log out", "button"), T("Privacy policy", "link")))
cmd("move", "land_01", "Move the Learn more button to the left of Try free.", "move", T("Learn more", "button"),
    {"relation": "left_of", "anchor": "Try free"}, order(T("Try free", "button"), T("Learn more", "button"), "left_of"))
cmd("move", "book_02", "Can the date field go below the time slots?", "move", T("Date", "input"),
    {"relation": "below", "anchor": "Time slot"}, order(T("9:00", "radio"), T("Date", "input")))


# ------------------------------------------------------------------ resize
def size(type, label, direction, dim="area"):
    return {"kind": "size_change", "type": type, "target_label": label, "direction": direction, "dim": dim}


cmd("resize", "login_01", "Make the login button bigger.", "resize", T("Login", "button"),
    {"direction": "increase"}, size("button", "Login", "increase"))
cmd("resize", "login_03", "the sign in button should be a bit bigger", "resize", T("Sign in", "button"),
    {"direction": "increase"}, size("button", "Sign in", "increase"))
cmd("resize", "reg_02", "Make the Create account button full width.", "resize", T("Create account", "button"),
    {"direction": "increase", "width": "full"}, size("button", "Create account", "increase", "width"))
cmd("resize", "dash_02", "Make the search box wider.", "resize", T("Search", "input"),
    {"direction": "increase", "dim": "width"}, size("input", "Search", "increase", "width"))
cmd("resize", "prof_01", "make the avatar smaller", "resize", T("", "image"),
    {"direction": "decrease"}, size("image", "", "decrease"))
cmd("resize", "shop_02", "Make the product image smaller.", "resize", T("", "image"),
    {"direction": "decrease"}, size("image", "", "decrease"))
cmd("resize", "land_02", "Make the Join waitlist button larger.", "resize", T("Join waitlist", "button"),
    {"direction": "increase"}, size("button", "Join waitlist", "increase"))
cmd("resize", "contact_01", "Make the message box taller.", "resize", T("Message", "textarea"),
    {"direction": "increase", "dim": "height"}, size("textarea", "Message", "increase", "height"))
cmd("resize", "bank_01", "Make the MyBank title bigger.", "resize", T("MyBank", "heading"),
    {"direction": "increase"}, size("heading", "MyBank", "increase", "font"))
cmd("resize", "set_03", "Make the update password button smaller.", "resize", T("Update password", "button"),
    {"direction": "decrease"}, size("button", "Update password", "decrease"))


# ------------------------------------------------------------------ style
def hue(type, label, h, key="color"):
    return {"kind": "style_eq", "type": type, "target_label": label, "key": key, "hue": h}


cmd("style", "login_01", "Make the login button blue.", "style", T("Login", "button"), {"color": "blue"},
    hue("button", "Login", "blue"), brief=True)
cmd("style", "reg_01", "Make the Register button green.", "style", T("Register", "button"), {"color": "green"},
    hue("button", "Register", "green"))
cmd("style", "dash_03", "Color the Send button purple.", "style", T("Send", "button"), {"color": "purple"},
    hue("button", "Send", "purple"))
cmd("style", "shop_01", "make the add to cart button orange", "style", T("Add to cart", "button"),
    {"color": "orange"}, hue("button", "Add to cart", "orange"))
cmd("style", "bank_02", "The Send button should be red.", "style", T("Send", "button"), {"color": "red"},
    hue("button", "Send", "red"))
cmd("style", "contact_01", "Make the Contact us heading dark blue.", "style", T("Contact us", "heading"),
    {"textColor": "dark blue"}, hue("heading", "Contact us", "blue", "textColor"))
cmd("style", "prof_01", "Make the Follow button pink.", "style", T("Follow", "button"), {"color": "pink"},
    hue("button", "Follow", "pink"))
cmd("style", "land_01", "Change the Get started button color to black.", "style", T("Get started", "button"),
    {"color": "black"}, hue("button", "Get started", "black"))
cmd("style", "set_04", "make the save button teal", "style", T("Save", "button"), {"color": "teal"},
    hue("button", "Save", "teal"))
cmd("style", "book_01", "Give the Search button a yellow background.", "style", T("Search", "button"),
    {"color": "yellow"}, hue("button", "Search", "yellow"))


# ------------------------------------------------------------------ interaction
def ev(label, action, **kw):
    return {"kind": "event", "target_label": label, "action": action, **kw}


cmd("interaction", "login_01", "When the login button is clicked, show an error if the fields are empty.",
    "interaction", T("Login", "button"), {"on": "click", "action": "validate_required"},
    ev("Login", "validate_required"), brief=True)
cmd("interaction", "reg_04", "When Next is clicked, check that all the fields are filled in.", "interaction",
    T("Next", "button"), {"on": "click", "action": "validate_required"}, ev("Next", "validate_required"))
cmd("interaction", "contact_04", "Show a message saying Thanks for subscribing when Subscribe is clicked.",
    "interaction", T("Subscribe", "button"), {"on": "click", "action": "show_message", "text": "thanks"},
    ev("Subscribe", "show_message", text_contains="thanks"))
cmd("interaction", "login_04", "When Need help? is clicked, show the message Contact your administrator.",
    "interaction", T("Need help?", "link"), {"on": "click", "action": "show_message", "text": "administrator"},
    ev("Need help?", "show_message", text_contains="administrator"))
cmd("interaction", "reg_02", "Check that the email is valid when Create account is clicked.", "interaction",
    T("Create account", "button"), {"on": "click", "action": "validate_format", "format": "email"},
    ev("Create account", "validate_format", field_label="Email", format="email"))
cmd("interaction", "bank_02", "Clicking Cancel should show the message Transfer cancelled.", "interaction",
    T("Cancel", "button"), {"on": "click", "action": "show_message", "text": "cancelled"},
    ev("Cancel", "show_message", text_contains="cancel"))
cmd("interaction", "book_03", "When Load more is clicked, show the message No more flights.", "interaction",
    T("Load more", "button"), {"on": "click", "action": "show_message", "text": "no more flights"},
    ev("Load more", "show_message", text_contains="no more flights"))
cmd("interaction", "land_04", "When Choose Basic is clicked, show Basic plan selected.", "interaction",
    T("Choose Basic", "button"), {"on": "click", "action": "show_message", "text": "basic plan"},
    ev("Choose Basic", "show_message", text_contains="basic plan"))
cmd("interaction", "contact_02", "Make the Submit button check that the email is valid.", "interaction",
    T("Submit", "button"), {"on": "click", "action": "validate_format", "format": "email"},
    ev("Submit", "validate_format", field_label="Email", format="email"))
cmd("interaction", "dash_03", "When Request is tapped, show Request sent.", "interaction", T("Request", "button"),
    {"on": "click", "action": "show_message", "text": "request sent"},
    ev("Request", "show_message", text_contains="request sent"))


# ------------------------------------------------------------------ navigation
def nav(label, page):
    return {"kind": "navigates", "target_label": label, "page": page}


cmd("navigation", "reg_03", "When Cancel is clicked, go back to the Home page.", "navigation",
    T("Cancel", "button"), {"page": "Home"}, nav("Cancel", "Home"))
cmd("navigation", "login_03", "Clicking Forgot password? should take me to a Reset password page.", "navigation",
    T("Forgot password?", "link"), {"page": "Reset password"}, nav("Forgot password", "Reset password"))
cmd("navigation", "dash_01", "Make the Settings link open a Settings page.", "navigation",
    T("Settings", "nav_item"), {"page": "Settings"}, nav("Settings", "Settings"))
cmd("navigation", "dash_02", "Clicking Analytics should open the Analytics page.", "navigation",
    T("Analytics", "nav_item"), {"page": "Analytics"}, nav("Analytics", "Analytics"))
cmd("navigation", "prof_02", "When Cancel is clicked, go to a Profile page.", "navigation",
    T("Cancel", "button"), {"page": "Profile"}, nav("Cancel", "Profile"))
cmd("navigation", "shop_04", "After Place order, go to an Order confirmed page.", "navigation",
    T("Place order", "button"), {"page": "Order confirmed"}, nav("Place order", "Order confirmed"))
cmd("navigation", "bank_01", "Pay bills should open a Bills page.", "navigation",
    T("Pay bills", "button"), {"page": "Bills"}, nav("Pay bills", "Bills"))
cmd("navigation", "book_01", "Make the Sign in button go to a Login page.", "navigation",
    T("Sign in", "button"), {"page": "Login"}, nav("Sign in", "Login"))
cmd("navigation", "land_02", "Clicking Docs should open the Documentation page.", "navigation",
    T("Docs", "nav_item"), {"page": "Documentation"}, nav("Docs", "Documentation"))
cmd("navigation", "contact_02", "Clicking Services in the navbar should open a Services page.", "navigation",
    T("Services", "nav_item"), {"page": "Services"}, nav("Services", "Services"))


def check_targets():
    """Every label a command refers to must exist (as that type) in the sketch ground truth."""
    problems = []
    for i, c in enumerate(C):
        if c["base"] == "empty":
            continue
        lab = json.loads((ROOT / "labels" / f"{c['sketch_id']}.json").read_text())
        comps = lab["components"]
        e = c["expected"]
        if e["target_type"]:
            ok = any(x["type"] == e["target_type"] and e["target_label"].lower() in x["label"].lower()
                     for x in comps)
            if not ok:
                problems.append(f"{i}: {c['sketch_id']} has no {e['target_type']} '{e['target_label']}'")
        anchor = e["params"].get("anchor")
        if anchor and not any(anchor.lower() in x["label"].lower() for x in comps):
            problems.append(f"{i}: {c['sketch_id']} has no anchor '{anchor}'")
    return problems


def main():
    probs = check_targets()
    if probs:
        print("\n".join(probs))
        sys.exit(1)
    cats = ["add", "remove", "modify", "move", "resize", "style", "interaction", "navigation"]
    for cat in cats:
        n = sum(1 for c in C if c["category"] == cat)
        assert n == 10, (cat, n)
    assert sum(c["brief"] for c in C) == 7
    out = ROOT / "commands" / "commands.jsonl"
    out.parent.mkdir(exist_ok=True)
    meta_path = ROOT / "commands" / "audio_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    with out.open("w") as f:
        for i, c in enumerate(C, 1):
            cid = f"cmd_{i:03d}"
            rec = {"id": cid, "category": c["category"], "sketch_id": c["sketch_id"], "text": c["text"],
                   "expected": c["expected"], "check": c["check"], "base": c["base"], "brief_example": c["brief"],
                   "audio": f"audio/{cid}.mp3"}
            if cid in meta:
                rec["tts"] = meta[cid]
            f.write(json.dumps(rec) + "\n")
    print(f"wrote {len(C)} commands -> {out}")


if __name__ == "__main__":
    main()
