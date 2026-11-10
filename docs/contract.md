# NeuroGenUI: shared contract (v1)

This is the single source of truth shared by backend, frontend and evaluation. Only the orchestrator edits it. If you need a change, implement the closest compatible thing and report the change you'd like.

## 0. Layout, ports, environment

```
project/
  backend/            FastAPI app (owner: backend agent)
    app/main.py       routes; serves ../frontend/dist at / and runtime at /runtime
    app/config.py     reads ../.env (project/.env)
    app/db.py         SQLite at backend/data/neurogenui.db
    app/schemas.py    pydantic models for everything in this contract
    app/pipeline/     sketch.py speech.py intent.py fusion.py refine.py codegen.py validate.py repair.py baseline.py orchestrator.py
    app/static/runtime/  preview.html + vendor/ (react 18.3.1 UMD, react-dom UMD, @babel/standalone) — fully offline
    data/             sqlite db + uploads (gitignored)
    tests/            pytest
    requirements.txt
  frontend/           React 19 + Vite + Tailwind v4 (owner: UI agent). Dev server port 5200, proxies /api /runtime /files to 8200
  dataset/            sketches + labels + voice commands + generator tools (owner: eval agent)
  evaluation/         eval scripts + results + plots (owner: eval agent)
  paper/              IEEE draft (orchestrator)
  docs/               contract.md (this), architecture assets
  Dockerfile  docker-compose.yml  setup.bat  run.bat  README.md  .env.example  .env
```

- Backend port **8200** (`run.bat` / `uvicorn app.main:app --port 8200`). Never use 8000, 8100 or 5173.
- `.env` (project/.env): `OPENAI_API_KEY`, `OPENAI_TEXT_MODEL=gpt-4.1-mini`, `OPENAI_VISION_MODEL=gpt-4.1-mini`, `OPENAI_STT_MODEL=whisper-1`, `OPENAI_TTS_MODEL=tts-1` (dataset only), `NGUI_PORT=8200`.
- Python 3.11–3.13. Heavy libraries (openai, cv2, playwright) are imported at module top level (Windows lesson: never import them first inside a worker thread).
- No mocks or fake results anywhere. If the key is missing, endpoints that need OpenAI return HTTP 503 `{"detail":"OPENAI_API_KEY not configured"}`. The OpenCV-only paths still work.

## 1. UI Intent Representation (IR), the core JSON

```jsonc
{
  "schema": "neurogenui.ir/1",
  "meta": { "title": "Login", "category": "login", "theme": { "primary": "#e11d74", "radius": 10, "font": "Inter" } },
  "pages": [
    { "id": "page_main", "name": "Main", "route": "/", "root": { /* Node, type "page" */ } }
  ],
  "next_id": 12
}
```

### Node
```jsonc
{
  "id": "btn_login",            // stable, unique across the doc: <typeprefix>_<slug>[_n]
  "type": "page",               // see the type list below
  "label": "Login",             // visible text/content ("" if none)
  "props": {},                  // type-specific, see below
  "style": {},                  // see style keys
  "layout": { "direction": "column", "gap": 12, "align": "stretch", "justify": "start" }, // containers only
  "bbox": { "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05 },  // normalised 0..1 to the sketch frame; null if not from the sketch
  "children": [],
  "relations": [ { "type": "below", "target": "inp_password" } ],  // below|above|left_of|right_of|inside|label_for
  "events": [ { "on": "click", "actions": [ /* Action */ ] } ],     // on: click|submit|change
  "origin": "sketch"            // sketch|voice|repair|manual
}
```

**Types** (with id prefixes): `page`(page) `container`(box) `card`(card) `form`(form) `header`(hdr) `navbar`(nav) `nav_item`(navi) `heading`(h) `text`(txt) `link`(lnk) `button`(btn) `input`(inp) `textarea`(ta) `checkbox`(chk) `radio`(rad) `select`(sel) `image`(img) `list`(list) `divider`(div) `icon`(ico).
Containers that have `children` and `layout`: page, container, card, form, header, navbar, list.

**props per type**
- heading: `level` 1–4
- input: `inputType` text|email|password|tel|number|date|search, `placeholder`, `required` bool, `name`
- textarea: `placeholder`, `rows`; checkbox/radio: `checked` bool, `group` (radio); select: `options` [str]
- image: `alt`, `photo` (a key into the runtime photo library: person, product, banner, food, travel, building, finance, nature, or "" for a neutral placeholder)
- link / nav_item / button: `href_page` (page id) optional
- list: `items` [str] optional

