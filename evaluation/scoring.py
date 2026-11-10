"""Interpretation accuracy: compare intent.parse_commands output with commands.jsonl `expected`.

op_ok      some op has the expected op type (create/add/remove/modify/move/resize/style/interaction/navigation)
target_ok  the op's target (anchor for `add`) resolves, in the base IR, to a node whose label contains the
           expected label (and whose type is compatible). The id the LLM gave is used; if it is missing or
           unknown, refine.resolve_target(ref) is applied exactly as the pipeline does. n/a for create.
params_ok  operation-specific parameters (see score_params). n/a for remove (target only).
all_ok     op_ok and every applicable part.
WER        word error rate of the Whisper transcript against the command text, after lower-casing and
           removing punctuation (jiwer), reported per command and corpus-level (total edits / total words).
"""
from __future__ import annotations

import re

import jiwer

import common  # noqa: F401
from app.pipeline import ir as irm, refine
from checks import hue_name

COMPAT = [{"button", "link", "nav_item"}, {"input", "textarea"}, {"heading", "text"}]


def nrm(s) -> str:
    return " ".join(re.findall(r"[a-z0-9$@.:]+", str(s or "").lower().replace("?", "")))


def type_compat(want, got):
    if not want or want == got:
        return True
    return any(want in g and got in g for g in COMPAT)


def _node_by_ref(ir, ref_obj, type_hint=None):
    if ir is None or not ref_obj:
        return None
    if isinstance(ref_obj, str):
        ref_obj = {"ref": ref_obj}
    nid = ref_obj.get("id")
    if nid:
        n, _, _ = irm.find(ir, nid)
        if n is not None:
            return n
    ref = ref_obj.get("ref")
    if ref:
        r = refine.resolve_target(ir, ref, type_hint)
        if r and r.get("id"):
            n, _, _ = irm.find(ir, r["id"])
            return n
    return None


def _label_ok(node, want_label, want_type):
    if node is None:
        return False
    if not type_compat(want_type, node["type"]):
        return False
    if not want_label:
        return True
    return nrm(want_label) in nrm(node.get("label")) or nrm(node.get("label")) == nrm(want_label)


def _style(op):
    ch = op.get("changes") or {}
    st = dict(ch.get("style") or {})
    st.update(op.get("style") or {})
    return st


def hex_to_rgb(h):
    h = str(h).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return None
    return f"rgb({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)})"


def color_hue(v):
    if v is None:
        return None
    hexv = refine.normalize_color(v) or v
    rgb = hex_to_rgb(hexv)
    return hue_name(rgb) if rgb else None


def score_params(op, exp, base_ir, node):
    cat = exp["op"]
    p = exp["params"]
    if cat == "create":
        comps = op.get("components") or []
        have = [(c.get("type"), nrm(c.get("label"))) for c in comps]
        return all(any(t == w["type"] and nrm(w["label"]) in l for t, l in have) for w in p["components"])
    if cat == "add":
        c = op.get("component") or {}
        ok = c.get("type") == p["component"]["type"] or type_compat(p["component"]["type"], c.get("type"))
        ok = ok and nrm(p["component"]["label"]) in nrm(c.get("label"))
        if p.get("relation"):
            ok = ok and (op.get("position") or {}).get("relation") == p["relation"]
        return ok
    if cat == "remove":
        return None
    if cat == "modify":
        ch = op.get("changes") or {}
        if "label" in p:
            return nrm(p["label"]) == nrm(ch.get("label")) or nrm(p["label"]) in nrm(ch.get("label"))
        if "props" in p:
            got = ch.get("props") or {}
            return all(nrm(v) in nrm(got.get(k)) for k, v in p["props"].items())
    if cat == "move":
        pos = op.get("position") or {}
        if pos.get("relation") != p["relation"]:
            # "to the top of the form, above X" and "first" express the same final order
            if not (p["relation"] == "above" and pos.get("relation") == "first"):
                return False
        anchor = _node_by_ref(base_ir, pos.get("anchor"))
        if pos.get("relation") == "first":
            return True
        return anchor is not None and nrm(p["anchor"]).split()[0] in nrm(anchor.get("label"))
    if cat == "resize":
        st = _style(op)
        scale = op.get("scale") or (op.get("changes") or {}).get("scale")
        inc = p["direction"] == "increase"
        if scale:
            return (float(scale) > 1) == inc
        cur = (node or {}).get("style", {}) if node else {}
        if "size" in st:
            order = {"xs": 0, "sm": 1, "md": 2, "lg": 3, "xl": 4}
            return (order.get(st["size"], 2) > order.get(cur.get("size", "md"), 2)) == inc
        if st.get("width") == "full":
            return inc
        for k in ("width", "height", "fontSize"):
            if isinstance(st.get(k), (int, float)):
                if isinstance(cur.get(k), (int, float)):
                    return (st[k] > cur[k]) == inc
                return True   # absolute value without a previous one: direction not determinable from IR
        return False
    if cat == "style":
        st = _style(op)
        want_key, want_val = next(iter(p.items()))
        want_hue = color_hue(want_val.replace("dark ", "")) if want_val not in ("black",) else "black"
        got = [color_hue(st.get(k)) for k in ("color", "bg", "textColor") if st.get(k)]
        return want_hue in got
    if cat == "interaction":
        ev = op.get("event") or {}
        acts = ev.get("actions") or []
        if (ev.get("on") or "click") != "click":
            return False
        for a in acts:
            if a.get("type") != p["action"]:
                continue
            if p["action"] == "show_message":
                if nrm(p["text"]) in nrm(a.get("text")):
                    return True
            elif p["action"] == "validate_format":
                if a.get("format") == p["format"]:
                    return True
            else:
                return True
        return False
    if cat == "navigation":
        pg = op.get("page") or {}
        name = pg.get("name") if isinstance(pg, dict) else pg
        if not name:   # also accept an interaction op carrying a navigate action
            for a in (op.get("event") or {}).get("actions") or []:
                if a.get("type") == "navigate":
                    name = a.get("page")
        return nrm(p["page"]) == nrm(name) or nrm(p["page"]) in nrm(name)
    return False


