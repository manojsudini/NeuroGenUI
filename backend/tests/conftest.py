import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Isolated data dir for the whole test session (set before the app modules are imported).
os.environ.setdefault("NGUI_DATA_DIR", tempfile.mkdtemp(prefix="ngui-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES = Path(__file__).parent / "fixtures"


def _node(nid, ntype, label="", **extra):
    node = {"id": nid, "type": ntype, "label": label, "props": extra.pop("props", {}), "style": extra.pop("style", {}),
            "bbox": extra.pop("bbox", None), "relations": [], "events": extra.pop("events", []), "origin": "sketch"}
    if "children" in extra:
        node["children"] = extra.pop("children")
        node["layout"] = {"direction": "column", "gap": 12, "align": "stretch", "justify": "start"}
    return node


@pytest.fixture
def login_ir():
    """Hand-built login IR: heading, image, form(email, password, login button)."""
    form = _node("form_login", "form", children=[
        _node("inp_email", "input", "Email", props={"inputType": "email", "required": True}),
        _node("inp_password", "input", "Password", props={"inputType": "password", "required": True}),
        _node("btn_login", "button", "Login"),
    ])
    root = _node("page_main", "page", "Main", children=[
        _node("h_login", "heading", "Login", props={"level": 1}),
        _node("img_logo", "image", "", props={"photo": "banner", "alt": "logo"}),
        form,
    ])
    return {"schema": "neurogenui.ir/1",
            "meta": {"title": "Login", "category": "login", "theme": {"primary": "#e11d74", "radius": 10, "font": "Inter"}},
            "pages": [{"id": "page_main", "name": "Main", "route": "/", "root": root}], "next_id": 10}


@pytest.fixture
def fixture_png():
    return (FIXTURES / "login_sketch.png").read_bytes()


@pytest.fixture
def fixture_truth():
    return json.loads((FIXTURES / "login_sketch.json").read_text())
