"""Fault-injection experiment for the validate -> repair loop (metric 7b).

For a clean IR (+ the analysis it came from), inject exactly one fault, then:
  detected   validate(faulty) has at least one failing check that the clean UI did not have
  localised  one of those new failing checks targets the faulted node
  repaired   repair_loop(faulty) ends with no failing check beyond the clean UI's failures AND the
             fault-specific condition is restored (node back / visible / sized / order / handler)

Fault types (one node chosen with a deterministic RNG per sketch and fault type):
  delete_node   remove a leaf component that came from the sketch (has a bbox)
  hide_node     style.hidden = true on a leaf
  zero_size     style.width = 0 and style.height = 0 on a leaf
  swap_order    swap two vertically-stacked siblings in a column container
  break_event   point one event action at a node/page that does not exist (pipeline IRs; needs events)
  code_error    inject `throw` into the compiled preview's App (detection only: repair recompiles from IR)
"""
from __future__ import annotations

import copy
import logging
import random

import common  # noqa: F401
from app.pipeline import codegen, ir as irm

log = logging.getLogger("eval.faults")

LEAF_SKIP = {"page", "container", "card", "form", "header", "navbar", "list"}
FAULTS = ["delete_node", "hide_node", "zero_size", "swap_order", "break_event", "code_error"]


def _leaves(ir):
    return [(n, p) for n, p, _ in irm.walk(ir) if n["type"] not in LEAF_SKIP and p is not None
            and n.get("bbox") and not irm.is_hidden(ir, n["id"])]


def inject(ir: dict, kind: str, rng: random.Random):
    """Return (faulty_ir, info) or (None, reason)."""
    ir = copy.deepcopy(ir)
    if kind in ("delete_node", "hide_node", "zero_size"):
        leaves = _leaves(ir)
        if not leaves:
            return None, "no leaf"
        node, parent = rng.choice(leaves)
        info = {"target": node["id"], "type": node["type"], "label": node.get("label", "")}
        if kind == "delete_node":
            parent["children"] = [c for c in parent["children"] if c["id"] != node["id"]]
        elif kind == "hide_node":
            node.setdefault("style", {})["hidden"] = True
        else:
            node.setdefault("style", {}).update({"width": 0, "height": 0})
        return ir, info
    if kind == "swap_order":
        opts = []
        for n, _, _ in irm.walk(ir):
            if n.get("layout", {}).get("direction") == "column":
                kids = [c for c in n.get("children", []) if c.get("bbox")]
                for a, b in zip(kids, kids[1:]):
                    if b["bbox"]["y"] > a["bbox"]["y"] + a["bbox"]["h"] * 0.5:
                        opts.append((n, a["id"], b["id"]))
        if not opts:
            return None, "no stacked siblings"
        cont, a, b = rng.choice(opts)
        ch = cont["children"]
        ia = next(i for i, c in enumerate(ch) if c["id"] == a)
        ib = next(i for i, c in enumerate(ch) if c["id"] == b)
        ch[ia], ch[ib] = ch[ib], ch[ia]
        return ir, {"target": a, "other": b}
    if kind == "break_event":
        evs = [(n, e, a) for n, _, _ in irm.walk(ir) for e in n.get("events", []) for a in e.get("actions", [])]
        if not evs:
            return None, "no events"
        n, e, a = rng.choice(evs)
        if a.get("type") == "navigate":
            a["page"] = "page_missing_injected"
        elif a.get("type") == "validate_required":
            a["targets"] = ["inp_missing_injected"]
        elif "target" in a:
            a["target"] = "node_missing_injected"
        else:
            a["type"] = "navigate"
            a["page"] = "page_missing_injected"
        return ir, {"target": n["id"], "action": a.get("type")}
    raise ValueError(kind)


def _failed(report):
    return {c["id"] for c in report.get("checks", []) if not c.get("ok")}


def _restored(kind, info, clean_ir, final_ir):
    if kind == "delete_node":
        return any(n["type"] == info["type"] and n.get("label", "") == info["label"]
                   and not irm.is_hidden(final_ir, n["id"]) for n, _, _ in irm.walk(final_ir))
    node, _, _ = irm.find(final_ir, info["target"])
    if node is None:
        return False
    if kind == "hide_node":
        return not irm.is_hidden(final_ir, info["target"])
    if kind == "zero_size":
        st = node.get("style", {})
        return st.get("width") != 0 and st.get("height") != 0
    if kind == "swap_order":
        def order(ir):
            seq = [n["id"] for n, _, _ in irm.walk(ir)]
            return seq.index(info["target"]) < seq.index(info["other"]) if info["other"] in seq else None
        return order(final_ir) == order(clean_ir)
    if kind == "break_event":
        return True   # judged by "no new failing checks"
    return False


def run_case(ir, analysis, kind, seed, validate, repair, snapshot=False):
    """snapshot=True also gives validate/repair the clean IR as `reference` (the previous version of the UI)."""
    ref = ir if snapshot else None
    rng = random.Random(seed)
    clean_code = codegen.generate_code(ir)
    clean = validate.strip_screenshot(validate.validate(ir, clean_code["preview"], analysis))
    base_fail = _failed(clean)
    rec = {"fault": kind, "clean_passed": clean["passed"]}
    if kind == "code_error":
        prev = clean_code["preview"]
        marker = "function App("
        i = prev.find(marker)
        if i < 0:
            return {**rec, "applicable": False, "reason": "no App function"}
        j = prev.find("{", i) + 1
        bad = prev[:j] + '\n  throw new Error("injected fault");\n' + prev[j:]
        rep = validate.strip_screenshot(validate.validate(ir, bad, analysis))
        new = _failed(rep) - base_fail
        return {**rec, "applicable": True, "detected": bool(new) or (clean["passed"] and not rep["passed"]),
                "localised": any(x.startswith("runtime") or "error" in x for x in new), "repaired": None,
                "new_failures": sorted(new)[:8]}
    faulty, info = inject(ir, kind, rng)
    if faulty is None:
        return {**rec, "applicable": False, "reason": info}
    code = codegen.generate_code(faulty)
    rep = validate.strip_screenshot(validate.validate(faulty, code["preview"], analysis, ref) if snapshot
                                     else validate.validate(faulty, code["preview"], analysis))
    new = _failed(rep) - base_fail
    comps = (analysis or {}).get("components") or []

    def points_at_fault(c):
        if c.get("target") == info["target"]:
            return True
        # a deleted node is reported against the sketch component it should come from: coverage:<index>
        if kind == "delete_node" and c["id"].startswith("coverage:"):
            try:
                a = comps[int(c["id"].split(":")[1])]
            except (ValueError, IndexError):
                return False
            return a.get("type") == info["type"] and (a.get("label") or "") == info["label"]
        return False
    rec.update({"applicable": True, "info": info, "detected": bool(new),
                "localised": any(points_at_fault(c) for c in rep["checks"] if not c.get("ok") and c["id"] in new),
                "new_failures": sorted(new)[:8]})
    rl = repair.repair_loop(copy.deepcopy(faulty), analysis, max_iter=3, reference=ref) if snapshot \
        else repair.repair_loop(copy.deepcopy(faulty), analysis, max_iter=3)
    final = validate.strip_screenshot(rl["report"])
    remaining = _failed(final) - base_fail
    rec["repaired"] = (not remaining) and _restored(kind, info, ir, rl["ir"])
    rec["repairs"] = [{k: r.get(k) for k in ("iteration", "check", "target", "action", "result")} for r in rl.get("repairs", [])]
    rec["remaining_new_failures"] = sorted(remaining)[:8]
    return rec
