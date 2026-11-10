"""NeuroGenUI API (FastAPI). Run: uvicorn app.main:app --port 8200"""
from __future__ import annotations

import io
import json
import queue
import re
import threading
import zipfile
from contextlib import asynccontextmanager

import cv2
import openai
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .pipeline import codegen, intent, orchestrator, sketch, speech, validate
from .pipeline import ir as irm
from .schemas import (AnalyzeRequest, CodePut, GenerateRequest, InterpretRequest, IRPatch, ModifyRequest,
                      ProjectCreate, ValidateRequest)

MAX_UPLOAD = 15 * 1024 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    threading.Thread(target=_warm_browser, daemon=True).start()
    yield


def _warm_browser() -> None:
    try:
        validate.warm_up()
    except Exception as exc:  # reported by /api/health; validation will retry
        print(f"[neurogenui] browser warm-up failed: {exc}")


app = FastAPI(title="NeuroGenUI API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5200", "http://127.0.0.1:5200", "http://localhost:8200", "http://127.0.0.1:8200"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

brief = APIRouter()   # the 7 brief endpoints, mounted at / and /api
api = APIRouter(prefix="/api")


# --------------------------------------------------------------------------- errors

@app.exception_handler(config.OpenAIUnavailable)
async def _no_key(_request: Request, exc: config.OpenAIUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(orchestrator.PipelineError)
async def _pipeline_error(_request: Request, exc: orchestrator.PipelineError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.exception_handler(openai.APIError)
async def _openai_error(_request: Request, exc: openai.APIError):
    # 500, not 502: the frontend reads 502 as "backend unreachable"
    return JSONResponse(status_code=500, content={"detail": f"OpenAI error: {getattr(exc, 'message', str(exc))}"})


@app.exception_handler(ValueError)
async def _value_error(_request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# --------------------------------------------------------------------------- helpers

def _version_summary(v: dict) -> dict:
    validation = v.get("validation") or {}
    return {
        "number": v["number"], "parent": v.get("parent"), "kind": v["kind"], "text": v.get("text", ""),
        "source": v.get("source", "text"), "created_at": v.get("created_at"),
        "passed": validation.get("passed"), "score": validation.get("score"),
        "screenshot_url": validation.get("screenshot_url"),
        "changes": len(v.get("changes") or []), "changes_ok": sum(1 for c in v.get("changes") or [] if c.get("ok")),
        "repairs": len(v.get("repairs") or []), "ir_synced": v.get("ir_synced", True),
        "total_ms": (v.get("timings") or {}).get("total"),
    }


def _project_summary(row: dict) -> dict:
    count, latest = db.version_count(row["id"])
    latest_version = db.get_version(row["id"], latest) if latest else None
    sketch_row = db.latest_sketch(row["id"])
    shot = ((latest_version or {}).get("validation") or {}).get("screenshot_url")
    return {
        "id": row["id"], "name": row["name"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        "versions": count, "latest_version": latest,
        "thumbnail_url": shot or orchestrator.sketch_url(sketch_row),
        "sketch_url": orchestrator.sketch_url(sketch_row),
        "sketch_id": sketch_row["id"] if sketch_row else None,
    }


def _project_or_404(project_id: str) -> dict:
    row = db.get_project_row(project_id)
    if row is None:
        raise HTTPException(404, f"project {project_id} not found")
    return row


def _sse(run) -> StreamingResponse:
    """Run a pipeline function in a thread and stream its stage events as SSE (POST + fetch reader)."""
    events: queue.Queue = queue.Queue()

    def worker():
        try:
            version = run(events.put)
            events.put({"event": "result", "version": version})
        except orchestrator.PipelineError as exc:
            events.put({"event": "error", "detail": exc.detail, "status": exc.status})
        except config.OpenAIUnavailable as exc:
            events.put({"event": "error", "detail": str(exc), "status": 503})
        except openai.APIError as exc:
            events.put({"event": "error", "detail": f"OpenAI error: {getattr(exc, 'message', str(exc))}", "status": 500})
        except Exception as exc:  # surface the failure to the client instead of hanging the stream
            events.put({"event": "error", "detail": f"{type(exc).__name__}: {exc}", "status": 500})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            try:
                item = events.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- brief endpoints (/ and /api)

@brief.post("/upload-sketch")
async def upload_sketch(file: UploadFile = File(...), project_id: str | None = Form(None)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Sketch is larger than 15 MB")
    try:
        img = sketch.decode(data)
    except ValueError:
        raise HTTPException(415, "Upload a PNG or JPG image")
    if project_id:
        _project_or_404(project_id)
    else:
        name = re.sub(r"\.[a-z0-9]+$", "", file.filename or "", flags=re.I).replace("_", " ").strip() or "Untitled project"
        project_id = db.create_project(name.title() if name != "Untitled project" else name)["id"]
    sid = db.new_id("s")
    filename = f"{sid}.png"
    cv2.imwrite(str(config.DATA_DIR / "sketches" / filename), img)
    height, width = img.shape[:2]
    db.add_sketch(project_id, filename, width, height, sketch_id=sid)
    return {"sketch_id": sid, "project_id": project_id, "url": f"/files/sketches/{filename}",
            "width": width, "height": height}


@brief.post("/analyze-sketch")
def analyze_sketch(body: AnalyzeRequest):
    return orchestrator.analyze(body.sketch_id, body.mode)


@brief.post("/voice-to-text")
def voice_to_text(file: UploadFile = File(...)):
    # A plain `def` runs in the thread pool, so a slow transcription never blocks the event loop.
    data = file.file.read()
    if not data:
        raise HTTPException(400, "Empty audio")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "Audio is larger than 25 MB")
    return speech.transcribe(data, file.filename or "audio.webm")


@brief.post("/generate-ui")
def generate_ui(body: GenerateRequest, stream: int = 0):
    project_id = body.project_id
    if not project_id:
        if body.sketch_id and (row := db.get_sketch(body.sketch_id)):
            project_id = row["project_id"]
        else:
            project_id = db.create_project("Untitled project")["id"]
    _project_or_404(project_id)

    def run(cb=None):
        return orchestrator.run_generate(project_id, body.sketch_id, body.text, body.source, cb, body.mode,
                                         body.auto_repair, body.transcribe_ms)

    return _sse(run) if stream else run()


@brief.post("/modify-ui")
def modify_ui(body: ModifyRequest, stream: int = 0):
    _project_or_404(body.project_id)
    ops = [op.model_dump(exclude_none=True) for op in body.ops] if body.ops else None

    def run(cb=None):
        return orchestrator.run_modify(body.project_id, body.text, body.source, body.base_version, cb,
                                       body.auto_repair, body.transcribe_ms, ops)

    return _sse(run) if stream else run()


@brief.post("/validate-ui")
def validate_ui(body: ValidateRequest):
    _project_or_404(body.project_id)
    return orchestrator.run_validate(body.project_id, body.version, body.repair)


@brief.get("/project/{project_id}")
def get_project(project_id: str):
    row = _project_or_404(project_id)
    versions = db.list_versions(project_id)
    out = _project_summary(row)
    out["version_count"] = out["versions"]
    out["versions"] = [_version_summary(v) for v in versions]
    out["latest"] = versions[-1] if versions else None
    out["sketch"] = db.latest_sketch(project_id)
    return out


# --------------------------------------------------------------------------- /api only

@api.get("/health")
def health():
    return {"ok": True, "openai_configured": config.openai_configured(), "models": config.models(),
            "browser": validate.browser_name()}


@api.get("/projects")
def list_projects():
    return [_project_summary(r) for r in db.list_project_rows()]


@api.post("/projects")
def create_project(body: ProjectCreate):
    return _project_summary(db.create_project(body.name))


@api.delete("/projects/{project_id}")
def delete_project(project_id: str):
    _project_or_404(project_id)
    return {"ok": db.delete_project(project_id)}


@api.get("/projects/{project_id}")
def get_project_alias(project_id: str):
    return get_project(project_id)


@api.post("/interpret")
def interpret(body: InterpretRequest):
    ir = None
    if body.project_id:
        version = db.get_version(body.project_id, body.version)
        ir = version["ir"] if version else None
    result = intent.parse_commands(body.text, ir)
    return {"ops": result["ops"], "latency_ms": result["latency_ms"], "model": result["model"]}


@api.get("/projects/{project_id}/versions")
def list_versions(project_id: str):
    _project_or_404(project_id)
    return [_version_summary(v) for v in db.list_versions(project_id)]


@api.get("/projects/{project_id}/versions/{number}")
def get_version(project_id: str, number: int):
    version = db.get_version(project_id, number)
    if version is None:
        raise HTTPException(404, "version not found")
    return version


@api.post("/projects/{project_id}/versions/{number}/restore")
def restore_version(project_id: str, number: int):
    _project_or_404(project_id)
    return orchestrator.restore(project_id, number)


@api.patch("/projects/{project_id}/ir")
def patch_ir(project_id: str, body: IRPatch):
    _project_or_404(project_id)
    return orchestrator.manual_ir(project_id, body.ir, body.base_version)


@api.put("/projects/{project_id}/code")
def put_code(project_id: str, body: CodePut):
    _project_or_404(project_id)
    return orchestrator.manual_code(project_id, body.files, body.preview, body.base_version)


@api.get("/projects/{project_id}/versions/{number}/export.zip")
def export_zip(project_id: str, number: int):
    version = db.get_version(project_id, number)
    if version is None:
        raise HTTPException(404, "version not found")
    title = (version.get("ir") or {}).get("meta", {}).get("title") or "neurogenui-app"
    folder = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "neurogenui-app"
    folder = f"{folder}-v{number}"
    text = "\n".join(version["files"].values())
    photos = set(re.findall(r'photo[=:]\s*"(\w+)"', text)) | set(re.findall(r"/photos/(\w+)\.jpg", text))
    if version.get("ir"):
        photos |= codegen.photos_used(version["ir"])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in sorted(version["files"].items()):
            zf.writestr(f"{folder}/{path}", content)
        for key in sorted(photos & set(irm.PHOTO_KEYS)):
            zf.write(config.RUNTIME_DIR / "photos" / f"{key}.jpg", f"{folder}/public/photos/{key}.jpg")
        zf.writestr(f"{folder}/neurogenui-ir.json", json.dumps(version.get("ir"), indent=2))
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{folder}.zip"'})


def _labels(sketch_id: str) -> dict | None:
    path = config.DATASET_DIR / "labels" / f"{sketch_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@api.get("/samples")
def samples():
    folder = config.DATASET_DIR / "sketches"
    if not folder.is_dir():
        return []
    out = []
    for png in sorted(folder.glob("*.png")):
        labels = _labels(png.stem) or {}
        out.append({"id": png.stem, "category": labels.get("category", png.stem.split("_")[0]),
                    "url": f"/files/dataset/sketches/{png.name}",
                    "title": labels.get("title") or png.stem.replace("_", " ").title(),
                    "instruction": labels.get("instruction", "")})
    return out


@api.get("/dataset")
def dataset():
    folder = config.DATASET_DIR / "sketches"
    sketches = []
    if folder.is_dir():
        for png in sorted(folder.glob("*.png")):
            labels = _labels(png.stem) or {}
            sketches.append({"id": png.stem, "category": labels.get("category", ""),
                             "url": f"/files/dataset/sketches/{png.name}",
                             "labels_url": f"/files/dataset/labels/{png.stem}.json",
                             "n_components": len(labels.get("components", [])),
                             "instruction": labels.get("instruction", "")})
    commands = []
    jsonl = config.DATASET_DIR / "commands" / "commands.jsonl"
    if jsonl.is_file():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                cmd = json.loads(line)
            except ValueError:
                continue
            commands.append({"id": cmd.get("id"), "category": cmd.get("category"), "text": cmd.get("text"),
                             "sketch_id": cmd.get("sketch_id"), "expected": cmd.get("expected"),
                             "audio_url": _audio_url(cmd.get("audio"))})
    return {"sketches": sketches, "commands": commands}


def _audio_url(audio: str | None) -> str | None:
    """Command audio paths are relative to dataset/commands/ (fall back to dataset/ for older files)."""
    if not audio:
        return None
    for base, prefix in ((config.DATASET_DIR / "commands", "/files/dataset/commands/"), (config.DATASET_DIR, "/files/dataset/")):
        if (base / audio).is_file():
            return prefix + audio
    return None


@api.get("/eval")
def eval_results():
    summary = config.EVAL_LATEST_DIR / "summary.json"
    if not summary.is_file():
        raise HTTPException(404, "no evaluation results yet")
    data = json.loads(summary.read_text(encoding="utf-8"))
    plots = sorted(p.relative_to(config.EVAL_LATEST_DIR).as_posix() for p in config.EVAL_LATEST_DIR.rglob("*")
                   if p.suffix.lower() in (".png", ".svg", ".jpg"))
    if isinstance(data, dict):
        data.setdefault("plots", [f"/files/eval/{p}" for p in plots])
        return data
    return {"summary": data, "plots": [f"/files/eval/{p}" for p in plots]}


app.include_router(brief)
app.include_router(brief, prefix="/api")
app.include_router(api)

# --------------------------------------------------------------------------- static files + SPA

app.mount("/runtime", StaticFiles(directory=config.RUNTIME_DIR, html=True), name="runtime")
app.mount("/files/sketches", StaticFiles(directory=config.DATA_DIR / "sketches"), name="sketches")
app.mount("/files/overlays", StaticFiles(directory=config.DATA_DIR / "overlays"), name="overlays")
app.mount("/files/shots", StaticFiles(directory=config.DATA_DIR / "shots"), name="shots")
app.mount("/files/dataset", StaticFiles(directory=config.DATASET_DIR, check_dir=False), name="dataset")
app.mount("/files/eval", StaticFiles(directory=config.EVAL_LATEST_DIR, check_dir=False), name="eval")

RESERVED = ("api/", "files/", "runtime/")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    """Serve the built frontend (project/frontend/dist) with an index.html fallback for client routes."""
    dist = config.FRONTEND_DIST
    if path.startswith(RESERVED) or not (dist / "index.html").is_file():
        if not path:
            return JSONResponse({"name": "NeuroGenUI API", "docs": "/docs", "health": "/api/health",
                                 "note": "frontend/dist not built"})
        raise HTTPException(404, "Not found")
    file = (dist / path).resolve()
    if path and file.is_file() and dist.resolve() in file.parents:
        return FileResponse(file)
    return FileResponse(dist / "index.html")