**style keys** (all optional): `variant` primary|secondary|outline|ghost|danger, `color` (CSS colour, the main fill for buttons/accents), `textColor`, `bg`, `size` sm|md|lg, `width` auto|full|<px int>, `height` <px int>, `align` left|center|right, `fontSize` <px int>, `fontWeight` 400|500|600|700, `radius` <px int>, `hidden` bool.
Colour words from voice ("blue") are mapped to hex by the backend (the table lives in `refine.py`) and stored as hex.

### Action (inside events)
```jsonc
{ "type": "validate_required", "targets": ["inp_email","inp_password"], "message": "Please fill in all fields" }
{ "type": "validate_format", "target": "inp_email", "format": "email|phone|number", "message": "Enter a valid email" }
{ "type": "show_message", "text": "Logged in", "tone": "success|error|info" }
{ "type": "navigate", "page": "page_dashboard" }
{ "type": "toggle_visibility", "target": "box_details" }
{ "type": "set_text", "target": "txt_status", "text": "Saved" }
```
Actions run in order. A failing `validate_*` shows its message as an error (in an element with `data-ngmsg="<event owner id>"` and `role="alert"`) and stops the chain.

## 2. Voice/text commands → Ops

`intent.parse_commands(text, ir_or_None) -> list[Op]`. One utterance may yield several ops.

```jsonc
{
  "op": "add|remove|modify|move|resize|style|interaction|navigation|create",
  "target": { "ref": "login button", "id": "btn_login" },          // id resolved by refine.resolve_target if the LLM left it null
  "component": { "type": "link", "label": "Forgot password?", "props": {} },   // add / create (create: "components":[...])
  "position": { "relation": "below|above|left_of|right_of|inside|first|last", "anchor": { "ref": "login button", "id": null } },
  "changes": { "label": "...", "props": {}, "style": {} },        // modify / style / resize
  "event": { "on": "click", "actions": [ /* Action, targets may be refs */ ] },  // interaction
  "page": { "name": "Dashboard" },                                  // navigation (creates the page if missing)
  "confidence": 0.93
}
```
- `create` (initial description) carries `"components": [Node partial...]` and `"meta": {"title","category"}`.
- `resize`: `changes.style` with width/height/size/fontSize, or `"scale": 1.5`.
- `navigation`: target is the clickable element, plus `page.name`. It creates the page if missing and adds a navigate action on click.
- Target resolution (`refine.resolve_target(ir, ref)`) is deterministic: type keywords + label fuzzy match + ordinal words ("second button") + position words. It returns an id and a score. The LLM sees a compact IR outline (id, type, label) so it can fill ids directly. The resolver is used when the id is missing or invalid.

## 3. Python pipeline API (backend/app/pipeline). Evaluation imports these in-process.

