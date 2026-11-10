"""Phase A: run the systems under test and cache every raw output.

pipeline (proposed): analyze_sketch (cv | vision | hybrid) -> intent.parse_commands(instruction)
                     -> fusion.fuse -> codegen.generate_code -> validate -> repair_loop
baseline (RR-04):    baseline.baseline_generate(sketch, instruction)   (one vision call -> full React code)
oracle (reference):  ground-truth labels as a perfect SketchAnalysis -> fuse -> generate_code (no API);
                     an upper bound for the deterministic back half of the pipeline.
commands:            speech.transcribe(audio), intent.parse_commands(text | transcript, base IR),
                     refine.apply_ops + generate_code  vs  baseline.baseline_modify(base code, text)

All API results go through RawCache (results/<run>/raw/<stage>/<id>.json, with wall time), so metric
re-runs on the same run directory make no API calls. Local deterministic stages are timed here too.
"""
from __future__ import annotations

import copy
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import common  # noqa: F401  (sys.path)
from app.pipeline import codegen, fusion, ir as irm, refine, sketch

log = logging.getLogger("eval.gen")


def _imp(name):
    import importlib
    return importlib.import_module(f"app.pipeline.{name}")


def gt_analysis(lab: dict) -> dict:
    """Ground-truth labels in SketchAnalysis form (perfect detection)."""
    return {"components": [{"type": c["type"], "label": c["label"], "bbox": c["bbox"], "confidence": 1.0,
                            "source": "gt", "parent": c["parent"]} for c in lab["components"]],
            "width": lab["width"], "height": lab["height"], "mode": "gt",
            "timings": {"cv_ms": 0, "vision_ms": 0, "total_ms": 0}}


def _ms(t0):
    return round((time.perf_counter() - t0) * 1000, 1)


def strip_analysis(a: dict) -> dict:
    return {k: v for k, v in a.items() if k not in ("overlay_png_b64", "cv_candidates")} | \
        {"n_cv_candidates": a["cv_candidates"] if isinstance(a.get("cv_candidates"), int)
         else len(a.get("cv_candidates") or [])}


# ------------------------------------------------------------------ per sketch

def analyses(lab, cache, modes):
    img = Path(lab["image_path"]).read_bytes()
    out = {}
    for mode in modes:
        out[mode] = cache.call(f"analyze_{mode}", lab["id"],
                               lambda m=mode: strip_analysis(sketch.analyze_sketch(img, mode=m, overlay=False)),
                               api_calls=0 if mode == "cv" else 1)
    return out


def interpret_instruction(lab, cache):
    intent = _imp("intent")
    return cache.call("interpret_instruction", lab["id"], lambda: intent.parse_commands(lab["instruction"], None))


def baseline_generate(lab, cache):
    baseline = _imp("baseline")
    img = Path(lab["image_path"]).read_bytes()
    return cache.call("baseline_generate", lab["id"], lambda: baseline.baseline_generate(img, lab["instruction"]))


def build_pipeline(lab, analysis_rec, ops_rec, cache):
    """Deterministic back half + validation + repair (local, Playwright). Cached as 'pipeline_build'."""
    def run():
        validate = _imp("validate")
        repair = _imp("repair")
        an = analysis_rec["value"]
        ops = ops_rec["value"]["ops"]
        t = {}
        t0 = time.perf_counter()
        ir = fusion.fuse(an, ops, title=lab["title"])
        t["fuse"] = _ms(t0)
        t0 = time.perf_counter()
        code = codegen.generate_code(ir)
        t["codegen"] = _ms(t0)
        t0 = time.perf_counter()
        rep0 = validate.strip_screenshot(validate.validate(ir, code["preview"], an))
        t["validate"] = _ms(t0)
        t0 = time.perf_counter()
        rl = repair.repair_loop(copy.deepcopy(ir), an, max_iter=3)
        t["repair"] = _ms(t0)
        final_code = rl.get("code") or codegen.generate_code(rl["ir"])
        return {"ir0": ir, "code0": code, "report0": rep0, "ir": rl["ir"], "code": final_code,
                "report": validate.strip_screenshot(rl["report"]), "repairs": rl.get("repairs", []), "timings": t}
    return cache.call("pipeline_build", lab["id"], run, api_calls=0)


def build_oracle(lab, cache):
    def run():
        t0 = time.perf_counter()
        an = gt_analysis(lab)
        ir = fusion.fuse(an, [], title=lab["title"])
        code = codegen.generate_code(ir)
        return {"ir": ir, "code": code, "analysis": an, "ms": _ms(t0)}
    return cache.call("oracle_build", lab["id"], run, api_calls=0)


# ------------------------------------------------------------------ per command

def transcribe(cmd, cache):
    speech = _imp("speech")
    audio = Path(cmd["audio_path"]).read_bytes()
    return cache.call("transcribe", cmd["id"], lambda: speech.transcribe(audio, Path(cmd["audio_path"]).name))


