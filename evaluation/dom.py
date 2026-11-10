"""Headless rendering + generic DOM measurement used for BOTH the pipeline and the baseline.

The same harness page renders any "preview" program (single-script JSX on the React/ReactDOM globals,
the runtime contract both systems follow): vendored React 18 UMD + @babel/standalone + runtime.css
from backend/app/static/runtime, served through Playwright request routing (no server needed).

`extract()` classifies rendered elements into contract component types using only tags, ARIA roles,
input types and visual cues (borders/shadows for cards). It deliberately ignores data-ngtype so that
the pipeline gets no advantage over the baseline; the pipeline's own data-ngid/data-ngtype attributes
are recorded alongside for pipeline-only analyses.

`simulate()` runs one interaction expectation (validate_required, validate_format, show_message,
navigate) on a fresh render, again with the same procedure for both systems.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from common import RUNTIME

log = logging.getLogger("eval.dom")

ORIGIN = "http://ngui.eval"
VIEWPORT = {"width": 1000, "height": 800}

HARNESS = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/runtime/runtime.css">
<style>html,body{margin:0}</style>
<script>window.NGUI_PHOTO_BASE = '/runtime/photos/';</script></head>
<body><div id="root"></div>
<script src="/runtime/vendor/react.production.min.js"></script>
<script src="/runtime/vendor/react-dom.production.min.js"></script>
<script src="/runtime/vendor/babel.min.js"></script>
<script>
window.__ngErrors = [];
window.addEventListener('error', e => window.__ngErrors.push(String(e.message || e)));
window.addEventListener('unhandledrejection', e => window.__ngErrors.push(String(e.reason)));
window.__ngRun = function (code) {
  let js;
  try { js = Babel.transform(code, {presets: [['react', {runtime: 'classic'}]], sourceType: 'script'}).code; }
  catch (e) { return {ok: false, stage: 'transpile', error: String(e && e.message || e)}; }
  try { (0, eval)(js); }
  catch (e) { return {ok: false, stage: 'run', error: String(e && e.stack || e)}; }
  try {
    const root = document.getElementById('root');
    if (!root.childElementCount && typeof App === 'function') {
      ReactDOM.createRoot(root).render(React.createElement(App));
    }
  } catch (e) { return {ok: false, stage: 'mount', error: String(e && e.stack || e)}; }
  return {ok: true};
};
</script></body></html>"""

