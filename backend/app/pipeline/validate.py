"""Visual + functional validation of generated UIs in a real headless browser (Playwright).

The validator loads the same runtime page the user sees (`/runtime/preview.html`), served straight from
disk through request interception, so it works in-process without the API server running.
One browser instance stays alive on a dedicated worker thread (Playwright's sync API is single-threaded);
`validate()` / `extract_dom()` can be called from any thread.
"""
from __future__ import annotations

import base64
import mimetypes
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from .. import config
from . import ir as irm

ORIGIN = "http://ngui.local"
TEXTUAL_TYPES = {"heading", "text", "button", "link", "nav_item", "list"}
PREVIEW_URL = f"{ORIGIN}/runtime/preview.html"
VIEWPORT = {"width": 1280, "height": 800}
SAMPLE_VALUES = {"email": "test.user@example.com", "password": "Secret123!", "tel": "5551234567",
                 "number": "42", "date": "2026-01-15", "search": "query", "text": "Sample text"}
FORMAT_SAMPLES = {"email": "test.user@example.com", "phone": "5551234567", "number": "42"}

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ngui-browser")
_state: dict = {"pw": None, "browser": None, "context": None, "page": None, "channel": None}
_start_lock = threading.Lock()


# --------------------------------------------------------------------------- browser lifecycle (worker thread)

def _channel_order() -> list[str]:
    forced = os.environ.get("NGUI_BROWSER", "").strip().lower()
    if forced in ("msedge", "chromium"):
        return [forced, "chromium" if forced == "msedge" else "msedge"]
    return ["msedge", "chromium"] if sys.platform.startswith("win") else ["chromium", "msedge"]


def _serve_runtime(route) -> None:
    path = route.request.url.split("?", 1)[0].removeprefix(ORIGIN)
    if path.startswith("/runtime/"):
        file = (config.RUNTIME_DIR / path.removeprefix("/runtime/")).resolve()
        if file.is_file() and config.RUNTIME_DIR.resolve() in file.parents:
            mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            route.fulfill(status=200, body=file.read_bytes(), headers={"Content-Type": mime, "Cache-Control": "max-age=3600"})
            return
    route.fulfill(status=404, body="not found")


def _ensure_page():
    if _state["page"] is not None and not _state["page"].is_closed():
        return _state["page"]
    if _state["browser"] is None or not _state["browser"].is_connected():
        if _state["pw"] is None:
            _state["pw"] = sync_playwright().start()
        last_error = None
        for channel in _channel_order():
            try:
                kwargs = {"headless": True}
                if channel == "msedge":
                    kwargs["channel"] = "msedge"
                _state["browser"] = _state["pw"].chromium.launch(**kwargs)
                _state["channel"] = channel
                break
            except PlaywrightError as exc:
                last_error = exc
        else:
            raise RuntimeError(f"No browser available for validation (tried msedge and chromium): {last_error}")
        _state["context"] = _state["browser"].new_context(viewport=VIEWPORT)
        _state["context"].route(f"{ORIGIN}/**", _serve_runtime)
    page = _state["context"].new_page()
    page.goto(PREVIEW_URL, wait_until="load")
    page.wait_for_function("() => window.__ngui && window.Babel && window.ReactDOM")
    _state["page"] = page
    return page


def _run_in_worker(fn, *args):
    future = _executor.submit(_with_page, fn, *args)
    return future.result()


def _with_page(fn, *args):
    try:
        return fn(_ensure_page(), *args)
    except PlaywrightError:
        # Page or browser died: rebuild once and retry.
        try:
            if _state["page"] is not None:
                _state["page"].close()
        except PlaywrightError:
            pass
        _state["page"] = None
        if _state["browser"] is not None and not _state["browser"].is_connected():
            _state["browser"] = None
        return fn(_ensure_page(), *args)


def browser_name() -> str:
    """Browser used (or that will be used) for validation: msedge | chromium | none."""
    if _state["channel"]:
        return _state["channel"]
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
            if base and Path(base, "Microsoft", "Edge", "Application", "msedge.exe").exists():
                return "msedge"
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "") or
                 (Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright" if sys.platform.startswith("win")
                  else Path.home() / ".cache" / "ms-playwright"))
    if cache.exists() and any(p.name.startswith("chromium") for p in cache.iterdir()):
        return "chromium"
    return "none"


