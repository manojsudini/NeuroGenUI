"""NeuroGenUI evaluation: run everything end to end and write results/<timestamp>/ (+ a copy in results/latest).

    python evaluation/run_all.py                       # full run (40 sketches, 80 commands, pipeline + baseline)
    python evaluation/run_all.py --limit 5             # 5 sketches (category round-robin) + their commands
    python evaluation/run_all.py --only login_01,dash  # sketch ids or categories
    python evaluation/run_all.py --skip-baseline       # proposed system only
    python evaluation/run_all.py --dataset holdout     # held-out set (dataset/holdout) -> results/<ts>-holdout/
    python evaluation/run_all.py --keyfree             # no API calls: cv detection, oracle UIs, fault injection
    python evaluation/run_all.py --run-dir results/20261101-1200   # reuse cached raw outputs, recompute metrics

See evaluation/README.md for the definition of every metric.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import RESULTS, RawCache, load_commands, load_sketches, setup_logging, write_json  # noqa: E402

log = logging.getLogger("eval")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", choices=["dev", "holdout"], default="dev",
                    help="dev = dataset/ (40 sketches, 80 commands); holdout = dataset/holdout/ (20 sketches, 30 commands)")
    ap.add_argument("--limit", type=int, help="number of sketches (balanced over categories)")
    ap.add_argument("--only", help="comma list of sketch ids / categories")
    ap.add_argument("--only-commands", help="comma list of command ids / command categories")
    ap.add_argument("--skip-baseline", action="store_true")
    ap.add_argument("--skip-pipeline", action="store_true", help="skip LLM pipeline stages (cv + oracle still run)")
    ap.add_argument("--skip-commands", action="store_true")
    ap.add_argument("--skip-faults", action="store_true")
    ap.add_argument("--keyfree", action="store_true", help="no API calls at all")
    ap.add_argument("--modes", default="cv,vision,hybrid")
    ap.add_argument("--workers", type=int, default=4, help="parallel API calls")
    ap.add_argument("--run-dir", help="existing run directory to reuse (raw cache)")
    ap.add_argument("--retry-errors", action="store_true", help="redo cached stages that failed")
    ap.add_argument("--no-latest", action="store_true", help="do not refresh results/latest")
    a = ap.parse_args(argv)
    a.modes = [m.strip() for m in a.modes.split(",") if m.strip()]
    if a.keyfree:
        a.skip_baseline = a.skip_pipeline = True
        a.modes = ["cv"]
    return a


# ====================================================================== phase helpers

def code_quality(items: list[dict]) -> dict:
    if not items:
        return {}
    p = subprocess.run(["node", str(common.EVAL / "tools" / "codequality.mjs")], input=json.dumps({"items": items}),
                       capture_output=True, text=True, cwd=str(common.EVAL), timeout=900)
    if p.returncode != 0:
        log.error("codequality.mjs failed: %s", p.stderr[-2000:])
        return {}
    return json.loads(p.stdout)["results"]


def safe(v, *path, default=None):
    for k in path:
        if v is None:
            return default
        v = v.get(k) if isinstance(v, dict) else None
    return default if v is None else v


def main(argv=None):
    args = parse_args(argv)
    common.set_dataset(args.dataset)
    suffix = "-holdout" if args.dataset == "holdout" else ""
    t_start = time.time()
    if args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.is_absolute():
            rel = Path(args.run_dir)
            run_dir = common.EVAL / rel if rel.parts[0] == "results" else RESULTS / rel
    else:
        run_dir = RESULTS / (datetime.now().strftime("%Y%m%d-%H%M%S") + suffix)
    setup_logging(run_dir)
    if not args.keyfree and not common.openai_configured():
        log.error("OPENAI_API_KEY missing in project/.env: use --keyfree for the key-free subset")
        return 2
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    sketches = load_sketches(only, args.limit)
    ids = {s["id"] for s in sketches}
    commands = [] if args.skip_commands else load_commands(ids, [s.strip() for s in args.only_commands.split(",")]
                                                            if args.only_commands else None)
    if args.keyfree:
        commands = []
    log.info("dataset=%s (%s)", args.dataset, common.DATASET)
    log.info("run dir %s | %d sketches, %d commands | baseline=%s pipeline=%s modes=%s",
             run_dir, len(sketches), len(commands), not args.skip_baseline, not args.skip_pipeline, args.modes)
    cache = RawCache(run_dir)
    cache.retry_errors = args.retry_errors

    from generate import run_phase_a
    from app.pipeline import validate as vmod
    t0 = time.time()
    gen, cmd_gen, empty_prev = run_phase_a(sketches, commands, cache, args)
    phase_a_s = time.time() - t0
    log.info("phase A (systems under test) done in %.1fs; cache hits=%d misses=%d", phase_a_s, cache.hits, cache.misses)

    rows = {k: [] for k in ("detection_analysis", "detection_dom", "detection_types", "visual", "functional",
                            "requirements", "voice", "refinement", "repair", "repair_actions", "faults", "timing",
                            "code_quality")}

    # ------------------------------------------------------------------ metric 1a: analysis-level detection
    from checks import match, prf
    for lab in sketches:
        for mode, rec in gen[lab["id"]]["analysis"].items():
            if not rec.get("_ok"):
                rows["detection_analysis"].append({"sketch": lab["id"], "category": lab["category"], "mode": mode,
                                                   "error": rec.get("_error")})
                continue
            an = rec["value"]
            m = match(lab["components"], an["components"])
            P, R, F = prf(m["tp_strict"], m["n_pred"], m["n_gt"])
            Pl, Rl, Fl = prf(m["tp_lenient"], m["n_pred"], m["n_gt"])
            rows["detection_analysis"].append({
                "sketch": lab["id"], "category": lab["category"], "mode": mode, "n_gt": m["n_gt"],
                "n_pred": m["n_pred"], "matched": m["matched"], "tp": m["tp_strict"], "tp_lenient": m["tp_lenient"],
                "precision": P, "recall": R, "f1": F, "precision_lenient": Pl, "recall_lenient": Rl, "f1_lenient": Fl,
                "loc_recall": m["matched"] / m["n_gt"] if m["n_gt"] else 0,
                "type_acc": m["tp_strict"] / m["matched"] if m["matched"] else None,
                "type_acc_lenient": m["tp_lenient"] / m["matched"] if m["matched"] else None,
                "mean_iou": m["iou_sum"] / m["matched"] if m["matched"] else None,
                "label_acc": _label_acc(lab, an, m),
                "analysis_ms": safe(an, "timings", "total_ms"), "wall_ms": rec.get("_wall_ms")})
            for i, g in enumerate(lab["components"]):
                pr = next((p for p in m["pairs"] if p["gt"] == i), None)
                rows["detection_types"].append({"mode": mode, "sketch": lab["id"], "gt_type": g["type"],
                                                "matched": pr is not None, "type_ok": bool(pr and pr["type_strict"]),
                                                "pred_type": pr["pred_type"] if pr else ""})

    # ------------------------------------------------------------------ pipeline repair + timing rows
    for lab in sketches:
        g = gen[lab["id"]]
        p = g.get("pipeline", {})
        if p.get("_ok"):
            v = p["value"]
            rows["repair"].append({"sketch": lab["id"], "category": lab["category"],
                                   "passed_before": v["report0"]["passed"], "passed_after": v["report"]["passed"],
                                   "score_before": v["report0"]["score"], "score_after": v["report"]["score"],
                                   "failed_before": sum(not c["ok"] for c in v["report0"]["checks"]),
                                   "failed_after": sum(not c["ok"] for c in v["report"]["checks"]),
                                   "n_repairs": len(v["repairs"])})
            for r in v["repairs"]:
                rows["repair_actions"].append({"sketch": lab["id"], "iteration": r.get("iteration"),
                                               "check": r.get("check"), "target": r.get("target"),
                                               "action": r.get("action"), "result": r.get("result")})
            an = g["analysis"]["hybrid"]
            ops = g["ops"]
            t = {"analyze_sketch": an["_wall_ms"], "interpret": ops["_wall_ms"], **v["timings"]}
            for st, ms in t.items():
                rows["timing"].append({"sketch": lab["id"], "system": "pipeline", "stage": st, "ms": ms})
            core = t["analyze_sketch"] + t["interpret"] + t["fuse"] + t["codegen"]
            rows["timing"].append({"sketch": lab["id"], "system": "pipeline", "stage": "total_generate", "ms": core})
            rows["timing"].append({"sketch": lab["id"], "system": "pipeline", "stage": "total_with_validation",
                                   "ms": core + t["validate"] + t["repair"]})
        b = g.get("baseline")
        if b and b.get("_ok"):
            rows["timing"].append({"sketch": lab["id"], "system": "baseline", "stage": "baseline_generate",
                                   "ms": b["_wall_ms"]})
            rows["timing"].append({"sketch": lab["id"], "system": "baseline", "stage": "total_generate",
                                   "ms": b["_wall_ms"]})
        for mode, rec in g["analysis"].items():
            if rec.get("_ok"):
                rows["timing"].append({"sketch": lab["id"], "system": f"analyze_{mode}", "stage": f"analyze_{mode}",
                                       "ms": rec["_wall_ms"]})

    # ------------------------------------------------------------------ metric 7b: fault injection (backend validator)
    if not args.skip_faults:
        from faults import FAULTS, run_case
        repair = __import__("importlib").import_module("app.pipeline.repair") if _has("repair") else None
        if repair is None:
            log.warning("repair.py missing: fault injection skipped")
        else:
            fi_path = run_dir / "raw" / "faults.json"
            fi = json.loads(fi_path.read_text()) if fi_path.exists() else {}
            for lab in sketches:
                g = gen[lab["id"]]
                sources = {"oracle": (g["oracle"]["value"]["ir"], g["oracle"]["value"]["analysis"])}
                if g.get("pipeline", {}).get("_ok"):
                    sources["pipeline"] = (g["pipeline"]["value"]["ir"], g["analysis"]["hybrid"]["value"])
                # "+snapshot" sources: the same faults, but validate/repair also get the clean IR as the previous version
                for name in list(sources):
                    sources[f"{name}+snapshot"] = sources[name]
                for src, (ir, an) in sources.items():
                    snap = src.endswith("+snapshot")
                    for k, fault in enumerate(["delete_node", "hide_node"] if snap else FAULTS):
                        key = f"{src}:{lab['id']}:{fault}"
                        if key not in fi:
                            try:
                                fi[key] = run_case(ir, an, fault, seed=_seed(lab["id"], fault), validate=vmod, repair=repair,
                                                   snapshot=snap)
                            except Exception as e:  # noqa: BLE001
                                log.exception("fault case %s failed", key)
                                fi[key] = {"fault": fault, "applicable": False, "reason": f"error: {e}"}
                        rows["faults"].append({"source": src, "sketch": lab["id"], **{
                            x: fi[key].get(x) for x in ("fault", "applicable", "clean_passed", "detected", "localised",
                                                        "repaired", "reason")},
                            "n_repairs": len(fi[key].get("repairs") or []),
                            "repair_actions": ";".join(sorted({r.get("action") or "" for r in fi[key].get("repairs") or []}))})
                write_json(fi_path, fi)
            log.info("fault injection: %d cases", len(rows["faults"]))

    # ------------------------------------------------------------------ browser measurements
    from dom import Renderer
    from measure import detection_from_dom, measure_command, measure_sketch
    from checks import prf as _prf
    renderer = Renderer()
    shots = run_dir / "shots"
    sys_codes = {}
    try:
        for i, lab in enumerate(sketches, 1):
            g = gen[lab["id"]]
            codes = {"oracle": g["oracle"]["value"]["code"]["preview"]}
            if g.get("pipeline", {}).get("_ok"):
                codes["pipeline"] = g["pipeline"]["value"]["code"]["preview"]
                codes["pipeline_norepair"] = g["pipeline"]["value"]["code0"]["preview"]
            if g.get("baseline", {}).get("_ok"):
                codes["baseline"] = g["baseline"]["value"]["preview"]
            sys_codes[lab["id"]] = codes
            res = measure_sketch(lab, codes, renderer, shots)
            # systems that failed to generate this UI are scored as failures, not dropped
            expected_sys = ([] if args.skip_pipeline else ["pipeline"]) + ([] if args.skip_baseline else ["baseline"])
            for sysname in expected_sys:
                if sysname in codes:
                    continue
                err = safe(g, sysname, "_error") or "no output"
                log.warning("%s produced no UI for %s: %s", sysname, lab["id"], err)
                n_gt = len(lab["components"])
                rows["detection_dom"].append({"sketch": lab["id"], "category": lab["category"], "system": sysname,
                                              "n_gt": n_gt, "n_pred": 0, "matched": 0, "tp": 0, "precision": 0.0,
                                              "recall": 0.0, "f1": 0.0, "f1_lenient": 0.0, "type_acc": None,
                                              "mean_iou": None, "failed": err})
                rows["visual"].append({"sketch": lab["id"], "category": lab["category"], "system": sysname,
                                       "layout_iou": 0.0, "ssim_edges": None, "render_ok": False,
                                       "runtime_errors": 0, "n_elements": 0, "failed": err})
                for it in lab["interactions"]:
                    rows["functional"].append({"sketch": lab["id"], "category": lab["category"], "system": sysname,
                                               "target": it["target_label"], "expect": it["expect"].get("type"),
                                               "passed": False, "detail": "system produced no UI"})
                for q in lab["requirements"]:
                    rows["requirements"].append({"sketch": lab["id"], "category": lab["category"], "system": sysname,
                                                 "kind": q["kind"], "what": q.get("label_contains") or q.get("target_label")
                                                 or q.get("type"), "passed": False, "detail": "system produced no UI"})
            for sysname, r in res.items():
                if not r.get("available"):
                    continue
                d = r["det"]
                P, R, F = _prf(d["tp_strict"], d["n_pred"], d["n_gt"])
                Pl, Rl, Fl = _prf(d["tp_lenient"], d["n_pred"], d["n_gt"])
                rows["detection_dom"].append({"sketch": lab["id"], "category": lab["category"], "system": sysname,
                                              **{k: d[k] for k in ("n_gt", "n_pred", "matched")}, "tp": d["tp_strict"],
                                              "precision": P, "recall": R, "f1": F, "f1_lenient": Fl,
                                              "type_acc": d["tp_strict"] / d["matched"] if d["matched"] else None,
                                              "mean_iou": d["iou_sum"] / d["matched"] if d["matched"] else None})
                rows["visual"].append({"sketch": lab["id"], "category": lab["category"], "system": sysname,
                                       "layout_iou": r["layout_iou"], "ssim_edges": r["ssim_edges"],
                                       "render_ok": r["render_ok"], "runtime_errors": len(r["runtime_errors"]),
                                       "n_elements": r["n_elements"]})
                for it in r["interactions"]:
                    rows["functional"].append({"sketch": lab["id"], "category": lab["category"], "system": sysname,
                                               "target": it["target"], "expect": it["expect"].get("type"),
                                               "passed": it["passed"], "detail": it["detail"]})
                for q in r["requirements"]:
                    rows["requirements"].append({"sketch": lab["id"], "category": lab["category"], "system": sysname,
                                                 "kind": q["req"]["kind"],
                                                 "what": q["req"].get("label_contains") or q["req"].get("target_label")
                                                 or q["req"].get("type"), "passed": q["passed"], "detail": q["detail"]})
            log.info("measured sketch %d/%d %s: %s", i, len(sketches), lab["id"],
                     {k: (round(v["layout_iou"], 2), sum(x["passed"] for x in v["interactions"]))
                      for k, v in res.items() if v.get("available")})

        # -------------------------------------------------------------- commands
        from scoring import score_interpretation, wer
        snaps = {}
        lab_by = {l["id"]: l for l in sketches}
        for i, c in enumerate(commands, 1):
            r = cmd_gen[c["id"]]
            g = gen.get(c["sketch_id"], {})
            lab = lab_by[c["sketch_id"]]
            base_ir = None if c["base"] == "empty" else safe(g, "pipeline", "value", "ir")
            row = {"id": c["id"], "category": c["category"], "sketch": c["sketch_id"], "text": c["text"],
                   "brief_example": c["brief_example"], "voice": safe(c, "tts", "voice")}
            tr = r.get("transcribe") or {}
            if tr.get("_ok"):
                hyp = tr["value"]["text"]
                w = wer(c["text"], hyp)
                row.update({"transcript": hyp, "wer": w["wer"], "wer_S": w["S"], "wer_D": w["D"], "wer_I": w["I"],
                            "wer_N": w["N"], "stt_ms": tr["_wall_ms"]})
            for src in ("text", "asr"):
                o = r.get(f"ops_{src}")
                if o and o.get("_ok"):
                    s = score_interpretation(c, o["value"]["ops"], base_ir)
                    row.update({f"{src}_{k}": s[k] for k in ("op_ok", "target_ok", "params_ok", "all_ok", "op_found",
                                                             "target_found", "n_ops")})
                    row[f"{src}_interpret_ms"] = o["_wall_ms"]
                elif o:
                    row[f"{src}_error"] = o.get("_error")
            rows["voice"].append(row)

            # refinement
            # recompile the base IR here so before/after come from the same compiler build
            before_p = None if base_ir is None else _compile(base_ir)
            before_b = empty_prev if c["base"] == "empty" else safe(g, "baseline", "value", "preview")
            if c["base"] == "empty":
                before_p = empty_prev
            variants = []
            # a system that failed earlier (no base UI, failed call) still gets a row: it counts as a failure
            if not args.skip_pipeline:
                for src, name in (("text", "pipeline"), ("asr", "pipeline_voice")):
                    ap_ = r.get(f"apply_{src}")
                    o = r.get(f"ops_{src}") or {}
                    after = safe(ap_, "code", "preview") if ap_ and "error" not in ap_ else None
                    ms = (o.get("_wall_ms") or 0) + sum((ap_ or {}).get("timings", {}).values()) if o.get("_ok") else None
                    variants.append((name, before_p, after, ms))
            if not args.skip_baseline:
                b = r.get("baseline") or {}
                variants.append(("baseline", before_b, safe(b, "value", "preview") if b.get("_ok") else None,
                                 b.get("_wall_ms") if b.get("_ok") else None))
            for name, before, after, ms in variants:
                m = measure_command(c, before, after, renderer, lab["height"], snaps)
                pres = m.get("preservation") or {}
                rows["refinement"].append({"id": c["id"], "category": c["category"], "sketch": c["sketch_id"],
                                           "system": name, "available": m["available"], "passed": m["passed"],
                                           "detail": m["detail"], "render_ok": m.get("render_ok"),
                                           "pre_satisfied": m.get("pre_satisfied"),
                                           "preservation": pres.get("rate"), "preserved_n": pres.get("kept"),
                                           "considered_n": pres.get("n"),
                                           "changed": ";".join(pres.get("changed") or []), "latency_ms": ms})
                if ms is not None:
                    rows["timing"].append({"sketch": c["id"], "system": name, "stage": "modify_total", "ms": ms})
            if i % 10 == 0 or i == len(commands):
                log.info("measured commands %d/%d", i, len(commands))
    finally:
        renderer.close()

    # ------------------------------------------------------------------ metric 9: code quality
    items = []
    for lab in sketches:
        g = gen[lab["id"]]
        for name, code in sys_codes.get(lab["id"], {}).items():
            if name == "pipeline_norepair":
                continue
            items.append({"key": f"{name}|preview|{lab['id']}", "files": {"preview.jsx": code}})
        if g.get("pipeline", {}).get("_ok"):
            files = {k: v for k, v in g["pipeline"]["value"]["code"]["files"].items() if k.endswith((".js", ".jsx"))}
            items.append({"key": f"pipeline|project|{lab['id']}", "files": files})
    cq = code_quality(items)
    for key, m in cq.items():
        sysname, form, sid = key.split("|")
        rows["code_quality"].append({"sketch": sid, "system": sysname, "form": form,
                                     **{k: m[k] for k in ("parses", "loc", "components", "usages", "reuse_ratio",
                                                          "max_fn_lines", "functions", "eslint_warnings", "files")},
                                     "eslint_top_rules": ";".join(f"{r}:{n}" for r, n in sorted(
                                         m["eslint_by_rule"].items(), key=lambda x: -x[1])[:4]),
                                     "parse_errors": ";".join(m["parse_errors"])[:300]})

    try:
        vmod.shutdown()
    except Exception:  # noqa: BLE001
        pass

    # ------------------------------------------------------------------ report
    from report import build_report
    meta = {"started": datetime.fromtimestamp(t_start).isoformat(timespec="seconds"),
            "duration_s": round(time.time() - t_start, 1), "phase_a_s": round(phase_a_s, 1),
            "api_calls_made_this_invocation": cache.api_calls, "cache_hits": cache.hits,
            "cache_misses": cache.misses, "args": vars(args), "n_sketches": len(sketches),
            "n_commands": len(commands), "api_calls_total_in_raw": _count_api_calls(run_dir)}
    build_report(run_dir, rows, meta, sketches, commands)
    if not args.no_latest:
        latest = RESULTS / ("latest-holdout" if args.dataset == "holdout" else "latest")
        if latest.exists():
            shutil.rmtree(latest)
        shutil.copytree(run_dir, latest, ignore=shutil.ignore_patterns("raw"))
    log.info("done in %.1f min -> %s", (time.time() - t_start) / 60, run_dir)
    return 0


_COMPILED = {}


def _compile(ir):
    from app.pipeline import codegen
    key = json.dumps(ir, sort_keys=True)
    if key not in _COMPILED:
        _COMPILED[key] = codegen.generate_code(ir)["preview"]
    return _COMPILED[key]


def _seed(sid, fault):
    import hashlib
    return int(hashlib.sha256(f"{sid}:{fault}".encode()).hexdigest()[:8], 16)


def _has(mod):
    return (common.BACKEND / "app" / "pipeline" / f"{mod}.py").exists()


def _label_acc(lab, an, m):
    """Among type-correct matches whose GT label is non-empty: predicted label equals GT label (normalised)."""
    from dom import norm
    pairs = [p for p in m["pairs"] if p["type_strict"] and lab["components"][p["gt"]]["label"]]
    if not pairs:
        return None
    ok = sum(norm(lab["components"][p["gt"]]["label"]) == norm(an["components"][p["pred"]].get("label", ""))
             for p in pairs)
    return ok / len(pairs)


def _count_api_calls(run_dir: Path) -> dict:
    out = {}
    for st in (run_dir / "raw").glob("*"):
        if st.is_dir() and st.name not in ("pipeline_build", "oracle_build", "analyze_cv"):
            out[st.name] = len(list(st.glob("*.json")))
    return out


if __name__ == "__main__":
    sys.exit(main())