```python
# sketch.py
detect_cv(image_bytes) -> list[dict]          # OpenCV candidates: {bbox, shape: rect|circle|line|text|squiggle|cross_box, area, aspect, fill, conf}
analyze_sketch(image_bytes, mode="hybrid")   -> SketchAnalysis   # mode: cv | vision | hybrid
# SketchAnalysis = {"components":[{"type","label","bbox","confidence","source":"cv|vision|hybrid","parent":idx|None}],
#                   "width","height","mode","timings":{"cv_ms","vision_ms","total_ms"}, "overlay_png_b64"?}
# hybrid = OpenCV proposes boxes -> vision model labels numbered boxes and adds text/missed ones -> merge (IoU) -> containment tree

# speech.py
transcribe(audio_bytes, filename) -> {"text","model","duration_ms"}

# intent.py
parse_commands(text, ir=None) -> {"ops":[Op], "model","latency_ms","raw"}

# fusion.py
fuse(analysis: SketchAnalysis | None, ops: list[Op], title=None) -> IR    # sketch gives layout/geometry; voice gives semantics, labels, input types, events; unmatched voice components get inserted at sensible positions

# refine.py
apply_ops(ir, ops) -> {"ir": IR, "changes":[{"op","target","detail","ok":bool,"error"?}]}  # pure, does not mutate the input; untouched nodes stay byte-identical
resolve_target(ir, ref, type_hint=None) -> {"id","score"}
COLOR_WORDS: dict

# codegen.py
generate_code(ir) -> {"files": {"src/App.jsx":..., "src/components/*.jsx":..., "src/pages/*.jsx":..., "src/styles.css":..., "src/runtime/actions.js":..., "package.json":..., "index.html":..., "src/main.jsx":...},
                      "preview": "<single-script JSX for the runtime>", "stats": {"files","components","loc"}}
# Deterministic compiler: one reusable component per type (Button, Field, Heading, ...), pages as components, a router via useState,
# every rendered node has data-ngid="<id>" data-ngtype="<type>". Events compile to handlers in src/runtime/actions.js.
# preview = the same code concatenated with imports stripped, using the React/ReactDOM globals, ending with createRoot(...).render(<App/>)

# validate.py   (Playwright; channel "msedge" on Windows, otherwise bundled chromium; falls back to the other)
validate(ir, preview_code, analysis=None) -> ValidationReport
# ValidationReport = {"passed":bool, "score":0..1, "checks":[{"id","kind":"visual|functional","name","target"?,"ok","detail"}],
#   "visual":{"presence":0..1,"layout_iou":0..1,"order_consistency":0..1}, "functional":{"runtime_errors":[...],"interactions_total","interactions_passed"},
#   "screenshot_b64", "dom":[{"id","type","rect"}], "duration_ms"}
# Checks: every IR node rendered + visible; vertical/horizontal order vs IR/sketch; bbox IoU vs sketch (normalised to page);
# no console/page errors; every button clickable; every input accepts typing; every event: simulate it and assert its effect
# (error message shown for empty required fields, navigation shows target page, toggle changes visibility, ...)

# repair.py
repair_loop(ir, analysis=None, max_iter=3) -> {"ir","code","report","repairs":[{"iteration","check","target","action","result"}]}
# targeted fixes per failed check: missing node -> re-insert from analysis; order mismatch -> reorder siblings; runtime error -> recompile
# the affected component in safe mode; interaction failure -> rebuild that node's event handler; hidden/zero-size -> reset style. Revalidate after each pass.

# baseline.py   (RR-04: the direct sketch -> AI -> UI baseline. ONE vision call: image + instruction -> full React code)
baseline_generate(image_bytes, instruction) -> {"preview","code","latency_ms"}
baseline_modify(preview_code, instruction)   -> {"preview","code","latency_ms"}   # regenerates the whole thing
# Baseline output uses the same runtime contract (single-script JSX on React globals) so the same validator/DOM extractor measures both.

# orchestrator.py
run_generate(project_id, sketch_id|None, text, source="text"|"voice", progress_cb=None) -> Version
run_modify(project_id, text, source, base_version=None, progress_cb=None) -> Version
# stages (names fixed, each timed in ms): upload, analyze_sketch, transcribe, interpret, fuse, codegen, validate, repair, save
```

## 4. REST API

The 7 brief endpoints are mounted **both** at the root (exact brief paths) and under `/api` with the same handlers. The frontend uses `/api/...`.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /api/health | | `{ok, openai_configured, models:{...}, browser:"msedge|chromium|none"}` |
| GET | /api/projects | | `[ProjectSummary]` |
| POST | /api/projects | `{name}` | `ProjectSummary` |
| DELETE | /api/projects/{id} | | `{ok}` |
| GET | /api/project/{id} (also /project/{id}) | | `Project` (summary + versions list + latest Version in full) |
| POST | /api/upload-sketch | multipart `file` (png/jpg), `project_id?` (creates a project if absent) | `{sketch_id, project_id, url, width, height}` |
| POST | /api/analyze-sketch | `{sketch_id, mode?: "hybrid"}` | `SketchAnalysis` + `overlay_url` |
| POST | /api/voice-to-text | multipart `file` (webm/wav/mp3/m4a) | `{text, model, duration_ms}` |
| POST | /api/interpret | `{text, project_id?}` | `{ops, latency_ms}` (preview of how a command is understood) |
| POST | /api/generate-ui | `{project_id, sketch_id?, text, source?: "voice"|"text", mode?: "hybrid", auto_repair?: true}` | `Version` |
| POST | /api/modify-ui | `{project_id, text, source?, base_version?, auto_repair?: true}` | `Version` |
| POST | /api/validate-ui | `{project_id, version?, repair?: false}` | `ValidationReport` (+ `repairs`, `new_version` if repair produced one) |
| GET | /api/projects/{id}/versions | | `[VersionSummary]` |
| GET | /api/projects/{id}/versions/{n} | | `Version` |
| POST | /api/projects/{id}/versions/{n}/restore | | new `Version` (kind "restore") |
| PATCH | /api/projects/{id}/ir | `{ir, base_version}` | new `Version` (kind "manual_ir", code regenerated) |
| PUT | /api/projects/{id}/code | `{files, preview, base_version}` | new `Version` (kind "manual_code", `ir_synced:false`) |
| GET | /api/projects/{id}/versions/{n}/export.zip | | a runnable Vite React project (`npm i && npm run dev`) |
| GET | /api/samples | | `[{id, category, url, title}]` sample sketches from dataset/sketches (demo quick-pick) |
| GET | /api/dataset | | `{sketches:[{id,category,url,labels_url,n_components}], commands:[{id,category,text,audio_url?,expected}]}` |
| GET | /api/eval | | contents of `evaluation/results/latest/summary.json` (+ list of plot urls under /files/eval/...) or 404 |