def warm_up() -> str:
    """Start the browser now (e.g. at server start) so the first validation is fast."""
    _run_in_worker(lambda page: None)
    return _state["channel"] or "none"


def shutdown() -> None:
    def _close():
        for key in ("context", "browser"):
            try:
                if _state[key] is not None:
                    _state[key].close()
            except PlaywrightError:
                pass
        if _state["pw"] is not None:
            _state["pw"].stop()
        _state.update({"pw": None, "browser": None, "context": None, "page": None})
    _executor.submit(_close).result()


# --------------------------------------------------------------------------- page helpers (worker thread)

NODE_INFO_JS = """
() => {
  const out = {};
  for (const el of document.querySelectorAll('[data-ngid]')) {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const visible = r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden'
      && parseFloat(cs.opacity || '1') > 0.05 && !el.closest('[hidden]');
    out[el.getAttribute('data-ngid')] = {
      type: el.getAttribute('data-ngtype'), visible,
      rect: { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height },
      text: (el.innerText || '').trim().slice(0, 200),
    };
  }
  return { nodes: out, scrollWidth: document.documentElement.scrollWidth };
}
"""

CLICKABLE_JS = """
(id) => {
  const el = document.querySelector(`[data-ngid="${id}"]`);
  if (!el) return { ok: false, detail: 'not in DOM' };
  el.scrollIntoView({ block: 'center' });
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return { ok: false, detail: 'zero size' };
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  const ok = !!hit && (hit === el || el.contains(hit));
  return { ok, detail: ok ? 'hit-test ok' : `covered by <${hit ? hit.tagName.toLowerCase() : 'nothing'}>` };
}
"""


def _run_code(page, code: str) -> dict:
    return page.evaluate("code => window.__ngui.run(code)", code)


def _errors(page) -> list[dict]:
    return page.evaluate("() => window.__ngui.errors()")


def _pw_detail(exc: Exception) -> str:
    """First line of a Playwright error; a click blocked by another element is reported as "covered by ..." (repairable by re-layout)."""
    text = str(exc)
    lines = text.splitlines() or [""]
    for line in lines:
        if "intercepts pointer events" in line:
            return "covered: " + line.strip(" -")[:140]
    return lines[0]


def _control(page, node_id: str):
    return page.locator(f'[data-ngid="{node_id}"]').locator("input, textarea, select").first


def _sample_for(node: dict) -> str:
    return SAMPLE_VALUES.get(node.get("props", {}).get("inputType", "text"), SAMPLE_VALUES["text"])


def _is_visible(page, selector: str) -> bool:
    loc = page.locator(selector)
    return loc.count() > 0 and loc.first.is_visible()


def _with_initial_page(code: str, ir: dict, page_id: str) -> str:
    first = ir["pages"][0]["id"]
    return code.replace(f'useUIStore("{first}"', f'useUIStore("{page_id}"', 1)


# --------------------------------------------------------------------------- checks

def _check(checks: list, cid: str, kind: str, name: str, ok: bool, detail: str, target: str | None = None,
           hard: bool = True) -> None:
    item = {"id": cid, "kind": kind, "name": name, "ok": bool(ok), "detail": detail, "hard": hard}
    if target:
        item["target"] = target
    checks.append(item)


def _norm_rects(rects: dict[str, dict]) -> dict[str, dict]:
    box = irm.union_bbox(list(rects.values()))
    if not box or box["w"] <= 0 or box["h"] <= 0:
        return {}
    return {k: {"x": (r["x"] - box["x"]) / box["w"], "y": (r["y"] - box["y"]) / box["h"],
                "w": r["w"] / box["w"], "h": r["h"] / box["h"]} for k, r in rects.items()}