EXTRACT_JS = r"""
() => {
  const root = document.getElementById('root');
  const docW = Math.max(document.documentElement.scrollWidth, window.innerWidth);
  const docH = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight, 1);
  const out = [];
  let idx = 0;
  const T = s => (s || '').replace(/\s+/g, ' ').trim();
  const rectOf = el => { const r = el.getBoundingClientRect();
    return {x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height}; };
  const visible = el => {
    const r = el.getBoundingClientRect();
    const thin = el.tagName === 'HR' || el.getAttribute('role') === 'separator';
    if (r.width < 2 || (r.height < 2 && !(thin && r.height > 0)) || (thin && r.height === 0 && r.width < 2)) return false;
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    }
    return true;
  };
  const inNav = el => !!el.closest('nav,[role=navigation]');
  const union = (a, b) => { const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y);
    return {x, y, w: Math.max(a.x + a.w, b.x + b.w) - x, h: Math.max(a.y + a.h, b.y + b.h) - y}; };
  const controlLabel = el => {
    const al = el.getAttribute('aria-label'); if (al) return {text: T(al)};
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return {text: T(l.innerText), el: l}; }
    const wrap = el.closest('label'); if (wrap) return {text: T(wrap.innerText), el: wrap};
    let p = el.previousElementSibling;
    if (p && (p.tagName === 'LABEL' || p.tagName === 'SPAN') && T(p.innerText) && !(p.htmlFor && p.htmlFor !== el.id)) return {text: T(p.innerText), el: p};
    const n = el.nextElementSibling;
    if ((el.type === 'checkbox' || el.type === 'radio') && n && T(n.innerText)) return {text: T(n.innerText), el: n};
    const par = el.parentElement;
    if (par && par.querySelectorAll('input,select,textarea').length === 1) {
      const lab = par.querySelector(':scope > label, :scope > span'); if (lab && T(lab.innerText)) return {text: T(lab.innerText), el: lab}; }
    if (el.placeholder) return {text: T(el.placeholder)};
    if (el.name) return {text: T(el.name)};
    return {text: ''};
  };
  const usedLabels = new Set();
  const push = (el, type, label, extra) => {
    const r = extra && extra.rect ? extra.rect : rectOf(el);
    el.setAttribute('data-ev-idx', String(idx));
    const cs = getComputedStyle(el);
    out.push(Object.assign({
      idx: idx++, type, label: T(label), tag: el.tagName.toLowerCase(),
      rect: r, nrect: {x: r.x / docW, y: r.y / docH, w: r.w / docW, h: r.h / docH},
      color: cs.color, bg: cs.backgroundColor, border: cs.borderTopColor, fontSize: parseFloat(cs.fontSize),
      fontWeight: cs.fontWeight, ngid: el.closest('[data-ngid]') ? el.closest('[data-ngid]').getAttribute('data-ngid') : null,
      ngtype: el.getAttribute('data-ngtype') || (el.closest('[data-ngtype]') ? el.closest('[data-ngtype]').getAttribute('data-ngtype') : null),
    }, extra || {}));
  };
  const all = root ? Array.from(root.querySelectorAll('*')) : [];
  // pass 1: controls (so their labels are known before text classification)
  for (const el of all) {
    if (!visible(el)) continue;
    const tag = el.tagName;
    if (tag === 'INPUT') {
      const t = (el.getAttribute('type') || 'text').toLowerCase();
      if (t === 'hidden') continue;
      const lab = controlLabel(el);
      if (lab.el) usedLabels.add(lab.el);
      if (t === 'checkbox' || t === 'radio') {
        const rect = lab.el && visible(lab.el) ? union(rectOf(el), rectOf(lab.el)) : rectOf(el);
        push(el, t, lab.text, {rect, checked: el.checked, name: el.name || ''});
      } else if (t === 'submit' || t === 'button' || t === 'reset') {
        push(el, 'button', el.value || lab.text);
      } else {
        push(el, 'input', lab.text, {inputType: t, placeholder: el.placeholder || '', required: el.required,
                                     value: el.value});
      }
    } else if (tag === 'TEXTAREA') {
      const lab = controlLabel(el); if (lab.el) usedLabels.add(lab.el);
      push(el, 'textarea', lab.text, {placeholder: el.placeholder || '', required: el.required});
    } else if (tag === 'SELECT') {
      const lab = controlLabel(el); if (lab.el) usedLabels.add(lab.el);
      push(el, 'select', lab.text, {options: Array.from(el.options).map(o => T(o.text))});
    }
  }
  const CLICK_SEL = 'button,a,[role=button],[role=link],input[type=submit],input[type=button]';
  for (const el of all) {
    if (!visible(el) || el.hasAttribute('data-ev-idx')) continue;
    const tag = el.tagName, role = el.getAttribute('role');
    const anc = el.parentElement ? el.parentElement.closest(CLICK_SEL) : null;
    if (/^H[1-6]$/.test(tag) || role === 'heading') {
      if (anc) continue;
      push(el, 'heading', el.innerText, {level: +(tag[1] || el.getAttribute('aria-level') || 2)});
    } else if (tag === 'BUTTON' || role === 'button') {
      if (anc) continue;
      push(el, inNav(el) ? 'nav_item' : 'button', el.innerText || el.getAttribute('aria-label') || el.title, {inNav: inNav(el)});
    } else if (tag === 'A' || role === 'link') {
      if (anc) continue;
      push(el, inNav(el) ? 'nav_item' : 'link', el.innerText || el.getAttribute('aria-label') || el.title, {inNav: inNav(el)});
    } else if (tag === 'IMG' || role === 'img') {
      const r = rectOf(el);
      push(el, (r.w < 40 && r.h < 40) ? 'icon' : 'image', el.getAttribute('alt') || el.getAttribute('aria-label') || '');
    } else if (tag === 'svg' || tag === 'SVG') {
      if (el.parentElement && el.parentElement.closest('svg')) continue;
      if (anc) continue;
      const r = rectOf(el);
      push(el, (r.w < 48 && r.h < 48) ? 'icon' : 'image', el.getAttribute('aria-label') || '');
    } else if (tag === 'HR' || role === 'separator') {
      push(el, 'divider', '');
    } else if (tag === 'NAV' || role === 'navigation') {
      push(el, 'navbar', '');
    } else if (tag === 'HEADER') {
      push(el, 'header', '');
    } else if (tag === 'FORM') {
      push(el, 'form', '');
    } else if (tag === 'UL' || tag === 'OL') {
      if (anc || el.closest('nav')) continue;
      push(el, 'list', '', {items: Array.from(el.children).map(li => T(li.innerText))});
    }
  }
  // pass 3: background-image placeholders, dividers drawn as thin boxes, cards, text
  for (const el of all) {
    if (!visible(el) || el.hasAttribute('data-ev-idx')) continue;
    if (el.closest('svg')) continue;
    const cs = getComputedStyle(el), r = rectOf(el);
    if (cs.backgroundImage && cs.backgroundImage.startsWith('url(') && r.w >= 40 && r.h >= 40) {
      push(el, 'image', el.getAttribute('aria-label') || ''); continue;
    }
    if (!el.childElementCount && r.h <= 4 && r.w >= 60 && !T(el.innerText)) { push(el, 'divider', ''); continue; }
  }
  const classified = el => el.hasAttribute('data-ev-idx');
  const SKIP_TEXT_ANC = 'button,a,[role=button],[role=link],h1,h2,h3,h4,h5,h6,select,option,ul,ol,[role=alert],[data-ngmsg]';
  for (const el of all) {
    if (!visible(el) || classified(el) || usedLabels.has(el)) continue;
    if (el.closest(SKIP_TEXT_ANC)) continue;
    if (el.tagName === 'LABEL' && (el.htmlFor || el.querySelector('input,select,textarea'))) continue;
    { const lab = el.closest('label'); if (lab && (usedLabels.has(lab) || lab.querySelector('input,select,textarea'))) continue; }
    { let a = el.parentElement, skip = false; while (a && a !== root) { if (usedLabels.has(a)) { skip = true; break; } a = a.parentElement; } if (skip) continue; }
    if (['SCRIPT', 'STYLE', 'OPTION'].includes(el.tagName)) continue;
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join(' ');
    if (!T(own)) continue;
    let p = el.parentElement, nested = false;
    while (p && p !== root) { if (p.getAttribute('data-ev-text') === '1') { nested = true; break; } p = p.parentElement; }
    if (nested) continue;
    el.setAttribute('data-ev-text', '1');
    push(el, 'text', el.innerText);
  }
  const CONTAINER_TAGS = new Set(['DIV', 'SECTION', 'ARTICLE', 'ASIDE', 'MAIN', 'FIELDSET']);
  for (const el of all) {
    if (!visible(el) || classified(el) || !CONTAINER_TAGS.has(el.tagName)) continue;
    const cs = getComputedStyle(el), r = rectOf(el);
    if (r.w > docW * 0.985 && r.h > docH * 0.9) continue;
    const bordered = ['Top', 'Right', 'Bottom', 'Left'].filter(s => parseFloat(cs['border' + s + 'Width']) > 0 && cs['border' + s + 'Style'] !== 'none').length >= 3;
    const shadow = cs.boxShadow && cs.boxShadow !== 'none';
    const pbg = el.parentElement ? getComputedStyle(el.parentElement).backgroundColor : '';
    const bgDiff = cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== pbg;
    if (!(bordered || shadow || bgDiff)) continue;
    const inner = Array.from(el.querySelectorAll('[data-ev-idx]')).length;
    if (inner >= 2 && r.w >= 80 && r.h >= 60) push(el, 'card', '');
  }
  const alerts = Array.from(document.querySelectorAll('[role=alert],[data-ngmsg]')).filter(visible).map(e => T(e.innerText)).filter(Boolean);
  return {elements: out, docW, docH, text: T(document.body.innerText), alerts, errors: (window.__ngui ? window.__ngui.errors().map(e => e.message) : window.__ngErrors.slice())};
}
"""


