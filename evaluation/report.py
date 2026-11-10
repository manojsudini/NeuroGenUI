"""Aggregate per-case rows into summary.json, per-case CSVs, tables.md and plots (PNG 300 dpi + PDF)."""
from __future__ import annotations

import csv
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from common import CATEGORIES, CMD_CATEGORIES, write_json  # noqa: E402

log = logging.getLogger("eval.report")

# validated categorical palette (dataviz reference palette, slots 1-4, light mode)
COLORS = {"pipeline": "#2a78d6", "baseline": "#eb6834", "oracle": "#1baf7a", "pipeline_voice": "#eda100",
          "pipeline_norepair": "#6250d6", "cv": "#eda100", "vision": "#1baf7a", "hybrid": "#2a78d6",
          "text": "#2a78d6", "asr": "#eda100", "detected": "#2a78d6", "localised": "#1baf7a", "repaired": "#eb6834"}
NAMES = {"pipeline": "Proposed (NeuroGenUI)", "baseline": "Baseline (sketch→AI→UI)", "oracle": "Oracle (GT IR)",
         "pipeline_voice": "Proposed, Whisper transcript", "pipeline_norepair": "Proposed, before repair",
         "cv": "OpenCV only", "vision": "Vision LLM only", "hybrid": "Hybrid (CV + vision)",
         "text": "ground-truth text", "asr": "Whisper transcript", "detected": "detected", "localised": "localised",
         "repaired": "repaired"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


# ---------------------------------------------------------------- small stats helpers
def vals(rows, key, **flt):
    out = []
    for r in rows:
        if all(r.get(k) == v for k, v in flt.items()):
            v = r.get(key)
            if v is None or v == "":
                continue
            out.append(float(v))
    return out


def mean(xs):
    return float(np.mean(xs)) if xs else None


def rate(rows, key, **flt):
    xs = [r.get(key) for r in rows if all(r.get(k) == v for k, v in flt.items()) and r.get(key) is not None]
    return (sum(bool(x) for x in xs) / len(xs)) if xs else None, len(xs)


def pct(x):
    return None if x is None else round(100 * x, 1)


def fmt(x, nd=1):
    if x is None:
        return "–"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def micro_prf(rows, tp_key="tp", **flt):
    sel = [r for r in rows if all(r.get(k) == v for k, v in flt.items()) and r.get("n_gt") is not None]
    if not sel:
        return None, None, None, 0
    tp = sum(r[tp_key] for r in sel)
    npred = sum(r["n_pred"] for r in sel)
    ngt = sum(r["n_gt"] for r in sel)
    p = tp / npred if npred else 0.0
    r_ = tp / ngt if ngt else 0.0
    f = 2 * p * r_ / (p + r_) if p + r_ else 0.0
    return p, r_, f, len(sel)


def dstats(xs):
    if not xs:
        return {"mean": None, "median": None, "p95": None, "n": 0}
    a = np.array(xs, float)
    return {"mean": float(a.mean()), "median": float(np.median(a)), "p95": float(np.percentile(a, 95)), "n": len(a)}


# ---------------------------------------------------------------- outputs
def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})


def md_table(t):
    out = [f"### {t['title']}", "", "| " + " | ".join(t["columns"]) + " |",
           "|" + "|".join("---" for _ in t["columns"]) + "|"]
    for row in t["rows"]:
        out.append("| " + " | ".join(fmt(c) if not isinstance(c, str) else c for c in row) + " |")
    if t.get("note"):
        out += ["", f"_{t['note']}_"]
    return "\n".join(out) + "\n"