def _visual_checks(ir: dict, page_ir: dict, info: dict, checks: list, analysis: dict | None) -> dict:
    nodes_info = info["nodes"]
    moved = set(ir.get("meta", {}).get("moved", []))
    expected = [n for n, _, _ in _walk_page(page_ir)]
    visible_expected = [n for n in expected if not irm.is_hidden(ir, n["id"])]
    present = 0
    for node in expected:
        got = nodes_info.get(node["id"])
        hidden = irm.is_hidden(ir, node["id"])
        if got is None:
            _check(checks, f"presence:{node['id']}", "visual", "component rendered", False, "missing from DOM", node["id"])
            continue
        if hidden:
            wrongly = node.get("style", {}).get("hidden") and node.get("bbox") and not intentionally_hidden(ir, node["id"])
            _check(checks, f"presence:{node['id']}", "visual", "component rendered", not wrongly,
                   "hidden although it is drawn in the sketch" if wrongly else "in DOM (hidden by design)", node["id"])
            continue
        ok = got["visible"] and got["rect"]["x"] >= -1 and got["rect"]["x"] + got["rect"]["w"] <= info["scrollWidth"] + 1
        detail = "visible" if ok else ("not visible" if not got["visible"] else "outside the page")
        if ok and node["type"] in TEXTUAL_TYPES and not got["text"]:
            ok, detail = False, "renders no text"  # an empty box is not the drawn component
        present += ok
        _check(checks, f"presence:{node['id']}", "visual", "component rendered and visible", ok, detail, node["id"])
        collapsed = _collapsed(node, got)
        if ok and collapsed:
            _check(checks, f"size:{node['id']}", "visual", "component has a usable size", False, collapsed, node["id"])

    # Order inside each container follows the IR/sketch order along the layout direction.
    for node, _, _ in _walk_page(page_ir):
        kids = [c for c in node.get("children", []) if nodes_info.get(c["id"], {}).get("visible")]
        if len(kids) < 2:
            continue
        direction = node.get("layout", {}).get("direction", "column")
        bad = []
        for prev, cur in zip(kids, kids[1:]):
            a, b = nodes_info[prev["id"]]["rect"], nodes_info[cur["id"]]["rect"]
            ok = b["y"] >= a["y"] - 2 if direction == "column" else (b["x"] >= a["x"] - 2 or b["y"] >= a["y"] + a["h"] - 2)
            if not ok:
                bad.append(f"{cur['id']} before {prev['id']}")
        _check(checks, f"order:{node['id']}", "visual", f"{direction} order of children", not bad,
               "; ".join(bad) or f"{len(kids)} children in order", node["id"])
        sketched = [c for c in node.get("children", []) if c.get("bbox") and c["id"] not in moved]
        if direction == "column" and len(sketched) > 1:
            wrong = [f"{b['id']} drawn above {a['id']}" for a, b in zip(sketched, sketched[1:])
                     if b["bbox"]["y"] + b["bbox"]["h"] <= a["bbox"]["y"] + 0.005]
            _check(checks, f"sketch_order:{node['id']}", "visual", "children follow the sketch's vertical order",
                   not wrong, "; ".join(wrong) or "matches sketch", node["id"])

    # Sketch vs render: pairwise vertical order and IoU after normalising both to their content box.
    leaves = [n for n in expected if n.get("bbox") and "children" not in n and n["id"] not in moved
              and nodes_info.get(n["id"], {}).get("visible")]
    sketch_boxes = {n["id"]: n["bbox"] for n in leaves}
    render_boxes = {n["id"]: nodes_info[n["id"]]["rect"] for n in leaves}
    pairs = consistent = 0
    ids = list(sketch_boxes)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            sa, sb = sketch_boxes[a], sketch_boxes[b]
            if sa["y"] + sa["h"] <= sb["y"]:
                first, second = a, b
            elif sb["y"] + sb["h"] <= sa["y"]:
                first, second = b, a
            else:
                continue
            pairs += 1
            consistent += render_boxes[first]["y"] < render_boxes[second]["y"] + 1
    order_consistency = consistent / pairs if pairs else 1.0
    ious = []
    if len(leaves) >= 2:
        ns, nr = _norm_rects(sketch_boxes), _norm_rects(render_boxes)
        for node in leaves:
            value = irm.iou(ns[node["id"]], nr[node["id"]])
            ious.append(value)
            if value < 0.1:
                _check(checks, f"layout:{node['id']}", "visual", "position/size close to the sketch", False,
                       f"IoU {value:.2f} vs sketch", node["id"], hard=False)
    layout_iou = sum(ious) / len(ious) if ious else 1.0
    if leaves:
        _check(checks, "layout:overall", "visual", "layout similar to the sketch (mean IoU)", layout_iou >= 0.25,
               f"mean IoU {layout_iou:.2f} over {len(ious)} sketched components; pairwise order {order_consistency:.2f}",
               hard=False)
    if analysis and analysis.get("components"):
        removed = ir.get("meta", {}).get("removed_sketch", [])
        sketched_nodes = [n for n, _, _ in irm.walk(ir) if n.get("bbox") and
                          (not irm.is_hidden(ir, n["id"]) or intentionally_hidden(ir, n["id"]))]
        for idx, comp in enumerate(analysis["components"]):
            if comp.get("type") == "text" and not comp.get("label"):
                continue
            covered = any(irm.iou(comp["bbox"], n["bbox"]) > 0.5 for n in sketched_nodes) or \
                any(irm.iou(comp["bbox"], r["bbox"]) > 0.5 for r in removed) or \
                any(irm.contains(n["bbox"], comp["bbox"], 0.9) and n["type"] in ("input", "textarea", "select", "checkbox", "radio")
                    for n in sketched_nodes) or comp.get("type") == "text" and _absorbed_label(comp, sketched_nodes)
            if not covered:
                _check(checks, f"coverage:{idx}", "visual", "sketch component represented in the UI", False,
                       f"sketched {comp['type']} {comp.get('label', '')!r} has no matching component", None)
    presence = present / len(visible_expected) if visible_expected else 1.0
    return {"presence": round(presence, 4), "layout_iou": round(layout_iou, 4), "order_consistency": round(order_consistency, 4)}


