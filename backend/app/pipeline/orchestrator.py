"""Pipeline orchestration: runs each stage separately, times it, reports progress and stores a Version.

Stages (names fixed): upload, analyze_sketch, transcribe, interpret, fuse, codegen, validate, repair, save.
"""
from __future__ import annotations

import base64
import copy
import time
from typing import Callable

from .. import config, db
from . import codegen, fusion, intent, refine, repair, sketch, validate
from . import ir as irm

ProgressCb = Callable[[dict], None] | None


class PipelineError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class _Stages:
    """Times stages and forwards start/done/error events to an optional progress callback."""

    def __init__(self, progress_cb: ProgressCb):
        self.cb = progress_cb
        self.timings: dict[str, int] = {}
        self.started = time.perf_counter()

    def emit(self, stage: str, status: str, ms: int = 0, data: dict | None = None) -> None:
        if self.cb:
            self.cb({"event": "stage", "stage": stage, "status": status, "ms": ms, "data": data or {}})

    def run(self, stage: str, fn, *args, summary: Callable | None = None, **kwargs):
        self.emit(stage, "start")
        t = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            ms = int((time.perf_counter() - t) * 1000)
            self.timings[stage] = ms
            self.emit(stage, "error", ms, {"detail": str(exc)[:300]})
            raise
        ms = int((time.perf_counter() - t) * 1000)
        self.timings[stage] = self.timings.get(stage, 0) + ms
        self.emit(stage, "done", ms, summary(result) if summary else None)
        return result

    def skip(self, stage: str) -> None:
        self.timings.setdefault(stage, 0)

    def total(self) -> dict:
        out = {name: self.timings.get(name, 0) for name in
               ("upload", "analyze_sketch", "transcribe", "interpret", "fuse", "codegen", "validate", "repair", "save")}
        out["total"] = int((time.perf_counter() - self.started) * 1000)
        return out


# --------------------------------------------------------------------------- files

def sketch_path(sketch_row: dict):
    return config.DATA_DIR / "sketches" / sketch_row["filename"]


def sketch_url(sketch_row: dict | None) -> str | None:
    return f"/files/sketches/{sketch_row['filename']}" if sketch_row else None


def _store_screenshot(report: dict, project_id: str, number: int) -> dict:
    report = dict(report)
    shot = report.pop("screenshot_b64", None)
    if shot:
        name = f"{project_id}_v{number}.png"
        (config.DATA_DIR / "shots" / name).write_bytes(base64.b64decode(shot))
        report["screenshot_url"] = f"/files/shots/{name}"
    return report


def analyze(sketch_id: str, mode: str = "hybrid") -> dict:
    """Analyse an uploaded sketch (cached per mode); saves the overlay PNG and returns the analysis."""
    row = db.get_sketch(sketch_id)
    if row is None:
        raise PipelineError(404, f"sketch {sketch_id} not found")
    cache = row["analysis"] or {}
    if mode in cache:
        return {**cache[mode], "cached": True}
    analysis = sketch.analyze_sketch(sketch_path(row).read_bytes(), mode=mode)
    overlay = sketch.overlay_png(analysis)
    analysis.pop("overlay_png_b64", None)
    if overlay:
        name = f"{sketch_id}_{mode}.png"
        (config.DATA_DIR / "overlays" / name).write_bytes(overlay)
        analysis["overlay_url"] = f"/files/overlays/{name}"
    analysis["sketch_id"] = sketch_id
    cache[mode] = analysis
    db.save_analysis(sketch_id, cache)
    return analysis


# --------------------------------------------------------------------------- shared tail: codegen, validate, repair, save

def _finish(stages: _Stages, *, project_id: str, kind: str, ir: dict, parent: int | None, text: str, source: str,
            ops: list, changes: list, sketch_id: str | None, analysis: dict | None, auto_repair: bool,
            extra: dict | None = None, reference: dict | None = None) -> dict:
    """`reference` = IR of the previous version (refinements): validate flags nodes that vanished or got hidden since, repair restores them."""
    number = db.next_version_number(project_id)
    code = stages.run("codegen", codegen.generate_code, ir, version=number,
                      summary=lambda r: {k: r["stats"][k] for k in ("files", "components", "loc")})
    report = stages.run("validate", validate.validate, ir, code["preview"], analysis, reference,
                        summary=lambda r: {"passed": r["passed"], "score": r["score"]})
    repairs: list = []
    if auto_repair and not report["passed"]:
        fixed = stages.run("repair", repair.repair_loop, ir, analysis, 3, code, report, reference=reference,
                           summary=lambda r: {"repairs": len(r["repairs"]), "passed": r["report"]["passed"]})
        ir, code, report, repairs = fixed["ir"], fixed["code"], fixed["report"], fixed["repairs"]
    else:
        stages.skip("repair")

    def save():
        version = {
            "project_id": project_id, "number": number, "parent": parent, "kind": kind,
            "text": text, "source": source, "ops": ops, "changes": changes, "ir": ir, "ir_synced": True,
            "files": code["files"], "preview": code["preview"], "code_stats": code["stats"],
            "sketch_id": sketch_id, "analysis": analysis,
            "validation": _store_screenshot(report, project_id, number), "repairs": repairs,
            **(extra or {}),
        }
        version["timings"] = stages.total()
        return db.save_version(version)

    version = stages.run("save", save, summary=lambda v: {"number": v["number"]})
    version["timings"] = stages.total()
    db.update_version(version)
    return version