**Streaming:** `generate-ui` and `modify-ui` accept `?stream=1`. The response is then `text/event-stream` with events
`{"event":"stage","stage":"analyze_sketch","status":"start|done|error","ms":123,"data":{...small}}`, ending with
`{"event":"result","version":{...}}` or `{"event":"error","detail":"..."}`. The frontend reads them with fetch + ReadableStream (POST).

Static: `/files/sketches/<file>`, `/files/overlays/<file>`, `/files/dataset/...` (project/dataset), `/files/eval/...` (project/evaluation/results/latest), `/runtime/preview.html`.

### Version (JSON)
```jsonc
{ "project_id": "p_ab12cd", "number": 3, "parent": 2,
  "kind": "generate|modify|repair|manual_ir|manual_code|restore",
  "text": "make the login button blue", "source": "voice|text",
  "ops": [Op], "changes": [Change], "ir": IR, "ir_synced": true,
  "files": {path: content}, "preview": "...", "code_stats": {...},
  "sketch_id": "s_...", "analysis": SketchAnalysis|null,
  "validation": ValidationReport (screenshot stored as /files/shots/<..>.png, url in validation.screenshot_url),
  "repairs": [...], "timings": {"analyze_sketch": 812, "...": 0, "total": 4210},
  "created_at": "ISO" }
```
`ProjectSummary = {id, name, created_at, updated_at, versions, latest_version, thumbnail_url (latest validation screenshot or sketch), sketch_url}`

## 5. Preview runtime (`/runtime/preview.html`)

- Loads vendored React 18.3.1 UMD, ReactDOM UMD and @babel/standalone, plus `runtime.css` (base styles for generated UIs) and the photo library (`/runtime/photos/<key>.jpg`).
- Code arrives by `?project=<id>&version=<n>` (it fetches `Version.preview`) **or** by `window.postMessage({type:"ngui:code", code})` from the parent. It transpiles (preset react), runs, and renders into `#root`.
- It posts to the parent: `{type:"ngui:ready"}`, `{type:"ngui:error", message, stack}` and `{type:"ngui:rendered", nodes:[{id,type,rect}]}`. Parent → iframe `{type:"ngui:highlight", id}` outlines a node (used by the IR tree hover).
- The validator uses the same page in Playwright, so preview and validation run identical code.

## 6. Dataset format (dataset/)

- `sketches/<id>.png` (e.g. `login_01.png`), 1000px wide, white background, synthetic hand-drawn style; `labels/<id>.json`:
  `{"id","category","synthetic":true,"generator":"...","width","height","instruction":"voice description for the generate step","components":[{"type","label","bbox":{x,y,w,h normalised},"parent":idx|null}], "interactions":[{"event","target_label","expect"}]}`
- `commands/commands.jsonl`: one per line: `{"id":"cmd_001","category":"add|remove|modify|move|resize|style|interaction|navigation","sketch_id":"login_01","text":"...","expected":{"op","target_id"?,"target_ref","params":{...}},"check":{...machine-checkable postcondition on the IR/DOM...},"audio":"audio/cmd_001.mp3"}`
- `dataset/README.md` documents how everything was generated and states clearly that it is synthetic.