def _collapsed(node: dict, got: dict) -> str | None:
    """Why a visible component has no usable size (an explicit 0 in its style, or a sliver on screen), else None."""
    style = node.get("style", {})
    for key in ("width", "height"):
        value = style.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value <= 0:
            return f"style.{key} is {value}"
    if node["type"] in ("divider", "icon", "page") or "children" in node and not node.get("children"):
        return None
    rect = got["rect"]
    if rect["w"] < 4 or rect["h"] < 4:
        return f"collapsed to {rect['w']:.0f}x{rect['h']:.0f}px"
    return None


def _reference_checks(ir: dict, reference: dict | None, checks: list) -> None:
    """Compare against an earlier snapshot of the IR: what is gone that nobody removed, what got hidden."""
    if not reference:
        return
    removed = set(ir.get("meta", {}).get("removed_ids", []))
    now = {n["id"]: n for n, _, _ in irm.walk(ir)}
    page_ids = {p["id"] for p in ir.get("pages", [])}
    gone: set[str] = set()
    for page in reference.get("pages", []):
        if page["id"] not in page_ids:
            continue  # a page the user removed
        for node, parent, _ in irm.walk({"pages": [page], "meta": {}}):
            if node["type"] == "page" or node["id"] in now or node["id"] in removed:
                continue
            if parent is not None and (parent["id"] in gone or parent["id"] in removed):
                continue  # reported through its ancestor / removed on purpose
            gone.add(node["id"])
            _check(checks, f"missing:{node['id']}", "visual", "component of the previous version is still there", False,
                   f"{node['type']} {node.get('label', '')!r} was in the reference version and is gone", node["id"])
    for node, _, _ in irm.walk(reference):
        cur = now.get(node["id"])
        if cur is not None and cur.get("style", {}).get("hidden") and not node.get("style", {}).get("hidden") \
                and node["id"] not in ir.get("meta", {}).get("hidden_by_user", []) and not intentionally_hidden(ir, node["id"]):
            _check(checks, f"snapshot_hidden:{node['id']}", "visual", "component visible as in the previous version", False,
                   "hidden although it was visible in the reference version", node["id"])


def intentionally_hidden(ir: dict, node_id: str) -> bool:
    """Hidden on purpose: the user hid it, or a toggle_visibility action shows it later."""
    if node_id in ir.get("meta", {}).get("hidden_by_user", []):
        return True
    chain = {node_id} | {a["id"] for a in irm.ancestors(ir, node_id)}
    return any(action.get("type") == "toggle_visibility" and action.get("target") in chain
               for n, _, _ in irm.walk(ir) for event in n.get("events", []) for action in event.get("actions", []))