def _route_runtime(route):
    url = route.request.url
    path = url[len(ORIGIN):].split("?")[0]
    if path in ("/", "/harness.html"):
        return route.fulfill(status=200, content_type="text/html", body=HARNESS)
    if path.startswith("/runtime/"):
        f = RUNTIME / path[len("/runtime/"):]
        if f.is_file():
            ct = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            return route.fulfill(status=200, content_type=ct, body=f.read_bytes())
        if path.endswith(".css"):
            return route.fulfill(status=200, content_type="text/css", body="")
    return route.fulfill(status=404, body="")


class Renderer:
    """One Chromium for the whole run. Each render uses a fresh page (no state leaks)."""

    def __init__(self):
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.launch()
        except Exception:  # noqa: BLE001
            self.browser = self._pw.chromium.launch(channel="msedge")
        self.ctx = self.browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
        self.ctx.route(f"{ORIGIN}/**", _route_runtime)
        self.ctx.route(re.compile(r"^https?://(?!ngui\.eval).*"), lambda r: r.abort())  # offline, both systems

    def close(self):
        try:
            self.ctx.close()
            self.browser.close()
        finally:
            self._pw.stop()

    # ------------------------------------------------------------------ render
    def open(self, code: str, height: int | None = None):
        page = self.ctx.new_page()
        if height:
            page.set_viewport_size({"width": VIEWPORT["width"], "height": int(height)})
        state = {"console_errors": [], "dialogs": []}
        page.on("console", lambda m: state["console_errors"].append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: state["console_errors"].append(str(e)))

        def on_dialog(d):
            state["dialogs"].append(d.message)
            try:
                d.dismiss()
            except Exception:  # noqa: BLE001
                pass
        page.on("dialog", on_dialog)
        if (RUNTIME / "preview.html").exists():
            # the backend's own runtime page (same one the live preview and validator use)
            page.goto(f"{ORIGIN}/runtime/preview.html")
            page.wait_for_function("window.__ngui && typeof window.__ngui.run === 'function'")
            res = page.evaluate(
                "code => window.__ngui.run(code).then(r => ({ok: r.ok, errors: r.errors.map(e => e.message)}))",
                code or "")
            res["runtime"] = "backend preview.html"
        else:
            page.goto(f"{ORIGIN}/harness.html")
            page.wait_for_function("typeof Babel !== 'undefined' && typeof ReactDOM !== 'undefined'")
            res = page.evaluate("code => window.__ngRun(code)", code or "")
            res["runtime"] = "evaluation harness"
        try:
            page.wait_for_function("document.getElementById('root').childElementCount > 0", timeout=4000)
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(150)
        state["run"] = res
        return page, state

    def render(self, code: str, screenshot: Path | None = None, height: int | None = None) -> dict:
        """Render code and return {ok, run, elements, docW, docH, text, errors, render_ms}."""
        t0 = time.perf_counter()
        page, state = self.open(code, height)
        try:
            snap = page.evaluate(EXTRACT_JS)
            if screenshot:
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot), full_page=True)
            snap["run"] = state["run"]
            snap["console_errors"] = state["console_errors"]
            snap["ok"] = bool(state["run"].get("ok")) and len(snap["elements"]) > 0
            snap["render_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            return snap
        finally:
            page.close()

    # ------------------------------------------------------------------ interactions
    def simulate(self, code: str, expect: dict, target_label: str, height: int | None = None) -> dict:
        """Run one interaction expectation on a fresh render. Same generic procedure for both systems.

        validate_required: leave every field empty, click the target; pass if an error-like message
            appears (new visible text / role=alert / alert() dialog) or native constraint validation
            blocks a form submit (a required field is :invalid).
        validate_format: fill every field with valid data except the named field which gets an invalid
            value, click; pass on an error-like message or the field being :invalid.
        show_message: fill every field validly, click; pass if text containing `text_contains` appears.
        navigate: fill validly, click; pass if a new non-clickable element mentioning the page name appears
            and the clicked view changed.
        """
        kind = expect.get("type") or expect.get("action")
        page, state = self.open(code, height)
        res = {"kind": kind, "target": target_label, "passed": False, "detail": ""}
        try:
            before = page.evaluate(EXTRACT_JS)
            els = before["elements"]
            tgt = find_element(els, target_label, prefer=("button", "link", "nav_item"))
            if tgt is None:
                res["detail"] = "target not found"
                return res
            res["target_found"] = tgt["label"]
            if kind != "validate_required":
                fill_fields(page, els, invalid_label=expect.get("field_label") if kind == "validate_format" else None)
                page.wait_for_timeout(80)
                before = page.evaluate(EXTRACT_JS)
            before_sigs = {(e["type"], norm(e["label"])) for e in before["elements"]}
            n_dialogs = len(state["dialogs"])
            try:
                page.click(f'[data-ev-idx="{tgt["idx"]}"]', timeout=2500)
            except Exception as e:  # noqa: BLE001
                res["detail"] = f"click failed: {str(e)[:120]}"
                return res
            page.wait_for_timeout(350)
            after = page.evaluate(EXTRACT_JS)
            new_dialogs = state["dialogs"][n_dialogs:]
            new_text = _new_text(before["text"], after["text"]) + " " + " ".join(after["alerts"]) + " " + " ".join(new_dialogs)
            invalid = page.evaluate("() => Array.from(document.querySelectorAll('input,textarea,select')).filter(e => !e.checkValidity()).map(e => e.name || e.placeholder || e.type)")
            res["new_text"] = new_text.strip()[:300]
            res["errors"] = after["errors"][:5]
            if kind == "validate_required":
                ok = bool(ERRORISH.search(new_text)) or bool(invalid and _submit_blocked(after, tgt))
                res["detail"] = "error shown" if ERRORISH.search(new_text) else ("native validation" if ok else "no error")
            elif kind == "validate_format":
                ok = bool(ERRORISH.search(new_text)) or bool(invalid)
                res["detail"] = "format error shown" if ok else "no error"
            elif kind == "show_message":
                want = norm(expect.get("text_contains", ""))
                ok = bool(want) and want in norm(new_text)
                res["detail"] = "message shown" if ok else "message not found"
            elif kind == "navigate":
                want = norm(expect.get("page", ""))
                fresh = [e for e in after["elements"] if (e["type"], norm(e["label"])) not in before_sigs
                         and e["type"] not in ("button", "link", "nav_item") and want and want in norm(e["label"])]
                after_sigs = {(e["type"], norm(e["label"])) for e in after["elements"]}
                jac = len(before_sigs & after_sigs) / max(1, len(before_sigs | after_sigs))
                ok = bool(fresh) and jac < 0.85
                res["detail"] = f"new page elements={len(fresh)} jaccard={jac:.2f}"
            else:
                ok = False
                res["detail"] = f"unsupported expectation {kind}"
            res["passed"] = bool(ok)
            return res
        finally:
            page.close()


ERRORISH = re.compile(r"(required|fill|empty|missing|please|invalid|valid|error|must|enter|cannot be blank)", re.I)


def _submit_blocked(after, tgt):
    return tgt["type"] in ("button",)


def _new_text(before: str, after: str) -> str:
    b = set(re.split(r"\s{1,}|\n", before))
    words = [w for w in re.split(r"\s+", after)]
    # keep the after-text if it contains a run of words not seen before
    fresh = [w for w in words if w not in b]
    return " ".join(fresh) if fresh else ""


def norm(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9$@.]+", (s or "").lower().replace("?", "")))


TYPE_EQUIV = {
    "nav_item": {"nav_item", "link", "button"},
    "link": {"link", "nav_item"},
    "button": {"button", "nav_item"},
    "input": {"input"},
    "textarea": {"textarea", "input"},
}


def type_ok(want: str | None, got: str) -> bool:
    if not want:
        return True
    return got in TYPE_EQUIV.get(want, {want})


def find_element(elements: list[dict], label: str, type: str | None = None, prefer=()) -> dict | None:
    """Best element whose label contains `label` (normalised). Exact matches first, then preferred
    types, then the shortest label. label="" matches by type only (first in document order)."""
    want = norm(label)
    cands = []
    for e in elements:
        if type and not type_ok(type, e["type"]):
            continue
        lab = norm(e["label"]) + " " + norm(e.get("placeholder", ""))
        if want and want not in lab:
            continue
        if not want and not type:
            continue
        exact = norm(e["label"]) == want
        cands.append((0 if exact else 1, 0 if e["type"] in prefer else 1, len(e["label"]), e["idx"], e))
    if not cands:
        return None
    cands.sort(key=lambda c: c[:4])
    return cands[0][4]


VALID = {"email": "test.user@example.com", "password": "Passw0rd!23", "tel": "5551234567", "number": "42",
         "date": "2026-11-03", "search": "shoes", "text": "Test value", "url": "https://example.com"}


def fill_fields(page, elements, invalid_label: str | None = None):
    """Fill every field with a valid value (by input type), optionally one field with an invalid value."""
    inv = find_element(elements, invalid_label, "input") if invalid_label else None
    radios_done = set()
    for e in elements:
        sel = f'[data-ev-idx="{e["idx"]}"]'
        try:
            if e["type"] == "input":
                it = e.get("inputType", "text")
                if inv is not None and e["idx"] == inv["idx"]:
                    val = "not-an-email" if it in ("email", "text") else "abc"
                    if it == "email":
                        val = "not-an-email"
                    page.fill(sel, val, timeout=1000)
                else:
                    page.fill(sel, VALID.get(it, VALID["text"]), timeout=1000)
            elif e["type"] == "textarea":
                page.fill(sel, "This is a test message.", timeout=1000)
            elif e["type"] == "select":
                opts = e.get("options") or []
                if len(opts) > 1:
                    page.select_option(sel, index=1, timeout=1000)
            elif e["type"] == "checkbox":
                page.check(sel, timeout=1000)
            elif e["type"] == "radio":
                g = e.get("name") or e["idx"]
                if g not in radios_done:
                    page.check(sel, timeout=1000)
                    radios_done.add(g)
        except Exception:  # noqa: BLE001 - a field that refuses input is simply left as is
            continue


def b64png(path: Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()
