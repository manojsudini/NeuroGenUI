import re

from app.pipeline import codegen
from app.pipeline import ir as irm


def test_files_and_determinism(login_ir):
    a = codegen.generate_code(login_ir)
    b = codegen.generate_code(login_ir)
    assert a == b
    for path in ("package.json", "index.html", "src/main.jsx", "src/App.jsx", "src/styles.css",
                 "src/runtime/actions.js", "src/runtime/store.js", "src/pages/MainPage.jsx",
                 "src/components/Button.jsx", "src/components/Field.jsx", "src/components/Heading.jsx"):
        assert path in a["files"], path
    assert '"react": "18.3.1"' in a["files"]["package.json"]
    assert "--ng-primary: #e11d74" in a["files"]["src/styles.css"]
    assert a["stats"]["components"] >= 6 and a["stats"]["loc"] > 100


def test_every_node_is_rendered_with_ngid(login_ir):
    page = codegen.generate_code(login_ir)["files"]["src/pages/MainPage.jsx"]
    for node, _, _ in irm.walk(login_ir):
        assert f'id="{node["id"]}"' in page


def test_preview_is_single_script(login_ir):
    preview = codegen.generate_code(login_ir)["preview"]
    assert not re.search(r"^\s*(import|export)\s", preview, re.M)
    assert preview.rstrip().endswith('ReactDOM.createRoot(document.getElementById("root")).render(<App />);')
    assert "const { createContext, useContext, useState } = React;" in preview


def test_events_compile_to_handlers(login_ir):
    login_ir["pages"][0]["root"]["children"][2]["children"][2]["events"] = [
        {"on": "click", "actions": [{"type": "validate_required", "targets": ["inp_email"], "message": "Fill it"}]}]
    page = codegen.generate_code(login_ir)["files"]["src/pages/MainPage.jsx"]
    assert "const BTN_LOGIN_CLICK = [" in page
    assert 'runActions("btn_login", BTN_LOGIN_CLICK, ui)' in page
    assert '<Message owner="btn_login" />' in page


def test_styles_compile(login_ir):
    btn = login_ir["pages"][0]["root"]["children"][2]["children"][2]
    btn["style"] = {"color": "#2563eb", "width": "full", "size": "lg"}
    page = codegen.generate_code(login_ir)["files"]["src/pages/MainPage.jsx"]
    assert 'size="lg"' in page
    assert 'background: "#2563eb"' in page and 'width: "100%"' in page