def _absorbed_label(comp: dict, nodes: list[dict]) -> bool:
    label = (comp.get("label") or "").strip().lower()
    return bool(label) and any((n.get("label") or "").strip().lower() == label for n in nodes)


def _walk_page(page_ir: dict):
    stack = [(page_ir["root"], None)]
    while stack:
        node, parent = stack.pop()
        yield node, parent, page_ir
        for child in reversed(node.get("children", [])):
            stack.append((child, node))


def _basic_functional(page, ir: dict, page_ir: dict, info: dict, checks: list) -> None:
    for node, _, _ in _walk_page(page_ir):
        if not info["nodes"].get(node["id"], {}).get("visible"):
            continue
        if node["type"] in irm.CLICKABLE_TYPES:
            res = page.evaluate(CLICKABLE_JS, node["id"])
            _check(checks, f"clickable:{node['id']}", "functional", "clickable", res["ok"], res["detail"], node["id"])
        elif node["type"] in ("input", "textarea"):
            value = _sample_for(node)
            try:
                control = _control(page, node["id"])
                control.fill(value, timeout=1500)
                got = control.input_value(timeout=1000)
                ok, detail = got == value, f"typed {value!r}, read {got!r}"
            except PlaywrightError as exc:
                ok, detail = False, f"cannot type: {_pw_detail(exc)}"
            _check(checks, f"typing:{node['id']}", "functional", "accepts typing", ok, detail, node["id"])
        elif node["type"] == "select":
            options = node.get("props", {}).get("options") or []
            if options:
                try:
                    _control(page, node["id"]).select_option(options[0], timeout=1500)
                    ok, detail = True, f"selected {options[0]!r}"
                except PlaywrightError as exc:
                    ok, detail = False, _pw_detail(exc)
                _check(checks, f"typing:{node['id']}", "functional", "option can be selected", ok, detail, node["id"])
        elif node["type"] in ("checkbox", "radio"):
            try:
                page.locator(f'[data-ngid="{node["id"]}"] input').first.check(timeout=1500)
                ok, detail = True, "checked"
            except PlaywrightError as exc:
                ok, detail = False, _pw_detail(exc)
            _check(checks, f"typing:{node['id']}", "functional", "can be checked", ok, detail, node["id"])


def _trigger(page, ir: dict, node: dict, on: str) -> None:
    sel = f'[data-ngid="{node["id"]}"]'
    if on == "submit":
        page.evaluate("""(sel) => { const f = document.querySelector(sel);
            if (f.requestSubmit) f.requestSubmit(); else f.dispatchEvent(new Event('submit', {cancelable: true, bubbles: true})); }""", sel)
    elif on == "change":
        if node["type"] in ("checkbox", "radio"):
            page.locator(f"{sel} input").first.click(timeout=1500)
        elif node["type"] == "select":
            options = node.get("props", {}).get("options") or []
            if options:
                _control(page, node["id"]).select_option(options[0], timeout=1500)
        else:
            _control(page, node["id"]).fill(_sample_for(node), timeout=1500)
    else:
        page.locator(sel).first.click(timeout=1500)
    page.wait_for_timeout(30)


def _fill_valid(page, ir: dict, actions: list[dict]) -> None:
    formats = {a["target"]: a["format"] for a in actions if a["type"] == "validate_format"}
    targets = {t for a in actions if a["type"] == "validate_required" for t in a.get("targets", [])} | set(formats)
    for target in targets:
        node, _, _ = irm.find(ir, target)
        if node is None:
            continue
        value = FORMAT_SAMPLES.get(formats.get(target, ""), _sample_for(node))
        if node["type"] == "checkbox":
            page.locator(f'[data-ngid="{target}"] input').first.check(timeout=1500)
        elif node["type"] == "select":
            options = node.get("props", {}).get("options") or ["x"]
            _control(page, target).select_option(options[0], timeout=1500)
        else:
            _control(page, target).fill(value, timeout=1500)