def _style_ax(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def grouped_bars(path_base: Path, title, groups, series, data, ylabel, ylim=None, value_fmt="{:.0f}",
                 figsize=(6.6, 3.0), legend_cols=None):
    """data[s][g] -> value or None. Saves PNG (300 dpi) and PDF."""
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5})
    fig, ax = plt.subplots(figsize=figsize)
    n = len(series)
    width = 0.8 / max(n, 1)
    x = np.arange(len(groups))
    for i, s in enumerate(series):
        ys = [data[s].get(g) for g in groups]
        ysafe = [0 if y is None else y for y in ys]
        bars = ax.bar(x - 0.4 + width * (i + 0.5), ysafe, width * 0.92, color=COLORS.get(s, "#999"),
                      label=NAMES.get(s, s), edgecolor="white", linewidth=0.8)
        for b, y in zip(bars, ys):
            if y is None:
                ax.text(b.get_x() + b.get_width() / 2, 0, "n/a", ha="center", va="bottom", fontsize=6, color=INK2)
            elif n <= 4 or len(groups) <= 4:
                ax.text(b.get_x() + b.get_width() / 2, y, value_fmt.format(y), ha="center", va="bottom",
                        fontsize=6.3, color=INK)
    ax.set_xticks(x, groups, rotation=0 if len(groups) <= 6 else 30, ha="center" if len(groups) <= 6 else "right")
    ax.set_ylabel(ylabel, color=INK2)
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_title(title, fontsize=9.5, color=INK, loc="left")
    _style_ax(ax)
    if n > 1:
        ax.legend(frameon=False, fontsize=7.5, ncol=legend_cols or min(n, 4), loc="upper left",
                  bbox_to_anchor=(0, -0.18 if len(groups) <= 6 else -0.32))
    fig.tight_layout()
    fig.savefig(path_base.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(path_base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def stacked_latency(path_base, stages, pipe_means, base_mean, title):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5})
    fig, ax = plt.subplots(figsize=(6.6, 2.4))
    stage_cols = ["#2a78d6", "#1baf7a", "#eda100", "#6250d6", "#e87ba4", "#008300"]
    left = 0
    for st, col in zip(stages, stage_cols):
        v = pipe_means.get(st) or 0
        ax.barh(1, v / 1000, left=left / 1000, color=col, edgecolor="white", linewidth=1.2, height=0.55, label=st)
        left += v
    ax.text(left / 1000, 1, f"  {left / 1000:.1f} s", va="center", fontsize=7.5, color=INK)
    if base_mean is not None:
        ax.barh(0, base_mean / 1000, color=COLORS["baseline"], height=0.55, edgecolor="white", label="baseline_generate")
        ax.text(base_mean / 1000, 0, f"  {base_mean / 1000:.1f} s", va="center", fontsize=7.5, color=INK)
    ax.set_yticks([0, 1], ["Baseline", "Proposed"])
    ax.set_xlabel("mean latency per UI (s)", color=INK2)
    ax.set_title(title, fontsize=9.5, loc="left", color=INK)
    _style_ax(ax)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.yaxis.grid(False)
    ax.legend(frameon=False, fontsize=7, ncol=4, loc="upper left", bbox_to_anchor=(0, -0.3))
    fig.tight_layout()
    fig.savefig(path_base.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(path_base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- main
def build_report(run_dir: Path, rows: dict, meta: dict, sketches, commands):
    csv_dir = run_dir / "csv"
    plots = run_dir / "plots"
    csv_dir.mkdir(parents=True, exist_ok=True)
    plots.mkdir(parents=True, exist_ok=True)
    for name, rs in rows.items():
        write_csv(csv_dir / f"{name}.csv", rs)

    M, T, C, P = {}, [], [], []

    def metric(name, pipeline, baseline, unit, desc, **extra):
        M[name] = {"pipeline": pipeline, "baseline": baseline, "unit": unit, "description": desc, **extra}

    da, dd = rows["detection_analysis"], rows["detection_dom"]
    # ---------- 1 detection
    det_tab = []
    for mode in ("cv", "vision", "hybrid"):
        p, r, f, n = micro_prf(da, mode=mode)
        if n:
            _, _, fl, _ = micro_prf(da, "tp_lenient", mode=mode)
            det_tab.append([f"analysis: {NAMES[mode]}", n, pct(p), pct(r), pct(f), pct(fl),
                            pct(mean(vals(da, "type_acc", mode=mode))), fmt(mean(vals(da, "mean_iou", mode=mode)), 3),
                            pct(mean(vals(da, "label_acc", mode=mode)))])
    for s in ("pipeline", "baseline", "oracle"):
        p, r, f, n = micro_prf(dd, system=s)
        if n:
            sel = [x for x in dd if x["system"] == s]
            tpl = None
            det_tab.append([f"rendered DOM: {NAMES[s]}", n, pct(p), pct(r), pct(f), tpl,
                            pct(mean(vals(sel, "type_acc"))), fmt(mean(vals(sel, "mean_iou")), 3), None])
    T.append({"title": "Component detection (micro-averaged over sketches; match = Hungarian, IoU ≥ 0.3, correct type)",
              "columns": ["Detector / output", "Sketches", "Precision %", "Recall %", "F1 %", "F1 lenient %",
                          "Type acc. of matched %", "Mean IoU of matched", "Label acc. %"], "rows": det_tab,
              "note": "Lenient = nav_item≈link, container≈card≈form, input≈textarea. DOM rows use validate.extract_dom "
                      "on the rendered UI with both sides normalised to their content box."})
    f_h = micro_prf(da, mode="hybrid")[2]
    f_bd = micro_prf(dd, system="baseline")[2]
    f_pd = micro_prf(dd, system="pipeline")[2]
    metric("component_detection_f1", pct(f_h), pct(f_bd), "%",
           "Detection F1 (IoU≥0.3 + type). Proposed = hybrid sketch analysis; baseline = components recovered "
           "from its rendered DOM (it has no analysis stage).",
           cv=pct(micro_prf(da, mode="cv")[2]), vision=pct(micro_prf(da, mode="vision")[2]))
    metric("component_detection_f1_dom", pct(f_pd), pct(f_bd), "%",
           "Detection F1 measured identically on both systems' rendered DOM (validate.extract_dom).")
    cat_rows, chart_cat = [], {m: {} for m in ("cv", "vision", "hybrid")}
    for cat in CATEGORIES:
        row = [cat]
        for mode in ("cv", "vision", "hybrid"):
            f = micro_prf(da, mode=mode, category=cat)[2]
            row.append(pct(f))
            chart_cat[mode][cat] = pct(f)
        row.append(pct(micro_prf(dd, system="baseline", category=cat)[2]))
        row.append(pct(micro_prf(dd, system="pipeline", category=cat)[2]))
        cat_rows.append(row)
    T.append({"title": "Detection F1 % per category", "columns": ["Category", "CV", "Vision", "Hybrid",
                                                                    "Baseline (DOM)", "Proposed (DOM)"],
              "rows": cat_rows})
    dt = rows["detection_types"]
    types = sorted({r["gt_type"] for r in dt}, key=lambda t: -sum(1 for r in dt if r["gt_type"] == t))
    type_rows = []
    for t in types:
        row = [t, sum(1 for r in dt if r["gt_type"] == t and r["mode"] == dt[0]["mode"])]
        for mode in ("cv", "vision", "hybrid"):
            sel = [r for r in dt if r["mode"] == mode and r["gt_type"] == t]
            row.append(pct(sum(r["type_ok"] for r in sel) / len(sel)) if sel else None)
        type_rows.append(row)
    T.append({"title": "Per-type detection recall % (GT component found with IoU ≥ 0.3 and the right type)",
              "columns": ["Type", "GT count", "CV", "Vision", "Hybrid"], "rows": type_rows})
    modes_present = [m for m in ("cv", "vision", "hybrid") if any(r["mode"] == m for r in da)]
    if modes_present:
        grouped_bars(plots / "detection_f1_by_category", "Component detection F1 by category",
                     CATEGORIES, modes_present, chart_cat, "F1 (%)", (0, 100))
        P.append("detection_f1_by_category")
        C.append({"title": "Detection F1 by category", "type": "bar", "x": CATEGORIES, "series": modes_present,
                  "data": chart_cat})
        modes_data = {m: {} for m in modes_present}
        for m in modes_present:
            p, r, f, _ = micro_prf(da, mode=m)
            modes_data[m] = {"Precision": pct(p), "Recall": pct(r), "F1": pct(f)}
        grouped_bars(plots / "detection_prf_by_mode", "Sketch analysis: precision / recall / F1",
                     ["Precision", "Recall", "F1"], modes_present, modes_data, "%", (0, 100))
        P.append("detection_prf_by_mode")
        C.append({"title": "Sketch analysis P/R/F1 by mode", "type": "bar", "x": ["Precision", "Recall", "F1"],
                  "series": modes_present, "data": modes_data})

    # ---------- 2 voice
    v = rows["voice"]
    if v:
        tot_err = sum(r.get("wer_S", 0) + r.get("wer_D", 0) + r.get("wer_I", 0) for r in v if "wer" in r)
        tot_n = sum(r.get("wer_N", 0) for r in v if "wer" in r)
        corpus_wer = tot_err / tot_n if tot_n else None
        metric("whisper_wer", pct(corpus_wer), None, "%",
               "Corpus word error rate of Whisper on the TTS audio of the 80 commands (lower is better).",
               mean_per_command=pct(mean(vals(v, "wer"))),
               exact_transcripts=pct(rate([{"x": r["wer"] == 0} for r in v if "wer" in r], "x")[0]))
        rr = []
        chart_v = {"text": {}, "asr": {}}
        for src, nm in (("text", "Ground-truth text"), ("asr", "Whisper transcript")):
            row = [nm, sum(1 for r in v if f"{src}_all_ok" in r)]
            for k, lab in (("op_ok", "Op"), ("target_ok", "Target"), ("params_ok", "Params"), ("all_ok", "All")):
                x = rate(v, f"{src}_{k}")[0]
                row.append(pct(x))
                chart_v[src][lab] = pct(x)
            rr.append(row)
        T.append({"title": "Voice command interpretation accuracy % (intent.parse_commands on the base IR)",
                  "columns": ["Input", "Commands", "Op type", "Target", "Parameters", "All correct"], "rows": rr,
                  "note": f"Whisper corpus WER {fmt(pct(corpus_wer))}% ; target n/a for create, params n/a for remove."})
        metric("voice_command_accuracy", pct(rate(v, "asr_all_ok")[0]), None, "%",
               "Commands fully interpreted (op + target + params) from the Whisper transcript of real TTS audio.",
               from_text=pct(rate(v, "text_all_ok")[0]))
        grouped_bars(plots / "voice_interpretation", "Voice command interpretation accuracy",
                     ["Op", "Target", "Params", "All"], ["text", "asr"],
                     chart_v, "accuracy (%)", (0, 105))
        P.append("voice_interpretation")
        C.append({"title": "Interpretation accuracy", "type": "bar", "x": ["Op", "Target", "Params", "All"],
                  "series": ["text", "asr"], "data": chart_v})
        crow = []
        for cat in CMD_CATEGORIES:
            sel = [r for r in v if r["category"] == cat]
            crow.append([cat, len(sel), pct(mean(vals(sel, "wer"))), pct(rate(sel, "text_all_ok")[0]),
                         pct(rate(sel, "asr_all_ok")[0])])
        T.append({"title": "Voice results per command category", "columns": ["Category", "n", "Mean WER %",
                                                                             "All-correct (text) %",
                                                                             "All-correct (Whisper) %"],
                  "rows": crow})
        vrow = []
        for voice in sorted({r.get("voice") for r in v if r.get("voice")}):
            sel = [r for r in v if r.get("voice") == voice and "wer" in r]
            e = sum(r["wer_S"] + r["wer_D"] + r["wer_I"] for r in sel)
            n = sum(r["wer_N"] for r in sel)
            vrow.append([voice, len(sel), pct(e / n if n else None)])
        T.append({"title": "Whisper WER by TTS voice", "columns": ["TTS voice", "Commands", "Corpus WER %"],
                  "rows": vrow})

    # ---------- 3/4/5 visual, functional, requirements
    vis, fn, rq = rows["visual"], rows["functional"], rows["requirements"]
    systems = [s for s in ("pipeline", "pipeline_norepair", "baseline", "oracle") if any(r["system"] == s for r in vis)]
    if systems:
        trows, chart_q = [], {s: {} for s in systems}
        for s in systems:
            li = mean(vals(vis, "layout_iou", system=s))
            ss = mean(vals(vis, "ssim_edges", system=s))
            ro = rate(vis, "render_ok", system=s)[0]
            fr, fnn = rate(fn, "passed", system=s)
            qr, qn = rate(rq, "passed", system=s)
            trows.append([NAMES[s], len(vals(vis, "layout_iou", system=s)), pct(ro), fmt(li, 3), fmt(ss, 3),
                          f"{fmt(pct(fr))} ({fnn})", f"{fmt(pct(qr))} ({qn})"])
            chart_q[s] = {"Renders": pct(ro), "Layout IoU×100": pct(li), "Edge SSIM×100": pct(ss),
                          "Functional": pct(fr), "Requirements": pct(qr)}
        T.append({"title": "Generated UI quality: visual similarity, functional correctness, requirement satisfaction",
                  "columns": ["System", "Sketches", "Renders %", "Layout IoU", "Edge SSIM", "Functional % (n)",
                              "Requirements % (n)"], "rows": trows,
                  "note": "Same generic DOM procedure for every system. Oracle = deterministic compiler on GT layout "
                          "with no voice semantics (no events), so its functional score is a floor, not a ceiling."})
        metric("visual_similarity_layout_iou", pct(mean(vals(vis, "layout_iou", system="pipeline"))),
               pct(mean(vals(vis, "layout_iou", system="baseline"))), "IoU×100",
               "Mean IoU between GT sketch boxes and Hungarian-assigned rendered elements (content-box normalised).")
        metric("visual_similarity_edge_ssim", pct(mean(vals(vis, "ssim_edges", system="pipeline"))),
               pct(mean(vals(vis, "ssim_edges", system="baseline"))), "SSIM×100",
               "SSIM between edge maps of the sketch and of the rendered screenshot.")
        metric("functional_correctness", pct(rate(fn, "passed", system="pipeline")[0]),
               pct(rate(fn, "passed", system="baseline")[0]), "%",
               "Specified interactions (labels.interactions) that work when simulated in the browser.")
        metric("requirement_satisfaction", pct(rate(rq, "passed", system="pipeline")[0]),
               pct(rate(rq, "passed", system="baseline")[0]), "%",
               "Instruction-derived requirements (named components, input types, images, behaviours) satisfied.")
        hs = [s for s in ("pipeline", "baseline", "oracle") if s in systems]
        groups = ["Layout IoU×100", "Edge SSIM×100", "Functional", "Requirements"]
        grouped_bars(plots / "generation_quality", "Generated UI quality (pipeline vs baseline)", groups, hs,
                     chart_q, "score (%)", (0, 105))
        P.append("generation_quality")
        C.append({"title": "Generated UI quality", "type": "bar", "x": groups, "series": hs, "data": chart_q})
        krow = []
        for kind in ("node_exists", "input_type", "count_at_least", "interaction"):
            krow.append([kind] + [pct(rate(rq, "passed", system=s, kind=kind)[0]) for s in hs])
        T.append({"title": "Requirement satisfaction % by requirement kind", "columns": ["Kind"] + [NAMES[s] for s in hs],
                  "rows": krow})
        frow = []
        for kind in sorted({r["expect"] for r in fn}):
            frow.append([kind, sum(1 for r in fn if r["expect"] == kind and r["system"] == hs[0])] +
                        [pct(rate(fn, "passed", system=s, expect=kind)[0]) for s in hs])
        T.append({"title": "Functional correctness % by interaction type", "columns": ["Interaction", "n"] +
                  [NAMES[s] for s in hs], "rows": frow})

    # ---------- 6 refinement
    rf = rows["refinement"]
    if rf:
        rsys = [s for s in ("pipeline", "pipeline_voice", "baseline") if any(r["system"] == s for r in rf)]
        rrows, chart_r = [], {s: {} for s in rsys}
        for cat in CMD_CATEGORIES + ["all"]:
            row = [cat]
            for s in rsys:
                sel = [r for r in rf if r["system"] == s and (cat == "all" or r["category"] == cat)]
                x = rate(sel, "passed")[0]
                row.append(pct(x))
                if cat != "all":
                    chart_r[s][cat] = pct(x)
            for s in rsys:
                sel = [r for r in rf if r["system"] == s and (cat == "all" or r["category"] == cat)]
                row.append(pct(mean(vals(sel, "preservation"))))
            rrows.append(row)
        T.append({"title": "Refinement success % and preservation % per command category",
                  "columns": ["Category"] + [f"Success: {NAMES[s]}" for s in rsys] +
                             [f"Preserved: {NAMES[s]}" for s in rsys], "rows": rrows,
                  "note": "Success = the command's post-condition holds on the rendered UI after the command. "
                          "Preservation = non-target elements with unchanged type, text, colours, font size and size (±15%)."})
        T.append({"title": "Commands whose post-condition already held on the base UI (before the command)",
                  "columns": ["System", "Checkable commands", "Already satisfied", "Of which counted as success"],
                  "rows": [[NAMES[s], sum(1 for r in rf if r["system"] == s and r.get("pre_satisfied") is not None),
                            sum(1 for r in rf if r["system"] == s and r.get("pre_satisfied")),
                            sum(1 for r in rf if r["system"] == s and r.get("pre_satisfied") and r["passed"])]
                           for s in rsys],
                  "note": "Reported for transparency; event/navigation/resize checks are excluded (they need the "
                          "after-UI). style checks additionally require the colour to have changed."})
        metric("refinement_success_rate", pct(rate(rf, "passed", system="pipeline")[0]),
               pct(rate(rf, "passed", system="baseline")[0]), "%",
               "Commands whose machine-checkable post-condition holds after applying them to the generated UI.",
               pipeline_from_whisper=pct(rate(rf, "passed", system="pipeline_voice")[0]))
        metric("preservation_rate", pct(mean(vals(rf, "preservation", system="pipeline"))),
               pct(mean(vals(rf, "preservation", system="baseline"))), "%",
               "Mean share of unaffected components left unchanged by a refinement command.")
        grouped_bars(plots / "refinement_by_category", "Refinement success by command category", CMD_CATEGORIES,
                     rsys, chart_r, "success (%)", (0, 105))
        P.append("refinement_by_category")
        C.append({"title": "Refinement success by category", "type": "bar", "x": CMD_CATEGORIES, "series": rsys,
                  "data": chart_r})
        sm = {s: {"Success": pct(rate(rf, "passed", system=s)[0]),
                  "Preservation": pct(mean(vals(rf, "preservation", system=s)))} for s in rsys}
        grouped_bars(plots / "refinement_overall", "Voice refinement: success and preservation",
                     ["Success", "Preservation"], rsys, sm, "%", (0, 105), figsize=(4.6, 2.9))
        P.append("refinement_overall")
        C.append({"title": "Refinement overall", "type": "bar", "x": ["Success", "Preservation"], "series": rsys,
                  "data": sm})

    # ---------- 7 validation + repair + fault injection
    rp, ra, fi = rows["repair"], rows["repair_actions"], rows["faults"]
    if rp:
        b, a = rate(rp, "passed_before")[0], rate(rp, "passed_after")[0]
        metric("validation_pass_rate_before_repair", pct(b), None, "%", "Generated UIs passing validate() before repair.")
        metric("validation_pass_rate_after_repair", pct(a), None, "%", "Generated UIs passing validate() after repair_loop.")
        T.append({"title": "Validation before vs after the repair loop (proposed pipeline)",
                  "columns": ["", "Pass rate %", "Mean score", "Mean failing checks"],
                  "rows": [["Before repair", pct(b), fmt(mean(vals(rp, "score_before")), 3),
                            fmt(mean(vals(rp, "failed_before")), 2)],
                           ["After repair", pct(a), fmt(mean(vals(rp, "score_after")), 3),
                            fmt(mean(vals(rp, "failed_after")), 2)]]})
        cnt = Counter(r["action"] for r in ra)
        T.append({"title": "Repair actions applied during generation (by type)", "columns": ["Action", "Count"],
                  "rows": [[k or "?", n] for k, n in cnt.most_common()]})
        grouped_bars(plots / "validation_before_after", "Validation pass rate before / after repair",
                     ["Before repair", "After repair"], ["pipeline"],
                     {"pipeline": {"Before repair": pct(b), "After repair": pct(a)}}, "pass rate (%)", (0, 105),
                     figsize=(3.6, 2.6))
        P.append("validation_before_after")
        C.append({"title": "Validation pass rate", "type": "bar", "x": ["Before repair", "After repair"],
                  "series": ["pipeline"], "data": {"pipeline": {"Before repair": pct(b), "After repair": pct(a)}}})
    if fi:
        frows, chart_f = [], {k: {} for k in ("detected", "localised", "repaired")}
        faults = sorted({r["fault"] for r in fi}, key=lambda f: ["delete_node", "hide_node", "zero_size", "swap_order",
                                                                "break_event", "code_error"].index(f))
        for src in sorted({r["source"] for r in fi}):
            for f in faults + ["all"]:
                sel = [r for r in fi if r["source"] == src and r.get("applicable") and (f == "all" or r["fault"] == f)]
                if not sel:
                    continue
                d, l_, rp_ = rate(sel, "detected")[0], rate(sel, "localised")[0], rate(sel, "repaired")[0]
                frows.append([src, f, len(sel), pct(d), pct(l_), pct(rp_)])
        for f in faults:
            sel = [r for r in fi if r.get("applicable") and r["fault"] == f]
            for k in chart_f:
                chart_f[k][f] = pct(rate(sel, k)[0])
        T.append({"title": "Fault injection: validator detection and repair-loop recovery",
                  "columns": ["IR source", "Fault", "Cases", "Detected %", "Localised %", "Repaired %"],
                  "rows": frows,
                  "note": "One fault per case. Detected = a new failing check vs the clean UI; localised = it targets "
                          "the faulted node; repaired = no new failing check after repair_loop and the fault undone. "
                          "code_error is detection-only (repair recompiles from the IR)."})
        allsel = [r for r in fi if r.get("applicable")]
        metric("fault_detection_rate", pct(rate(allsel, "detected")[0]), None, "%",
               "Injected faults detected by validate() (new failing check).")
        metric("fault_repair_rate", pct(rate(allsel, "repaired")[0]), None, "%",
               "Injected IR faults fully repaired by repair_loop.")
        grouped_bars(plots / "fault_injection", "Fault injection: detection and repair", faults,
                     ["detected", "localised", "repaired"], chart_f, "%", (0, 105))
        P.append("fault_injection")
        C.append({"title": "Fault injection", "type": "bar", "x": faults, "series": ["detected", "localised", "repaired"],
                  "data": chart_f})

    # ---------- 8 time
    tm = rows["timing"]
    if tm:
        trows = []
        order = [("pipeline", "analyze_sketch"), ("pipeline", "interpret"), ("pipeline", "fuse"), ("pipeline", "codegen"),
                 ("pipeline", "total_generate"), ("pipeline", "validate"), ("pipeline", "repair"),
                 ("pipeline", "total_with_validation"), ("baseline", "total_generate"),
                 ("analyze_cv", "analyze_cv"), ("analyze_vision", "analyze_vision"), ("analyze_hybrid", "analyze_hybrid"),
                 ("pipeline", "modify_total"), ("pipeline_voice", "modify_total"), ("baseline", "modify_total")]
        for s, st in order:
            d = dstats(vals(tm, "ms", system=s, stage=st))
            if d["n"]:
                trows.append([s, st, d["n"], fmt(d["mean"], 0), fmt(d["median"], 0), fmt(d["p95"], 0)])
        T.append({"title": "Latency (ms) per stage and end to end", "columns": ["System", "Stage", "n", "Mean", "Median",
                                                                               "p95"], "rows": trows,
                  "note": "Wall-clock times measured around each call in-process; API calls ran with bounded "
                          "concurrency (same for both systems). modify_total for the pipeline = interpret + apply_ops + codegen."})
        pg, bg = dstats(vals(tm, "ms", system="pipeline", stage="total_generate")), \
            dstats(vals(tm, "ms", system="baseline", stage="total_generate"))
        metric("generation_time_ms", pg["mean"], bg["mean"], "ms",
               "Mean end-to-end generation latency (pipeline: analyze + interpret + fuse + codegen).",
               pipeline_median=pg["median"], pipeline_p95=pg["p95"], baseline_median=bg["median"], baseline_p95=bg["p95"],
               pipeline_with_validation_mean=dstats(vals(tm, "ms", system="pipeline", stage="total_with_validation"))["mean"])
        pm, bm = dstats(vals(tm, "ms", system="pipeline", stage="modify_total")), \
            dstats(vals(tm, "ms", system="baseline", stage="modify_total"))
        metric("modification_time_ms", pm["mean"], bm["mean"], "ms", "Mean latency of one voice refinement command.",
               pipeline_median=pm["median"], baseline_median=bm["median"])
        stages = ["analyze_sketch", "interpret", "fuse", "codegen", "validate", "repair"]
        pmeans = {st: dstats(vals(tm, "ms", system="pipeline", stage=st))["mean"] for st in stages}
        if any(pmeans.values()):
            stacked_latency(plots / "latency_stages", stages, pmeans, bg["mean"], "Generation latency by stage")
            P.append("latency_stages")
            C.append({"title": "Generation latency by stage (ms)", "type": "stacked", "x": stages,
                      "series": ["pipeline"], "data": {"pipeline": pmeans, "baseline_total": bg["mean"]}})

    # ---------- 9 code quality
    cq = rows["code_quality"]
    if cq:
        crow, chart_c = [], {}
        keys = [("parses", "Parses %"), ("loc", "LOC"), ("components", "Components"), ("reuse_ratio", "Reuse ratio"),
                ("max_fn_lines", "Max function lines"), ("eslint_warnings", "ESLint msgs"), ("files", "Files")]
        for s, form in (("pipeline", "project"), ("pipeline", "preview"), ("baseline", "preview"), ("oracle", "preview")):
            sel = [r for r in cq if r["system"] == s and r["form"] == form]
            if not sel:
                continue
            row = [f"{NAMES[s]} [{form}]", len(sel)]
            for k, _ in keys:
                if k == "parses":
                    row.append(pct(rate(sel, "parses")[0]))
                else:
                    row.append(fmt(mean(vals(sel, k)), 2 if k == "reuse_ratio" else 1))
            crow.append(row)
            if form == "preview":
                chart_c[s] = {"ESLint msgs": mean(vals(sel, "eslint_warnings")),
                              "Max fn lines": mean(vals(sel, "max_fn_lines")),
                              "Reuse ratio": mean(vals(sel, "reuse_ratio"))}
        T.append({"title": "Code quality of generated React (static analysis, mean per UI)",
                  "columns": ["Code", "UIs"] + [k[1] for k in keys], "rows": crow,
                  "note": "Parsed with @babel/parser (JSX); ESLint 9 recommended + react + react-hooks "
                          "(prop-types/react-in-jsx-scope off for both). Reuse ratio = JSX usages of user-defined "
                          "components / their definitions. [preview] = single-script runtime form used by both systems."})
        metric("code_parse_rate", pct(rate([r for r in cq if r["system"] == "pipeline" and r["form"] == "preview"], "parses")[0]),
               pct(rate([r for r in cq if r["system"] == "baseline"], "parses")[0]), "%", "Generated code that parses.")
        metric("code_eslint_messages", mean(vals(cq, "eslint_warnings", system="pipeline", form="preview")),
               mean(vals(cq, "eslint_warnings", system="baseline", form="preview")), "count/UI",
               "Mean ESLint messages per generated UI (lower is better).")
        metric("code_reuse_ratio", mean(vals(cq, "reuse_ratio", system="pipeline", form="preview")),
               mean(vals(cq, "reuse_ratio", system="baseline", form="preview")), "usages/definition",
               "Component reuse: JSX usages of defined components per definition (higher = more reuse).")
        metric("code_max_function_lines", mean(vals(cq, "max_fn_lines", system="pipeline", form="preview")),
               mean(vals(cq, "max_fn_lines", system="baseline", form="preview")), "lines",
               "Mean length of the longest function per UI (lower = more modular).")
        cs = [s for s in ("pipeline", "baseline", "oracle") if s in chart_c]
        groups = ["ESLint msgs", "Max fn lines", "Reuse ratio"]
        grouped_bars(plots / "code_quality", "Static code quality (mean per UI, preview form)", groups, cs,
                     {s: chart_c[s] for s in cs}, "value", None, value_fmt="{:.1f}")
        P.append("code_quality")
        C.append({"title": "Code quality", "type": "bar", "x": groups, "series": cs, "data": {s: chart_c[s] for s in cs}})

    # ---------- headline table
    head = []
    for name in ("component_detection_f1", "component_detection_f1_dom", "whisper_wer", "voice_command_accuracy",
                 "visual_similarity_layout_iou", "visual_similarity_edge_ssim", "functional_correctness",
                 "requirement_satisfaction", "refinement_success_rate", "preservation_rate",
                 "validation_pass_rate_before_repair", "validation_pass_rate_after_repair", "fault_detection_rate",
                 "fault_repair_rate", "generation_time_ms", "modification_time_ms", "code_parse_rate",
                 "code_eslint_messages", "code_reuse_ratio", "code_max_function_lines"):
        if name in M:
            m = M[name]
            nd = 0 if m["unit"] == "ms" else (2 if m["unit"] in ("usages/definition",) else 1)
            head.append([name, fmt(m["pipeline"], nd) if m["pipeline"] is not None else "–",
                         fmt(m["baseline"], nd) if m["baseline"] is not None else "–", m["unit"]])
    T.insert(0, {"title": "Headline results: proposed pipeline vs baseline", "columns": ["Metric", "Proposed",
                                                                                         "Baseline", "Unit"],
                 "rows": head})

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {"models": _models(), "counts": {"sketches": meta["n_sketches"], "commands": meta["n_commands"],
                                                   "categories": len({s["category"] for s in sketches}),
                                                   "gt_components": sum(len(s["components"]) for s in sketches)},
                   "run": meta},
        "metrics": M, "tables": T, "charts": C,
        "plots": [f"/files/eval/plots/{p}.png" for p in P],
    }
    write_json(run_dir / "summary.json", summary)
    md = [f"# NeuroGenUI evaluation results\n", f"Generated {summary['generated_at']} | "
          f"{meta['n_sketches']} sketches, {meta['n_commands']} commands | run {meta['duration_s']} s | "
          f"models {json.dumps(summary['config']['models'])}\n"]
    md += [md_table(t) for t in T]
    (run_dir / "tables.md").write_text("\n".join(md), encoding="utf-8")
    log.info("report written: %d metrics, %d tables, %d plots", len(M), len(T), len(P))
    return summary


def _models():
    import os
    return {k: os.environ.get(k) for k in ("OPENAI_TEXT_MODEL", "OPENAI_VISION_MODEL", "OPENAI_STT_MODEL",
                                           "OPENAI_TTS_MODEL")}