# --------------------------------------------------------------------------- generate / modify

def run_generate(project_id: str, sketch_id: str | None, text: str, source: str = "text",
                 progress_cb: ProgressCb = None, mode: str = "hybrid", auto_repair: bool = True,
                 transcribe_ms: int | None = None) -> dict:
    """Sketch (+ description) -> fused IR -> React -> validated (and repaired) Version."""
    if db.get_project_row(project_id) is None:
        raise PipelineError(404, f"project {project_id} not found")
    text = (text or "").strip()
    if not sketch_id and not text:
        raise PipelineError(400, "Provide a sketch, a description, or both")
    stages = _Stages(progress_cb)
    analysis = None
    if sketch_id:
        row = stages.run("upload", db.get_sketch, sketch_id, summary=lambda r: {"sketch_id": sketch_id})
        if row is None or row["project_id"] != project_id:
            raise PipelineError(404, f"sketch {sketch_id} not found in project {project_id}")
        analysis = stages.run("analyze_sketch", analyze, sketch_id, mode,
                              summary=lambda a: {"components": len(a["components"]), "mode": a["mode"],
                                                 "overlay_url": a.get("overlay_url"), "cached": a.get("cached", False)})
    else:
        stages.skip("upload")
        stages.skip("analyze_sketch")
    stages.timings["transcribe"] = int(transcribe_ms or 0)
    interpreted = {"ops": [], "model": None, "latency_ms": 0}
    if text:
        interpreted = stages.run("interpret", intent.parse_commands, text, None,
                                 summary=lambda r: {"ops": len(r["ops"]), "model": r["model"]})
    else:
        stages.skip("interpret")
    ir, changes = stages.run("fuse", fusion.fuse_with_report, analysis, interpreted["ops"],
                             summary=lambda r: {"nodes": sum(1 for _ in irm.walk(r[0])), "pages": len(r[0]["pages"])})
    if analysis and analysis.get("title") and not any(op.get("meta", {}).get("title") for op in interpreted["ops"]):
        ir["meta"]["title"] = analysis["title"]
    if not db.list_versions(project_id) and ir["meta"].get("title"):
        row = db.get_project_row(project_id)
        if row and row["name"] in ("Untitled project", "New project", ""):
            db.rename_project(project_id, ir["meta"]["title"])
    return _finish(stages, project_id=project_id, kind="generate", ir=ir, parent=_latest_number(project_id),
                   text=text, source=source, ops=interpreted["ops"], changes=changes, sketch_id=sketch_id,
                   analysis=analysis, auto_repair=auto_repair,
                   extra={"interpret": {"model": interpreted.get("model"), "latency_ms": interpreted.get("latency_ms")}})


def run_modify(project_id: str, text: str, source: str = "text", base_version: int | None = None,
               progress_cb: ProgressCb = None, auto_repair: bool = True, transcribe_ms: int | None = None,
               ops: list | None = None) -> dict:
    """Voice/text command -> Ops -> apply to the existing IR -> regenerate -> validate (and repair)."""
    base = db.get_version(project_id, base_version)
    if base is None:
        raise PipelineError(404, "no version to modify; generate a UI first")
    text = (text or "").strip()
    if not text and not ops:
        raise PipelineError(400, "Empty command")
    stages = _Stages(progress_cb)
    stages.skip("upload")
    stages.skip("analyze_sketch")
    stages.timings["transcribe"] = int(transcribe_ms or 0)
    if ops is None:
        interpreted = stages.run("interpret", intent.parse_commands, text, base["ir"],
                                 summary=lambda r: {"ops": len(r["ops"]), "model": r["model"]})
    else:
        interpreted = {"ops": ops, "model": None, "latency_ms": 0}
        stages.skip("interpret")
    result = stages.run("fuse", refine.apply_ops, base["ir"], interpreted["ops"],
                        summary=lambda r: {"changes": len(r["changes"]), "ok": sum(c["ok"] for c in r["changes"])})
    return _finish(stages, project_id=project_id, kind="modify", ir=result["ir"], parent=base["number"],
                   text=text, source=source, ops=interpreted["ops"], changes=result["changes"],
                   sketch_id=base.get("sketch_id"), analysis=base.get("analysis"), auto_repair=auto_repair,
                   extra={"interpret": {"model": interpreted.get("model"), "latency_ms": interpreted.get("latency_ms")}},
                   reference=base["ir"])