def _event_checks(page, ir: dict, code: str, checks: list, counters: dict) -> None:
    for node, _, page_ir in irm.walk(ir):
        for event in node.get("events", []):
            on, actions = event.get("on", "click"), event.get("actions", [])
            if not actions:
                continue
            counters["total"] += 1
            run_code = code if page_ir is ir["pages"][0] else _with_initial_page(code, ir, page_ir["id"])
            problems, notes = [], []
            try:
                validations = [a for a in actions if a["type"].startswith("validate_")]
                effects = [a for a in actions if not a["type"].startswith("validate_")]
                msg_sel = f'[data-ngmsg="{node["id"]}"]'
                if validations and any(a["type"] == "validate_required" for a in validations):
                    _run_code(page, run_code)
                    if on != "change":
                        _trigger(page, ir, node, on)
                        if _is_visible(page, f'{msg_sel}[role="alert"]'):
                            notes.append("empty fields -> error shown")
                        else:
                            problems.append("no error message for empty required fields")
                        nav = next((a for a in effects if a["type"] == "navigate"), None)
                        if nav and nav["page"] != page_ir["id"] and _is_visible(page, f'[data-ngid="{nav["page"]}"]'):
                            problems.append("navigated despite failed validation")
                _run_code(page, run_code)
                before = {a["target"]: _is_visible(page, f'[data-ngid="{a["target"]}"]')
                          for a in effects if a["type"] == "toggle_visibility"}
                if validations:
                    _fill_valid(page, ir, validations)
                _trigger(page, ir, node, on)
                for action in effects:
                    kind = action["type"]
                    if kind == "navigate":
                        ok = _is_visible(page, f'[data-ngid="{action["page"]}"]')
                        (notes if ok else problems).append(f"navigate -> {action['page']}" + ("" if ok else " not shown"))
                    elif kind == "show_message":
                        ok = _is_visible(page, msg_sel) and action["text"].strip()[:40] in page.locator(msg_sel).first.inner_text()
                        (notes if ok else problems).append("message shown" if ok else f"message {action['text']!r} not shown")
                    elif kind == "toggle_visibility":
                        now = _is_visible(page, f'[data-ngid="{action["target"]}"]')
                        ok = now != before.get(action["target"])
                        (notes if ok else problems).append(f"toggle {action['target']}" + ("" if ok else " had no effect"))
                    elif kind == "set_text":
                        loc = page.locator(f'[data-ngid="{action["target"]}"]')
                        ok = loc.count() > 0 and action["text"] in loc.first.inner_text()
                        (notes if ok else problems).append(f"text of {action['target']}" + (" set" if ok else " unchanged"))
                if validations and not effects:
                    if _is_visible(page, f'{msg_sel}[role="alert"]'):
                        problems.append("error shown although fields were valid")
                    else:
                        notes.append("valid input -> no error")
                if [e for e in _errors(page) if not e.get("console")]:
                    problems.append("runtime error during interaction: " + _errors(page)[0]["message"][:120])
            except PlaywrightError as exc:
                problems.append(f"could not simulate: {_pw_detail(exc)[:160]}")
            ok = not problems
            counters["passed"] += ok
            _check(checks, f"event:{node['id']}:{on}", "functional", f"{on} behaviour works", ok,
                   "; ".join(problems or notes), node["id"])