def score_interpretation(cmd: dict, ops: list[dict] | None, base_ir: dict | None) -> dict:
    exp = cmd["expected"]
    ops = ops or []
    want = exp["op"]
    cands = [o for o in ops if (o.get("op") or "").lower() == want]
    # "navigation" is also expressed by some interpreters as an interaction with a navigate action
    if not cands and want == "navigation":
        cands = [o for o in ops if (o.get("op") or "").lower() == "interaction"
                 and any(a.get("type") == "navigate" for a in (o.get("event") or {}).get("actions") or [])]
        op_ok = False
    else:
        op_ok = bool(cands)
    best = None
    for o in (cands or ops[:1]):
        if want == "create":
            t_ok, node = None, None
        else:
            ref = (o.get("position") or {}).get("anchor") if want == "add" else o.get("target")
            lab = exp["params"].get("anchor") if want == "add" else exp["target_label"]
            ty = None if want == "add" else exp["target_type"]
            node = _node_by_ref(base_ir, ref, ty)
            t_ok = _label_ok(node, lab, ty)
        tnode = _node_by_ref(base_ir, o.get("target"), exp.get("target_type")) if want not in ("create", "add") else None
        try:
            p_ok = score_params(o, exp, base_ir, tnode)
        except Exception:  # noqa: BLE001 - malformed op = wrong params
            p_ok = False
        cand = {"op_ok": op_ok, "target_ok": t_ok, "params_ok": p_ok, "op_found": o.get("op"),
                "target_found": (node or {}).get("label") if node else None}
        cand["all_ok"] = bool(op_ok) and t_ok is not False and p_ok is not False
        if best is None or (cand["all_ok"], cand["target_ok"] is not False, cand["params_ok"] is not False) > \
                (best["all_ok"], best["target_ok"] is not False, best["params_ok"] is not False):
            best = cand
    if best is None:
        best = {"op_ok": False, "target_ok": False if want != "create" else None,
                "params_ok": False if want != "remove" else None, "all_ok": False, "op_found": None,
                "target_found": None}
    best["n_ops"] = len(ops)
    return best


_WER_TX = jiwer.Compose([jiwer.ToLowerCase(), jiwer.RemovePunctuation(), jiwer.RemoveMultipleSpaces(),
                         jiwer.Strip(), jiwer.ReduceToListOfListOfWords()])


def wer(ref: str, hyp: str) -> dict:
    o = jiwer.process_words(ref, hyp, reference_transform=_WER_TX, hypothesis_transform=_WER_TX)
    n = o.hits + o.substitutions + o.deletions
    return {"wer": o.wer, "S": o.substitutions, "D": o.deletions, "I": o.insertions, "N": n}