# --------------------------------------------------------------------------- validate / versions

def run_validate(project_id: str, number: int | None = None, do_repair: bool = False) -> dict:
    version = db.get_version(project_id, number)
    if version is None:
        raise PipelineError(404, "version not found")
    t = time.perf_counter()
    reference = _reference_ir(project_id, version)
    report = validate.validate(version["ir"], version["preview"], version.get("analysis"), reference)
    validate_ms = int((time.perf_counter() - t) * 1000)
    out = _store_screenshot(report, project_id, version["number"])
    out["repairs"] = []
    if do_repair and not report["passed"]:
        t = time.perf_counter()
        fixed = repair.repair_loop(version["ir"], version.get("analysis"), 3,
                                   {"files": version["files"], "preview": version["preview"],
                                    "stats": version.get("code_stats", {})},
                                   report, manual_code=not version.get("ir_synced", True), reference=reference)
        repair_ms = int((time.perf_counter() - t) * 1000)
        if fixed["repairs"]:
            number_new = db.next_version_number(project_id)
            new = {
                "project_id": project_id, "number": number_new, "parent": version["number"], "kind": "repair",
                "text": "Automatic repair", "source": "text", "ops": [], "changes": [], "ir": fixed["ir"],
                "ir_synced": True, "files": fixed["code"]["files"], "preview": fixed["code"]["preview"],
                "code_stats": fixed["code"]["stats"], "sketch_id": version.get("sketch_id"),
                "analysis": version.get("analysis"),
                "validation": _store_screenshot(fixed["report"], project_id, number_new),
                "repairs": fixed["repairs"],
                "timings": {"validate": validate_ms, "repair": repair_ms, "total": validate_ms + repair_ms},
            }
            out["repairs"] = fixed["repairs"]
            out["new_version"] = db.save_version(new)
    return out


def _reference_ir(project_id: str, version: dict) -> dict | None:
    """Snapshot for recovery: the parent's IR of a refinement (modify) version; other kinds have no meaningful predecessor."""
    if version.get("kind") != "modify" or version.get("parent") is None:
        return None
    parent = db.get_version(project_id, version["parent"])
    return parent["ir"] if parent else None


def _latest_number(project_id: str) -> int | None:
    return db.version_count(project_id)[1]


def _derived_version(project_id: str, kind: str, base: dict, text: str, **fields) -> dict:
    number = db.next_version_number(project_id)
    version = {
        "project_id": project_id, "number": number, "parent": base["number"], "kind": kind, "text": text,
        "source": "text", "ops": [], "changes": [], "ir": base["ir"], "ir_synced": base.get("ir_synced", True),
        "files": base["files"], "preview": base["preview"], "code_stats": base.get("code_stats", {}),
        "sketch_id": base.get("sketch_id"), "analysis": base.get("analysis"),
        "validation": base.get("validation"), "repairs": [], "timings": {"total": 0},
    }
    version.update(fields)
    return version


def restore(project_id: str, number: int) -> dict:
    base = db.get_version(project_id, number)
    if base is None:
        raise PipelineError(404, "version not found")
    latest = _latest_number(project_id)
    version = _derived_version(project_id, "restore", base, f"Restored version {number}")
    version["parent"] = latest
    return db.save_version(version)


def manual_ir(project_id: str, ir: dict, base_version: int | None, auto_validate: bool = True) -> dict:
    base = db.get_version(project_id, base_version)
    if base is None:
        raise PipelineError(404, "base version not found")
    if not isinstance(ir, dict) or not ir.get("pages"):
        raise PipelineError(422, "IR must contain at least one page")
    stages = _Stages(None)
    ir = copy.deepcopy(ir)
    return _finish(stages, project_id=project_id, kind="manual_ir", ir=ir, parent=base["number"],
                   text="Manual IR edit", source="text", ops=[], changes=[], sketch_id=base.get("sketch_id"),
                   analysis=base.get("analysis"), auto_repair=False)


def manual_code(project_id: str, files: dict, preview: str, base_version: int | None) -> dict:
    base = db.get_version(project_id, base_version)
    if base is None:
        raise PipelineError(404, "base version not found")
    number = db.next_version_number(project_id)
    t = time.perf_counter()
    report = validate.validate(base["ir"], preview, base.get("analysis"))
    ms = int((time.perf_counter() - t) * 1000)
    merged = {**base["files"], **(files or {})}
    version = _derived_version(project_id, "manual_code", base, "Manual code edit", files=merged, preview=preview,
                               ir_synced=False, validation=_store_screenshot(report, project_id, number),
                               timings={"validate": ms, "total": ms})
    version["number"] = number
    return db.save_version(version)