def _validate_impl(page, ir: dict, code: str, analysis: dict | None, reference: dict | None = None) -> dict:
    started = time.perf_counter()
    checks: list[dict] = []
    result = _run_code(page, code)
    errors = result["errors"]
    info = page.evaluate(NODE_INFO_JS)
    rendered = len(info["nodes"]) > 0
    _check(checks, "runtime:render", "functional", "renders without runtime errors", rendered and not errors,
           "; ".join(e["message"][:200] for e in errors[:3]) or f"{len(info['nodes'])} components rendered")
    visual = _visual_checks(ir, ir["pages"][0], info, checks, analysis)
    _reference_checks(ir, reference, checks)
    screenshot = page.screenshot(full_page=True, type="png")
    dom = [{"id": k, "type": v["type"], "rect": v["rect"]} for k, v in info["nodes"].items()]
    counters = {"total": 0, "passed": 0}
    if rendered and not errors:
        _basic_functional(page, ir, ir["pages"][0], info, checks)
        for extra in ir["pages"][1:]:
            _run_code(page, _with_initial_page(code, ir, extra["id"]))
            extra_info = page.evaluate(NODE_INFO_JS)
            for node, _, _ in _walk_page(extra):
                got = extra_info["nodes"].get(node["id"])
                ok = bool(got) and (got["visible"] or irm.is_hidden(ir, node["id"]))
                _check(checks, f"presence:{node['id']}", "visual", "component rendered and visible", ok,
                       "visible" if ok else "missing or invisible", node["id"])
        _event_checks(page, ir, code, checks, counters)
        runtime_errors = [e["message"] for e in _errors(page) if not e.get("console")]
    else:
        runtime_errors = [e["message"] for e in errors]
    hard = [c for c in checks if c["hard"]]
    functional_basic = [c for c in checks if c["kind"] == "functional" and not c["id"].startswith(("event:", "runtime:"))]
    basic_ratio = sum(c["ok"] for c in functional_basic) / len(functional_basic) if functional_basic else 1.0
    interaction_ratio = counters["passed"] / counters["total"] if counters["total"] else 1.0
    no_errors = 1.0 if rendered and not errors else 0.0
    score = (0.25 * visual["presence"] + 0.1 * visual["order_consistency"] + 0.1 * visual["layout_iou"]
             + 0.2 * no_errors + 0.15 * basic_ratio + 0.2 * interaction_ratio)
    return {
        "passed": all(c["ok"] for c in hard),
        "score": round(score, 4),
        "checks": checks,
        "visual": visual,
        "functional": {"runtime_errors": runtime_errors, "interactions_total": counters["total"],
                       "interactions_passed": counters["passed"], "basic_ratio": round(basic_ratio, 4)},
        "screenshot_b64": base64.b64encode(screenshot).decode(),
        "dom": dom,
        "browser": _state["channel"],
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def validate(ir: dict, preview_code: str, analysis: dict | None = None, reference: dict | None = None) -> dict:
    """Render `preview_code` headlessly and check it against the IR (and the sketch analysis if given).

    `reference` is an earlier IR snapshot of the same UI (the previous version). Components that were in it and
    are gone from `ir`, without the user having removed them, are reported as failing `missing:<id>` checks;
    components hidden now but visible in the snapshot as `snapshot_hidden:<id>`."""
    return _run_in_worker(_validate_impl, ir, preview_code, analysis, reference)


# --------------------------------------------------------------------------- generic DOM extraction

EXTRACT_JS = """
() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden' && !el.closest('[hidden]'); };
  const text = (el) => (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').replace(/\\s*\\*$/, '').slice(0, 120);
  const out = []; const taken = new Set();
  const add = (el, type, label) => {
    if (taken.has(el) || !vis(el)) return; taken.add(el);
    const r = el.getBoundingClientRect();
    out.push({ type, label: label ?? text(el), tag: el.tagName.toLowerCase(),
               rect: { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height } });
  };
  const labelFor = (ctl) => {
    if (ctl.id) { const l = document.querySelector(`label[for="${CSS.escape(ctl.id)}"]`); if (l) return text(l); }
    const wrap = ctl.closest('label'); if (wrap) return text(wrap);
    return ctl.getAttribute('aria-label') || ctl.getAttribute('placeholder') || '';
  };
  const root = document.getElementById('root') || document.body;
  root.querySelectorAll('nav, [role=navigation]').forEach(el => add(el, 'navbar'));
  root.querySelectorAll('header').forEach(el => add(el, 'header'));
  root.querySelectorAll('form').forEach(el => add(el, 'form', ''));
  root.querySelectorAll('h1,h2,h3,h4,h5,h6,[role=heading]').forEach(el => add(el, 'heading'));
  root.querySelectorAll('button, [role=button], input[type=submit], input[type=button]').forEach(el => add(el, 'button'));
  root.querySelectorAll('input[type=checkbox]').forEach(el => add(el.closest('label') || el, 'checkbox', labelFor(el)));
  root.querySelectorAll('input[type=radio]').forEach(el => add(el.closest('label') || el, 'radio', labelFor(el)));
  root.querySelectorAll('textarea').forEach(el => add(el, 'textarea', labelFor(el)));
  root.querySelectorAll('select').forEach(el => add(el, 'select', labelFor(el)));
  root.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button]):not([type=hidden])')
      .forEach(el => add(el, 'input', labelFor(el)));
  root.querySelectorAll('a, [role=link]').forEach(el => add(el, el.closest('nav') ? 'nav_item' : 'link'));
  root.querySelectorAll('img, [role=img], svg[aria-label]').forEach(el => { if (!el.closest('button,a')) add(el, 'image', el.getAttribute('alt') || el.getAttribute('aria-label') || ''); });
  root.querySelectorAll('hr').forEach(el => add(el, 'divider', ''));
  const covered = (el) => [...taken].some(t => t !== el && (t.contains(el)) && !['form','nav','header'].includes(t.tagName.toLowerCase()));
  root.querySelectorAll('label').forEach(l => taken.add(l));
  root.querySelectorAll('p, span, li, small, strong, em, div, td, th, label').forEach(el => {
    if (taken.has(el) || covered(el)) return;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 0);
    if (own && el.querySelector('input,button,select,textarea') === null) add(el, 'text');
  });
  return out;
}
"""


def _extract_impl(page, preview_code: str, screenshot: bool) -> dict:
    started = time.perf_counter()
    result = _run_code(page, preview_code)
    comps = page.evaluate(EXTRACT_JS)
    norm = _norm_rects({str(i): c["rect"] for i, c in enumerate(comps)})
    for i, comp in enumerate(comps):
        comp["bbox"] = {k: round(v, 4) for k, v in norm.get(str(i), comp["rect"]).items()}
    out = {
        "components": comps,
        "errors": [e["message"] for e in result["errors"]],
        "rendered": bool(comps),
        "duration_ms": 0,
    }
    if screenshot:
        out["screenshot_b64"] = base64.b64encode(page.screenshot(full_page=True, type="png")).decode()
    out["duration_ms"] = int((time.perf_counter() - started) * 1000)
    return out


def extract_dom(preview_code: str, screenshot: bool = False) -> dict:
    """Detect generic components (by tag/role/text, not data-ngid) so baseline and pipeline are measured alike.

    Returns {"components":[{type,label,tag,rect,bbox(normalised to content box)}], "errors", "rendered", ...}.
    """
    return _run_in_worker(_extract_impl, preview_code, screenshot)


PROBE_JS = "() => (document.getElementById('root') || document.body).innerText"


def _probe_impl(page, preview_code: str) -> dict:
    """Click every visible button/link once (fresh state each time) and report whether the UI reacted."""
    _run_code(page, preview_code)
    count = page.locator("#root button:visible, #root a:visible, #root [role=button]:visible").count()
    results = []
    for i in range(min(count, 25)):
        _run_code(page, preview_code)
        loc = page.locator("#root button:visible, #root a:visible, #root [role=button]:visible").nth(i)
        label = (loc.inner_text() or "").strip()[:60]
        before = page.evaluate(PROBE_JS)
        try:
            loc.click(timeout=1500)
            page.wait_for_timeout(40)
            after = page.evaluate(PROBE_JS)
            alert = page.locator("[role=alert]:visible").count() > 0
            results.append({"label": label, "clicked": True, "changed": after != before, "alert": alert,
                            "errors": [e["message"] for e in _errors(page) if not e.get("console")]})
        except PlaywrightError as exc:
            results.append({"label": label, "clicked": False, "changed": False, "alert": False,
                            "errors": [str(exc).splitlines()[0]]})
    return {"clickables": results}


def probe_interactions(preview_code: str) -> dict:
    return _run_in_worker(_probe_impl, preview_code)


def screenshot_png(preview_code: str) -> bytes:
    def _shot(page, code):
        _run_code(page, code)
        return page.screenshot(full_page=True, type="png")
    return _run_in_worker(_shot, preview_code)


def strip_screenshot(report: dict) -> dict:
    return {k: v for k, v in report.items() if k != "screenshot_b64"}