def interpret_cmd(cmd, text, base_ir, cache, stage):
    intent = _imp("intent")
    return cache.call(stage, cmd["id"], lambda: intent.parse_commands(text, copy.deepcopy(base_ir) if base_ir else None))


def baseline_modify(cmd, base_preview, cache):
    baseline = _imp("baseline")
    return cache.call("baseline_modify", cmd["id"], lambda: baseline.baseline_modify(base_preview, cmd["text"]))


def apply_pipeline(base_ir, ops, title):
    """Refinement path of the proposed system: pure IR edit + recompile (no LLM)."""
    t0 = time.perf_counter()
    if base_ir is None:
        ir = fusion.fuse(None, ops, title=title)
        changes = [{"op": "create", "ok": True}]
    else:
        res = refine.apply_ops(base_ir, ops)
        ir, changes = res["ir"], res["changes"]
    t_apply = _ms(t0)
    t0 = time.perf_counter()
    code = codegen.generate_code(ir)
    return {"ir": ir, "code": code, "changes": changes, "timings": {"apply": t_apply, "codegen": _ms(t0)}}


def empty_preview():
    return codegen.generate_code(irm.new_ir("Untitled"))["preview"]


# ------------------------------------------------------------------ phase driver

def run_phase_a(sketches, commands, cache, args):
    """Run all API-backed stages (parallel, bounded) then local pipeline builds."""
    workers = args.workers
    modes = [m for m in ("cv", "vision", "hybrid") if m in args.modes]
    gen = {lab["id"]: {} for lab in sketches}

    def per_sketch(lab):
        r = gen[lab["id"]]
        r["analysis"] = analyses(lab, cache, modes)
        if not args.skip_pipeline:
            r["ops"] = interpret_instruction(lab, cache)
        if not args.skip_baseline:
            r["baseline"] = baseline_generate(lab, cache)
        return lab["id"]

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(per_sketch, lab) for lab in sketches]
        for i, f in enumerate(as_completed(futs), 1):
            log.info("generation API stages %d/%d done (%s)", i, len(futs), f.result())

    for lab in sketches:
        r = gen[lab["id"]]
        r["oracle"] = build_oracle(lab, cache)
        if not args.skip_pipeline and r["analysis"].get("hybrid", {}).get("_ok") and r["ops"].get("_ok"):
            r["pipeline"] = build_pipeline(lab, r["analysis"]["hybrid"], r["ops"], cache)
            log.info("pipeline build %s: ok=%s", lab["id"], r["pipeline"]["_ok"])
        else:
            r["pipeline"] = {"_ok": False, "_error": "upstream stage failed or skipped", "value": None}

    # commands
    cmd_out = {c["id"]: {} for c in commands}
    lab_by = {l["id"]: l for l in sketches}
    empty = empty_preview()

    def per_cmd(c):
        r = cmd_out[c["id"]]
        g = gen.get(c["sketch_id"], {})
        r["transcribe"] = transcribe(c, cache)
        base_ir = None
        if c["base"] != "empty":
            p = g.get("pipeline", {})
            base_ir = p["value"]["ir"] if p.get("_ok") else None
        if not args.skip_pipeline and (base_ir is not None or c["base"] == "empty"):
            r["ops_text"] = interpret_cmd(c, c["text"], base_ir, cache, "interpret_cmd_text")
            if r["transcribe"].get("_ok"):
                r["ops_asr"] = interpret_cmd(c, r["transcribe"]["value"]["text"], base_ir, cache, "interpret_cmd_asr")
        if not args.skip_baseline:
            if c["base"] == "empty":
                base_prev = empty
            else:
                b = g.get("baseline", {})
                base_prev = b["value"]["preview"] if b.get("_ok") else None
            if base_prev:
                r["baseline"] = baseline_modify(c, base_prev, cache)
        return c["id"]

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(per_cmd, c) for c in commands]
        for i, f in enumerate(as_completed(futs), 1):
            if i % 10 == 0 or i == len(futs):
                log.info("command API stages %d/%d", i, len(futs))

    for c in commands:
        r = cmd_out[c["id"]]
        g = gen.get(c["sketch_id"], {})
        base_ir = None if c["base"] == "empty" else (g.get("pipeline", {}).get("value") or {}).get("ir")
        lab = lab_by.get(c["sketch_id"])
        for src in ("text", "asr"):
            o = r.get(f"ops_{src}")
            if o and o.get("_ok") and (base_ir is not None or c["base"] == "empty"):
                try:
                    r[f"apply_{src}"] = apply_pipeline(copy.deepcopy(base_ir) if base_ir else None,
                                                       o["value"]["ops"], lab["title"] if lab else None)
                except Exception as e:  # noqa: BLE001 - recorded as a failed refinement
                    log.exception("apply_ops failed for %s (%s)", c["id"], src)
                    r[f"apply_{src}"] = {"error": f"{type(e).__name__}: {e}"}
    return gen, cmd_out, empty
